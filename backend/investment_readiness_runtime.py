"""Evidence-based investment-readiness analysis for stocks, funds and ETFs.

This endpoint is decision support, not a buy/sell recommendation. It combines
independent public signals and explicitly reduces confidence when data is missing.
"""
from datetime import datetime, timezone
import threading
import time

import extra_api
import instrument_detail_runtime
from database import connect
from instrument_analytics_runtime import instrument_analytics
from instrument_signal_runtime import score_analytics
from news_routes import _yahoo_news
from news_runtime import aggregate_news
from providers import NordicRegulatoryProvider, YahooProvider

_CACHE = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 180
_CACHE_MAX = 32

_POSITIVE = (
    "raises guidance", "raise guidance", "guidance raised", "strong results", "record results",
    "beats estimates", "beat estimates", "better than expected", "contract award", "new contract",
    "major contract", "order intake", "dividend increase", "increases dividend", "share buyback",
    "upgrade", "upgraded", "profit growth", "revenue growth", "margin improvement", "strong demand",
)
_NEGATIVE = (
    "profit warning", "lowers guidance", "lower guidance", "guidance cut", "cuts guidance",
    "below expectations", "misses estimates", "missed estimates", "weak results", "weak demand",
    "dividend cut", "cuts dividend", "rights issue", "capital raise", "private placement", "dilution",
    "impairment", "liquidity", "covenant", "investigation", "lawsuit", "downgrade", "downgraded",
    "suspension", "suspended", "going concern", "bankruptcy", "default", "restructuring",
)
_SEVERE = (
    "profit warning", "going concern", "bankruptcy", "default", "liquidity crisis", "covenant breach",
    "trading suspended", "suspension", "fraud investigation", "rights issue", "capital raise",
)


def _clamp(value, low=0.0, high=100.0):
    return max(low, min(high, float(value)))


def _base_ticker(symbol):
    value = str(symbol or "").strip().upper()
    return value[:-3] if value.endswith(".OL") else value


