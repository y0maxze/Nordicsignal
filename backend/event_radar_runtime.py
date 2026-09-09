"""Verified Oslo Børs event radar for NordicSignal.

Classifies existing Euronext / Oslo Børs announcements into decision-useful event
families. Classification is informational only and never changes scores, signals or
Opportunity thresholds. Official exchange announcements are preferred; media items
are not promoted into the radar.
"""
from datetime import datetime, timezone
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


def _classify(item):
    text = news_runtime._norm(" ".join(str(item.get(k) or "") for k in ("title", "topic", "summary")))
    for kind, label, priority, terms in _RULES:
        if any(news_runtime._norm(term) in text for term in terms):
            return kind, label, priority
    return None


def _event(item):
    classified = _classify(item)
    if not classified:
        return None
    kind, label, priority = classified
    out = dict(item)
    out.update({
        "event_type": kind,
        "event_label": label,
        "priority": priority,
        "verified": bool(item.get("official")),
        "source": "Euronext / Oslo Børs",
    })
    return out


def build_event_radar(limit=40, ticker=None, force=False, provider=None):
    limit = max(1, min(int(limit or 40), 100))
    now = time.time()

    # Keep the lock scoped strictly to cache state. Provider/network work must happen
    # outside the lock, otherwise a cache miss can deadlock or block every reader.
    with _CACHE_LOCK:
        cached = _CACHE.get("items")
        cache_is_fresh = cached is not None and not force and now - _CACHE["at"] < _CACHE_TTL
        items = list(cached) if cache_is_fresh else None

    if items is None:
        feed = general_news_runtime.general_market_news(provider=provider or YahooProvider(), limit=50)
        items = []
        for raw in feed.get("items") or []:
            # Radar claims require the official exchange source. Media remains news.
            if not raw.get("official") or raw.get("source_type") != "exchange":
                continue
            event = _event(raw)
            if event:
                items.append(event)
        rank = {"high": 0, "watch": 1, "normal": 2}
        items.sort(key=lambda x: (rank.get(x.get("priority"), 9), str(x.get("published_at") or "")))
        with _CACHE_LOCK:
            _CACHE.update({"at": now, "items": list(items)})

    wanted = str(ticker or "").upper().strip()
    if wanted:
        items = [x for x in items if str(x.get("ticker") or "").upper() == wanted]
    return {
        "status": "live" if items else "no_matches",
        "ticker": wanted or None,
        "items": items[:limit],
        "count": min(len(items), limit),
        "source": "Euronext / Oslo Børs",
        "policy": "Verified event context only. Does not change NordicSignal scores, signals or thresholds.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def install():
    if getattr(extra_api, "_event_radar_runtime_v1", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)

        @app.get("/api/event-radar")
        def event_radar(limit: int = 40, ticker: str = "", refresh: bool = False):
            return build_event_radar(limit=limit, ticker=ticker, force=refresh)

    extra_api.install = patched_install
    extra_api._event_radar_runtime_v1 = True


install()
