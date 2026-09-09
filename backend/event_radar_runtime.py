"""Verified Oslo Børs event radar for NordicSignal.

Classifies existing Euronext / Oslo Børs announcements into decision-useful event
families. Classification and materiality are informational only and never change
scores, signals or Opportunity thresholds.
"""
from datetime import datetime, timezone
import re
import threading
import time

import extra_api
import general_news_runtime
import news_runtime
from providers import YahooProvider

_CACHE = {"at": 0.0, "items": None}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 180

_RULES = (
    ("contract_lost", "Kontrakt tapt / avsluttet", "high", ("contract termination", "contract terminated", "terminated contract", "contract cancelled", "contract canceled", "lost contract", "avsluttet kontrakt", "terminert kontrakt", "mistet kontrakt")),
    ("profit_warning", "Resultatvarsel / guiding", "high", ("profit warning", "guidance update", "outlook update", "trading update", "resultatvarsel", "nedjusterer guiding", "oppjusterer guiding", "guiding")),
    ("acquisition", "Oppkjøp / fusjon", "high", ("acquisition", "acquires", "merger", "takeover", "oppkjop", "fusjon", "kjoper")),
    ("disposal", "Salg / avhendelse", "watch", ("divestment", "disposal", "sells subsidiary", "sale of", "avhendelse", "selger")),
    ("contract", "Kontrakt / ordre", "watch", ("contract award", "awarded contract", "new contract", "contract", "order intake", "purchase order", "order", "kontrakt", "ordre")),
    ("agreement", "Avtale / partnerskap", "watch", ("strategic agreement", "framework agreement", "partnership", "joint venture", "letter of intent", "memorandum of understanding", "agreement", "partnerskap", "rammeavtale", "intensjonsavtale", "avtale")),
    ("major_shareholding", "Storeier / flagging", "watch", ("major shareholding", "major shareholder", "notification of major holdings", "flagging", "flagged holding")),
    ("buyback", "Tilbakekjøp", "normal", ("share buyback", "buy-back", "repurchase of shares", "own shares", "tilbakekjop", "egne aksjer")),
)

_AMOUNT_RE = re.compile(r"\b(?:nok|nkr|kr)\s*([0-9]+(?:[.,][0-9]+)?)\s*(billion|million|bn|mn|mrd|mill(?:ioner)?)?\b|\b([0-9]+(?:[.,][0-9]+)?)\s*(billion|million|bn|mn|mrd|mill(?:ioner)?)\s*(?:nok|nkr|kr)\b", re.I)
_SCALE = {"billion": 1e9, "bn": 1e9, "mrd": 1e9, "million": 1e6, "mn": 1e6, "mill": 1e6, "millioner": 1e6}


def _classify(item):
    text = news_runtime._norm(" ".join(str(item.get(k) or "") for k in ("title", "topic", "summary")))
    for kind, label, priority, terms in _RULES:
        if any(news_runtime._norm(term) in text for term in terms):
            return kind, label, priority
    return None


def _extract_nok_amount(item):
    text = " ".join(str(item.get(k) or "") for k in ("title", "topic", "summary"))
    match = _AMOUNT_RE.search(text)
    if not match:
        return None
    number = match.group(1) or match.group(3)
    scale = (match.group(2) or match.group(4) or "").lower()
    try:
        return float(number.replace(",", ".")) * _SCALE.get(scale, 1.0)
    except (TypeError, ValueError):
        return None


def _latest_revenue(research):
    value = ((research or {}).get("financialData") or {}).get("totalRevenue")
    return float(value) if isinstance(value, (int, float)) and value > 0 else None


def _materiality(event, provider=None):
    """Attach evidence only when both announced NOK value and revenue are known.

    Labels are descriptive buckets, not predictions and never alter the canonical
    event priority. Missing/ambiguous evidence fails closed to ``unknown``.
    """
    amount = _extract_nok_amount(event)
    ticker = str(event.get("ticker") or "").upper().strip()
    result = {"status": "unknown", "announced_value_nok": amount, "revenue_nok": None, "revenue_ratio_pct": None, "label": "Ukjent materialitet"}
    if amount is None or not ticker or event.get("event_type") not in ("contract", "contract_lost", "acquisition", "disposal"):
        return result
    try:
        revenue = _latest_revenue((provider or YahooProvider()).research(ticker))
    except Exception:
        revenue = None
    if not revenue:
        return result
    ratio = amount / revenue * 100.0
    if ratio >= 25:
        label = "Svært stor relativt til omsetning"
    elif ratio >= 10:
        label = "Stor relativt til omsetning"
    elif ratio >= 3:
        label = "Merkbar relativt til omsetning"
    else:
        label = "Begrenset relativt til omsetning"
    return {"status": "measured", "announced_value_nok": amount, "revenue_nok": revenue, "revenue_ratio_pct": round(ratio, 2), "label": label}


def _event(item):
    classified = _classify(item)
    if not classified:
        return None
    kind, label, priority = classified
    out = dict(item)
    out.update({"event_type": kind, "event_label": label, "priority": priority, "verified": bool(item.get("official")), "source": "Euronext / Oslo Børs"})
    return out


def enrich_materiality(event, provider=None):
    out = dict(event)
    out["materiality"] = _materiality(out, provider=provider)
    return out


def build_event_radar(limit=40, ticker=None, force=False, provider=None):
    limit = max(1, min(int(limit or 40), 100)); now = time.time()
    with _CACHE_LOCK:
        cached = _CACHE.get("items")
        cache_is_fresh = cached is not None and not force and now - _CACHE["at"] < _CACHE_TTL
        items = list(cached) if cache_is_fresh else None
    if items is None:
        provider = provider or YahooProvider()
        feed = general_news_runtime.general_market_news(provider=provider, limit=50)
        items = []
        for raw in feed.get("items") or []:
            if not raw.get("official") or raw.get("source_type") != "exchange": continue
            event = _event(raw)
            if event: items.append(enrich_materiality(event, provider=provider))
        rank = {"high": 0, "watch": 1, "normal": 2}
        items.sort(key=lambda x: (rank.get(x.get("priority"), 9), str(x.get("published_at") or "")))
        with _CACHE_LOCK: _CACHE.update({"at": now, "items": list(items)})
    wanted = str(ticker or "").upper().strip()
    if wanted: items = [x for x in items if str(x.get("ticker") or "").upper() == wanted]
    return {"status": "live" if items else "no_matches", "ticker": wanted or None, "items": items[:limit], "count": min(len(items), limit), "source": "Euronext / Oslo Børs", "policy": "Verified event context and measured materiality only. Does not change NordicSignal scores, signals or thresholds.", "generated_at": datetime.now(timezone.utc).isoformat()}


def install():
    if getattr(extra_api, "_event_radar_runtime_v1", False): return
    original_install = extra_api.install
    def patched_install(app):
        original_install(app)
        @app.get("/api/event-radar")
        def event_radar(limit: int = 40, ticker: str = "", refresh: bool = False):
            return build_event_radar(limit=limit, ticker=ticker, force=refresh)
    extra_api.install = patched_install; extra_api._event_radar_runtime_v1 = True

install()
