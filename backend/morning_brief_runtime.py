"""Pre-market Morning Brief for NordicSignal.

Combines the existing official Euronext financial calendar, verified event radar and
market-news feed with cached global-market snapshots. This is informational/event-risk
context only; it never changes NordicSignal scores, Opportunity rules or thresholds.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import threading
import time

import extra_api
import event_radar_runtime
import general_news_runtime
import market_calendar_runtime
from providers import YahooProvider

OSLO = ZoneInfo("Europe/Oslo")
_CACHE_TTL = 300
_CACHE_LOCK = threading.Lock()
_CACHE = {"at": 0.0, "value": None}

MARKETS = (
    ("Brent", "BZ=F", "Energi"),
    ("WTI", "CL=F", "Energi"),
    ("S&P 500", "^GSPC", "USA"),
    ("Nasdaq", "^IXIC", "USA"),
    ("Euro Stoxx 50", "^STOXX50E", "Europa"),
    ("USD/NOK", "NOK=X", "Valuta"),
)


def _previous_oslo_close(now=None):
    local = (now or datetime.now(timezone.utc)).astimezone(OSLO)
    day = local.date()
    close_today = datetime.combine(day, datetime.min.time(), OSLO).replace(hour=16, minute=20)
    if local <= close_today:
        day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return datetime.combine(day, datetime.min.time(), OSLO).replace(hour=16, minute=20)


def _parse_time(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _market_row(provider, label, symbol, group):
    data = provider._get(
        f"{provider.BASE}/v8/finance/chart/{symbol}",
        {"range": "5d", "interval": "1d", "includePrePost": "true"},
    )
    result = ((data.get("chart") or {}).get("result") or [None])[0] or {}
    meta = result.get("meta") or {}
    price = meta.get("regularMarketPrice")
    previous = meta.get("previousClose") or meta.get("chartPreviousClose")
    change = ((float(price) - float(previous)) / float(previous) * 100.0) if price is not None and previous else None
    return {
        "label": label,
        "symbol": symbol,
        "group": group,
        "price": price,
        "previous_close": previous,
        "change_pct": change,
        "currency": meta.get("currency"),
        "source": "Yahoo Finance",
        "status": "live" if price is not None else "unavailable",
    }


def _market_snapshot(provider):
    rows, errors = [], []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_market_row, provider, *item): item for item in MARKETS}
        for future in as_completed(futures):
            label, symbol, group = futures[future]
            try:
                rows.append(future.result())
            except Exception as exc:
                errors.append(f"{label}: {exc}")
                rows.append({"label": label, "symbol": symbol, "group": group, "change_pct": None, "status": "unavailable"})
    order = {item[0]: i for i, item in enumerate(MARKETS)}
    rows.sort(key=lambda x: order.get(x.get("label"), 99))
    return rows, errors


def _risk(event):
    days = int(event.get("days_until") or 0)
    kind = event.get("event_type")
    if kind == "report" and days <= 1:
        return "critical"
    if kind == "report" and days <= 3:
        return "high"
    if kind in ("report", "meeting") and days <= 7:
        return "watch"
    if kind == "dividend" and days <= 3:
        return "watch"
    return "normal"


def _event_sort_key(item):
    risk_rank = {"critical": 0, "high": 1, "watch": 2, "normal": 3}
    return (risk_rank.get(item.get("risk"), 9), int(item.get("days_until") or 0), 0 if item.get("tracked") else 1, item.get("ticker") or item.get("company") or "")


def _radar_risk(priority):
    return "high" if priority == "high" else "watch" if priority == "watch" else "normal"


def _must_know_sort(item):
    rank = {"critical": 0, "high": 1, "watch": 2, "normal": 3}
    source_rank = 0 if item.get("source_context") == "calendar" else 1
    return (rank.get(item.get("risk"), 9), source_rank, int(item.get("days_until") or 99))


def build_morning_brief(days=7, news_limit=12, now=None, provider=None, force=False):
    days = max(1, min(int(days or 7), 30))
    news_limit = max(1, min(int(news_limit or 12), 30))
    current = now or datetime.now(timezone.utc)
    cache_key_ok = days == 7 and news_limit == 12 and now is None
    with _CACHE_LOCK:
        if cache_key_ok and not force and _CACHE["value"] is not None and time.time() - _CACHE["at"] < _CACHE_TTL:
            return dict(_CACHE["value"])

    provider = provider or YahooProvider()
    calendar = market_calendar_runtime.build_calendar(days=days, limit=160, holdings_only=False, today=current.astimezone(OSLO).date())
    events = []
    for raw in calendar.get("items") or []:
        item = dict(raw)
        item["risk"] = _risk(item)
        events.append(item)
    events.sort(key=_event_sort_key)

    close = _previous_oslo_close(current)
    market_news = general_news_runtime.general_market_news(provider=provider, limit=40)
    overnight_news = []
    radar_events = []
    for raw in market_news.get("items") or []:
        published = _parse_time(raw.get("published_at"))
        if not published or published.astimezone(OSLO) < close:
            continue
        item = dict(raw)
        overnight_news.append(item)
        if item.get("official") and item.get("source_type") == "exchange":
            radar = event_radar_runtime._event(item)
            if radar:
                radar["risk"] = _radar_risk(radar.get("priority"))
                radar["source_context"] = "radar"
                radar_events.append(radar)
    overnight_news = overnight_news[:news_limit]
    radar_events.sort(key=lambda x: str(x.get("published_at") or ""), reverse=True)
    radar_rank = {"high": 0, "watch": 1, "normal": 2}
    radar_events.sort(key=lambda x: radar_rank.get(x.get("priority"), 9))

    markets, market_errors = _market_snapshot(provider)
    notable_markets = [x for x in markets if isinstance(x.get("change_pct"), (int, float)) and abs(x["change_pct"]) >= 1.0]
    urgent_events = [x for x in events if x.get("risk") in ("critical", "high")]
    tracked_upcoming = [x for x in events if x.get("tracked")][:12]

    calendar_must = [dict(x, source_context="calendar") for x in urgent_events]
    radar_must = [x for x in radar_events if x.get("risk") in ("high", "watch")]
    must_know = (calendar_must + radar_must)[:16]
    must_know.sort(key=_must_know_sort)
    must_know = must_know[:10]

    bullets = []
    if urgent_events:
        bullets.append(f"{len(urgent_events)} rapport-/eventrisikoer de neste 3 dagene")
    if radar_events:
        bullets.append(f"{len(radar_events)} verifiserte Radar-hendelser siden forrige Oslo-close")
    elif overnight_news:
        bullets.append(f"{len(overnight_news)} nye markedsmeldinger siden forrige Oslo-close")
    if notable_markets:
        labels = ", ".join(x["label"] for x in notable_markets[:3])
        bullets.append(f"Uvanlig bevegelse i {labels}")
    if not bullets:
        bullets.append("Ingen tydelig høy event-risiko registrert akkurat nå")

    value = {
        "status": "live" if calendar.get("status") != "partial" else "partial",
        "market": "Oslo Børs",
        "title": "Før børs",
        "as_of": current.isoformat(),
        "previous_oslo_close": close.isoformat(),
        "summary": bullets,
        "must_know": must_know,
        "radar_events": radar_events[:12],
        "upcoming": tracked_upcoming,
        "calendar": events[:30],
        "overnight_news": overnight_news,
        "markets": markets,
        "notable_markets": notable_markets,
        "sources": {
            "calendar": calendar.get("source"),
            "radar": "Verified Euronext / Oslo Børs announcements",
            "news": market_news.get("source"),
            "markets": "Yahoo Finance chart snapshots",
        },
        "errors": list(calendar.get("errors") or []) + market_errors,
        "policy": "Event-risk context only. Does not change NordicSignal scores, signals or thresholds.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    with _CACHE_LOCK:
        if cache_key_ok:
            _CACHE.update({"at": time.time(), "value": value})
    return dict(value)


def install():
    if getattr(extra_api, "_morning_brief_runtime_v1", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)

        @app.get("/api/morning-brief")
        def morning_brief(days: int = 7, news_limit: int = 12, refresh: bool = False):
            return build_morning_brief(days=days, news_limit=news_limit, force=refresh)

    extra_api.install = patched_install
    extra_api._morning_brief_runtime_v1 = True


install()
