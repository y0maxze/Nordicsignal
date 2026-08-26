"""Dedicated history-based signal engine for funds and ETFs.

This model is intentionally separate from the Oslo equity model. It scores trend,
momentum and risk from each instrument's own price/NAV history, so a mutual fund or
ETF never inherits stock fundamentals, insider or valuation points that do not apply.
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import BaseModel, Field

import extra_api
from database import connect
from instrument_analytics_runtime import instrument_analytics
from providers import YahooProvider

CACHE_SECONDS = 15 * 60
SUPPORTED = {"Fond", "ETF"}
SEEDS = (
    ("OP0001OPBLIR", "KLP AksjeGlobal Indeks N", "MUTUALFUND", "Fond", "Irish", "NOK"),
    ("VOO", "Vanguard S&P 500 ETF", "ETF", "ETF", "NYSEArca", "USD"),
    ("VTI", "Vanguard Total Stock Market ETF", "ETF", "ETF", "NYSEArca", "USD"),
    ("VT", "Vanguard Total World Stock ETF", "ETF", "ETF", "NYSEArca", "USD"),
    ("QQQ", "Invesco QQQ Trust", "ETF", "ETF", "Nasdaq", "USD"),
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _ensure_schema():
    conn = connect()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS signal_instrument_catalog (
          symbol TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          quote_type TEXT,
          asset_class TEXT NOT NULL,
          exchange TEXT,
          currency TEXT,
          last_seen_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS instrument_signal_cache (
          symbol TEXT PRIMARY KEY,
          payload TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        """)
        for symbol, name, quote_type, asset_class, exchange, currency in SEEDS:
            row = conn.execute("SELECT symbol FROM signal_instrument_catalog WHERE symbol=?", (symbol,)).fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO signal_instrument_catalog(symbol,name,quote_type,asset_class,exchange,currency,last_seen_at) VALUES(?,?,?,?,?,?,?)",
                    (symbol, name, quote_type, asset_class, exchange, currency, _now()),
                )
        conn.commit()
    finally:
        conn.close()


class CatalogInstrument(BaseModel):
    symbol: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=180)
    quote_type: str | None = Field(default=None, max_length=40)
    asset_class: str = Field(min_length=1, max_length=40)
    exchange: str | None = Field(default=None, max_length=100)
    currency: str | None = Field(default=None, max_length=12)


def _clamp(v, low=0.0, high=100.0):
    return max(low, min(high, float(v)))


def _scaled(value, bad, good, points):
    if value is None:
        return None
    if good == bad:
        return 0.0
    return _clamp((float(value) - bad) / (good - bad), 0.0, 1.0) * points


def score_analytics(analytics, asset_class="Fond"):
    """Return a transparent 0-100 signal from history-derived analytics.

    Weights: trend 40, momentum 20, risk 25, long-term consistency 15.
    Missing inputs reduce coverage instead of silently receiving neutral points.
    """
    a = analytics or {}
    parts = []

    # Trend: recent and annual performance plus position versus 200-day average.
    parts.append(("1m trend", _scaled(a.get("return_1m_pct"), -6, 6, 10), 10))
    parts.append(("3m trend", _scaled(a.get("return_3m_pct"), -12, 18, 12), 12))
    parts.append(("1y trend", _scaled(a.get("return_1y_pct"), -25, 30, 13), 13))
    above200 = a.get("above_sma_200")
    parts.append(("200d trend", 5.0 if above200 is True else 0.0 if above200 is False else None, 5))

    # Momentum: YTD plus price position relative to 50-day average.
    parts.append(("YTD momentum", _scaled(a.get("return_ytd_pct"), -20, 25, 12), 12))
    cur, sma50 = a.get("current"), a.get("sma_50")
    if cur is None or sma50 in (None, 0):
        above50_points = None
    else:
        delta = (float(cur) / float(sma50) - 1.0) * 100.0
        above50_points = _scaled(delta, -8, 8, 8)
    parts.append(("50d momentum", above50_points, 8))

    # Risk: lower volatility and shallower drawdowns are rewarded.
    vol = a.get("volatility_1y_pct")
    vol_points = None if vol is None else _clamp((45.0 - float(vol)) / 35.0, 0, 1) * 13
    dd = a.get("max_drawdown_1y_pct")
    dd_points = None if dd is None else _clamp((float(dd) + 50.0) / 42.0, 0, 1) * 12
    parts.append(("volatility", vol_points, 13))
    parts.append(("drawdown", dd_points, 12))

    # Long-term consistency. A long history is useful, but absence must not fabricate points.
    parts.append(("3y CAGR", _scaled(a.get("cagr_3y_pct"), -8, 15, 8), 8))
    parts.append(("5y CAGR", _scaled(a.get("cagr_5y_pct"), -5, 12, 7), 7))

    available_max = sum(max_points for _, value, max_points in parts if value is not None)
    earned = sum(float(value) for _, value, _ in parts if value is not None)
    coverage = available_max
    score = round((earned / available_max * 100.0) if available_max else 50.0)
    score = int(_clamp(score))

    # Sparse data is not allowed to produce a high-conviction signal.
    if coverage < 60 and score >= 72:
        score = 71
    if coverage < 40:
        signal, strength = "Watch", "watch"
    elif score >= 72:
        signal, strength = "Strong", "strong"
    elif score >= 52:
        signal, strength = "Watch", "watch"
    else:
        signal, strength = "Risk", "risk"

    label = "fond" if asset_class == "Fond" else "ETF"
    event = (
        f"Positiv {label}trend" if signal == "Strong" else
        f"Blandet {label}trend" if signal == "Watch" else
        f"Svak {label}trend"
    )
    return {
        "score": score,
        "signal": signal,
        "strength": strength,
        "event": event,
        "coverage_pct": round(coverage, 1),
        "components": {
            name: {"points": None if value is None else round(float(value), 2), "max": max_points}
            for name, value, max_points in parts
        },
        "model": "history_trend_risk_v1",
        "model_note": "Fond/ETF-modell basert på historisk trend, momentum, volatilitet og drawdown; ikke aksjefundamentaler.",
    }