def _tracked_stock(symbol):
    ticker = _base_ticker(symbol)
    conn = connect()
    try:
        row = conn.execute(
            "SELECT s.ticker,s.name,s.sector,sc.fundamentals,sc.insider,sc.valuation,sc.sentiment,"
            "sc.total,sc.created_at,COALESCE(sc.source,'stored') source "
            "FROM stocks s JOIN scores sc ON sc.id=(SELECT MAX(id) FROM scores x WHERE x.ticker=s.ticker) "
            "WHERE s.active=1 AND s.ticker=? LIMIT 1",
            (ticker,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _news_pulse(items):
    score = 0.0
    positives, negatives = [], []
    severe = False
    for item in (items or [])[:12]:
        text = " ".join((str(item.get("title") or ""), str(item.get("summary") or ""))).lower()
        if not text.strip():
            continue
        weight = 2.5 if item.get("official") else 1.75 if item.get("news_scope") == "direct" else 1.0
        pos = [k for k in _POSITIVE if k in text]
        neg = [k for k in _NEGATIVE if k in text]
        if pos:
            score += weight
            if len(positives) < 4:
                positives.append(item.get("title") or pos[0])
        if neg:
            score -= weight * 1.25
            if len(negatives) < 4:
                negatives.append(item.get("title") or neg[0])
        if any(k in text for k in _SEVERE):
            severe = True
    return {
        "score": max(-12.0, min(12.0, score)),
        "positive_headlines": positives,
        "risk_headlines": negatives,
        "severe_risk_flag": severe,
    }


def _trend_contribution(analytics, positives, risks):
    score = 0.0
    one = analytics.get("return_1m_pct")
    three = analytics.get("return_3m_pct")
    above = analytics.get("above_sma_200")
    vol = analytics.get("volatility_1y_pct")
    dd = analytics.get("max_drawdown_1y_pct")

    if one is not None:
        if one >= 5:
            score += 5; positives.append(f"1 måneds utvikling er {one:+.1f}%")
        elif one <= -5:
            score -= 5; risks.append(f"1 måneds utvikling er {one:+.1f}%")
    if three is not None:
        if three >= 10:
            score += 8; positives.append(f"3 måneders trend er {three:+.1f}%")
        elif three <= -10:
            score -= 8; risks.append(f"3 måneders trend er {three:+.1f}%")
    if above is True:
        score += 8; positives.append("kursen ligger over 200-dagers snitt")
    elif above is False:
        score -= 8; risks.append("kursen ligger under 200-dagers snitt")
    if vol is not None:
        if vol < 20:
            score += 6; positives.append(f"relativt moderat 1-års volatilitet ({vol:.1f}%)")
        elif vol > 50:
            score -= 10; risks.append(f"svært høy 1-års volatilitet ({vol:.1f}%)")
        elif vol > 35:
            score -= 4; risks.append(f"høy 1-års volatilitet ({vol:.1f}%)")
    if dd is not None:
        if dd > -12:
            score += 5
        elif dd < -35:
            score -= 10; risks.append(f"stort 1-års drawdown ({dd:.1f}%)")
        elif dd < -20:
            score -= 5; risks.append(f"betydelig 1-års drawdown ({dd:.1f}%)")
    return score


def _status(score, coverage, severe):
    if coverage < 55:
        return "WAIT_FOR_DATA", "Vent på mer data", "watch"
    if severe:
        return "ELEVATED_RISK", "Forhøyet risiko", "risk"
    if score >= 70:
        return "MORE_READY", "Mer investeringsklart", "positive"
    if score >= 52:
        return "MIXED", "Blandet / følg med", "watch"
    if score >= 35:
        return "ELEVATED_RISK", "Forhøyet risiko", "risk"
    return "HIGH_RISK", "Høy risiko / vær forsiktig", "risk"


def _brief(name, label, score, positives, risks, news):
    if label == "Mer investeringsklart":
        lead = f"{name} har et forholdsvis robust samlet databilde akkurat nå ({score:.0f}/100)."
    elif label == "Vent på mer data":
        lead = f"NordicSignal har ikke nok ferske, uavhengige datapunkter til å gi {name} en tydelig readiness-status ennå."
    elif label == "Blandet / følg med":
        lead = f"Bildet for {name} er blandet ({score:.0f}/100), uten et tydelig robust eller svakt regime."
    else:
        lead = f"{name} har flere risikofaktorer i det samlede databilde akkurat nå ({score:.0f}/100)."
    if news.get("risk_headlines"):
        lead += " Nyhetsbildet inneholder også minst én tydelig risikohendelse."
    elif news.get("positive_headlines"):
        lead += " Nyhetsbildet har samtidig positive drivere."
    if risks:
        lead += " Viktigste risiko å følge: " + risks[0] + "."
    elif positives:
        lead += " Sterkeste støttepunkt: " + positives[0] + "."
    return lead


def _build(provider, regulatory, requested_symbol):
    requested = str(requested_symbol or "").strip().upper()
    if not requested:
        raise ValueError("Missing symbol")
    tracked = _tracked_stock(requested)
    market_symbol = f"{tracked['ticker']}.OL" if tracked else requested
    snapshot = instrument_detail_runtime.instrument_snapshot(provider, market_symbol)
    asset_class = "Aksjer" if tracked else (snapshot.get("asset_class") or "Øvrig")
    name = tracked.get("name") if tracked else snapshot.get("name") or market_symbol
    analytics = instrument_analytics(provider, market_symbol)

    positives, risks = [], []
    score = 50.0 + _trend_contribution(analytics, positives, risks)
    coverage = 45.0 if analytics.get("data_points", 0) >= 100 else 28.0
    sources = ["Yahoo Finance price/NAV history"]

    if tracked:
        stock_score = float(tracked.get("total") or 50)
        score += _clamp((stock_score - 50.0) * 0.40, -20, 20)
        coverage += 25 if tracked.get("source") in ("live", "partial_live") else 10
        if stock_score >= 70:
            positives.append(f"NordicSignal aksjescore er {stock_score:.0f}/100")
        elif stock_score < 50:
            risks.append(f"NordicSignal aksjescore er {stock_score:.0f}/100")
        fundamentals = tracked.get("fundamentals")
        valuation = tracked.get("valuation")
        if fundamentals is not None:
            if fundamentals >= 28: score += 5; positives.append(f"fundamentalscore {fundamentals}/40")
            elif fundamentals < 16: score -= 6; risks.append(f"svak fundamentalscore {fundamentals}/40")
        if valuation is not None:
            if valuation >= 13: score += 3
            elif valuation < 7: score -= 4; risks.append(f"svak verdsettelsesscore {valuation}/20")
        sources.append("NordicSignal coverage-aware Oslo Børs score")
        try:
            company = tracked.get("name") or tracked["ticker"]
            def old_news(ticker, limit=20):
                return _yahoo_news(provider, ticker, company, limit)
            news_data = aggregate_news(old_news, tracked["ticker"], company, 12)
        except Exception as exc:
            news_data = {"items": [], "status": "unavailable", "detail": str(exc)}
        try:
            short = regulatory.short(tracked["ticker"], tracked.get("name") or "")
            short_pct = short.get("short_percent_float")
            if short_pct is not None:
                coverage += 8
                sources.append("Finanstilsynet Short Sale Register")
                short_pct = float(short_pct)
                if short_pct >= 5: score -= 10; risks.append(f"høy offentlig shortandel ({short_pct:.2f}%)")
                elif short_pct >= 3: score -= 6; risks.append(f"forhøyet offentlig shortandel ({short_pct:.2f}%)")
                elif short_pct >= 1.5: score -= 3
        except Exception:
            short = {"status": "unavailable"}
    else:
        signal = score_analytics(analytics, asset_class if asset_class in ("Fond", "ETF") else "ETF")
        signal_score = float(signal.get("score") or 50)
        score += _clamp((signal_score - 50.0) * 0.32, -16, 16)
        coverage += 22
        if signal_score >= 72:
            positives.append(f"historisk trend-/risikomodell er {signal_score:.0f}/100")
        elif signal_score < 52:
            risks.append(f"historisk trend-/risikomodell er {signal_score:.0f}/100")
        sources.append("NordicSignal history trend/risk model")
        short = None
        try:
            news_data = instrument_detail_runtime.instrument_news(provider, market_symbol, name, 12)
        except Exception as exc:
            news_data = {"items": [], "status": "unavailable", "detail": str(exc)}

    news = _news_pulse(news_data.get("items") or [])
    score += news["score"]
    if news_data.get("status") not in ("unavailable", None):
        coverage += 12
        sources.append(news_data.get("source") or "Public news sources")
    positives.extend([f"positiv nyhetsdriver: {x}" for x in news["positive_headlines"][:2]])
    risks.extend([f"risikonyhet: {x}" for x in news["risk_headlines"][:2]])

    score = _clamp(score)
    coverage = _clamp(coverage)
    code, label, tone = _status(score, coverage, news["severe_risk_flag"])
    if news["severe_risk_flag"] and score > 58:
        score = 58.0
        code, label, tone = _status(score, coverage, True)

    return {
        "symbol": market_symbol,
        "requested_symbol": requested,
        "ticker": tracked.get("ticker") if tracked else market_symbol,
        "name": name,
        "asset_class": asset_class,
        "exchange": snapshot.get("exchange"),
        "currency": snapshot.get("currency"),
        "price": snapshot.get("price"),
        "change_pct": snapshot.get("change_pct"),
        "readiness_score": round(score),
        "readiness_code": code,
        "readiness_label": label,
        "tone": tone,
        "coverage_pct": round(coverage),
        "brief": _brief(name, label, score, positives, risks, news),
        "positive_factors": positives[:6],
        "risk_factors": risks[:6],
        "news_assessment": news,
        "news_items": (news_data.get("items") or [])[:8],
        "analytics": {
            key: analytics.get(key) for key in (
                "return_1m_pct", "return_3m_pct", "return_1y_pct", "volatility_1y_pct",
                "max_drawdown_1y_pct", "above_sma_200", "sma_50", "sma_200"
            )
        },
        "stock_model": None if not tracked else {
            "score": tracked.get("total"), "fundamentals": tracked.get("fundamentals"),
            "valuation": tracked.get("valuation"), "sentiment": tracked.get("sentiment"),
            "insider": tracked.get("insider") if tracked.get("source") == "live" else None,
            "coverage": tracked.get("source"),
        },
        "short": short,
        "sources": list(dict.fromkeys(x for x in sources if x)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "classification": "informational_decision_support",
            "not_personal_advice": True,
            "note": "Readiness-status er en modellbasert informasjonsindikator, ikke en kjøps-, salgs- eller holdeanbefaling.",
        },
    }


def _cached_build(provider, regulatory, symbol, refresh=False):
    key = str(symbol or "").strip().upper()
    now = time.time()
    if not refresh:
        with _CACHE_LOCK:
            row = _CACHE.get(key)
            if row and now - row[0] < _CACHE_TTL:
                return row[1]
    payload = _build(provider, regulatory, key)
    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_MAX:
            oldest = min(_CACHE, key=lambda x: _CACHE[x][0])
            _CACHE.pop(oldest, None)
        _CACHE[key] = (now, payload)
    return payload


def install():
    if getattr(extra_api, "_investment_readiness_runtime_installed", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)
        provider = YahooProvider()
        regulatory = NordicRegulatoryProvider()

        @app.get("/api/readiness/{symbol}")
        def investment_readiness(symbol: str, refresh: bool = False):
            return _cached_build(provider, regulatory, symbol, refresh=refresh)

    extra_api.install = patched_install
    extra_api._investment_readiness_runtime_installed = True