def _catalog_rows(asset_class=None, limit=20):
    limit = max(1, min(int(limit or 20), 50))
    conn = connect()
    try:
        if asset_class in SUPPORTED:
            rows = conn.execute(
                "SELECT * FROM signal_instrument_catalog WHERE asset_class=? ORDER BY last_seen_at DESC,name LIMIT ?",
                (asset_class, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM signal_instrument_catalog WHERE asset_class IN ('Fond','ETF') ORDER BY last_seen_at DESC,name LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(x) for x in rows]
    finally:
        conn.close()


def _parse_time(value):
    try:
        dt = datetime.fromisoformat(str(value))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _cache_get(symbol):
    import json
    conn = connect()
    try:
        row = conn.execute("SELECT payload,updated_at FROM instrument_signal_cache WHERE symbol=?", (symbol,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    updated = _parse_time(row["updated_at"])
    age = (datetime.now(timezone.utc) - updated).total_seconds() if updated else CACHE_SECONDS + 1
    if age > CACHE_SECONDS:
        return None
    try:
        return json.loads(row["payload"])
    except Exception:
        return None


def _cache_put(symbol, payload):
    import json
    conn = connect()
    try:
        existing = conn.execute("SELECT symbol FROM instrument_signal_cache WHERE symbol=?", (symbol,)).fetchone()
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if existing:
            conn.execute("UPDATE instrument_signal_cache SET payload=?,updated_at=? WHERE symbol=?", (encoded, _now(), symbol))
        else:
            conn.execute("INSERT INTO instrument_signal_cache(symbol,payload,updated_at) VALUES(?,?,?)", (symbol, encoded, _now()))
        conn.commit()
    finally:
        conn.close()


def _build_signal(provider, meta, refresh=False):
    symbol = meta["symbol"]
    if not refresh:
        cached = _cache_get(symbol)
        if cached:
            return cached
    analytics = instrument_analytics(provider, symbol)
    scored = score_analytics(analytics, meta.get("asset_class") or "Fond")
    payload = {
        "ticker": symbol,
        "symbol": symbol,
        "name": meta.get("name") or symbol,
        "quote_type": meta.get("quote_type"),
        "asset_class": meta.get("asset_class"),
        "exchange": meta.get("exchange"),
        "currency": meta.get("currency"),
        **scored,
        "analytics": analytics,
        "score_source": "history_model",
        "live_verified": False,
        "partial_live": False,
        "updated_at": _now(),
    }
    _cache_put(symbol, payload)
    return payload


def register_catalog(payload):
    asset_class = str(payload.asset_class or "").strip()
    if asset_class not in SUPPORTED:
        return {"status": "ignored", "reason": "Only funds and ETFs use this catalog"}
    symbol = payload.symbol.strip().upper()
    conn = connect()
    try:
        row = conn.execute("SELECT symbol FROM signal_instrument_catalog WHERE symbol=?", (symbol,)).fetchone()
        values = (
            payload.name.strip(),
            (payload.quote_type or "").strip().upper() or None,
            asset_class,
            (payload.exchange or "").strip() or None,
            (payload.currency or "").strip().upper() or None,
            _now(),
            symbol,
        )
        if row:
            conn.execute(
                "UPDATE signal_instrument_catalog SET name=?,quote_type=?,asset_class=?,exchange=?,currency=?,last_seen_at=? WHERE symbol=?",
                values,
            )
        else:
            conn.execute(
                "INSERT INTO signal_instrument_catalog(name,quote_type,asset_class,exchange,currency,last_seen_at,symbol) VALUES(?,?,?,?,?,?,?)",
                values,
            )
        conn.commit()
    finally:
        conn.close()
    return {"status": "ok", "symbol": symbol, "asset_class": asset_class}


def install():
    if getattr(extra_api, "_instrument_signal_runtime_installed", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)
        _ensure_schema()
        provider = YahooProvider()

        @app.post("/api/instrument-signals/register")
        def register_instrument_signal(payload: CatalogInstrument):
            return register_catalog(payload)

        @app.get("/api/instrument-signals")
        def instrument_signals(asset_class: str = "Fond", limit: int = 20, refresh: bool = False):
            requested = str(asset_class or "").strip()
            if requested not in SUPPORTED and requested not in ("Alle", ""):
                raise HTTPException(400, detail="asset_class must be Fond, ETF or Alle")
            rows = _catalog_rows(None if requested in ("Alle", "") else requested, limit)
            items, errors = [], []
            for meta in rows:
                try:
                    items.append(_build_signal(provider, meta, refresh=refresh))
                except Exception as exc:
                    errors.append({"symbol": meta.get("symbol"), "name": meta.get("name"), "error": str(exc)})
            items.sort(key=lambda x: (-int(x.get("score") or 0), str(x.get("name") or "")))
            return {
                "asset_class": requested or "Alle",
                "items": items,
                "errors": errors,
                "model": "history_trend_risk_v1",
                "source": "Yahoo Finance price/NAV history",
                "updated_at": _now(),
            }

    extra_api.install = patched_install
    extra_api._instrument_signal_runtime_installed = True
