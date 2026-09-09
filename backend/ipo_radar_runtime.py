"""IPO / new-listing radar for NordicSignal.

The radar detects verified Oslo Børs / Euronext announcements about upcoming
listings and offering terms. It is deliberately separate from the stock score:
pre-listing companies do not have enough comparable market history for the normal
NordicSignal model.
"""
from datetime import datetime, timezone
import re
import threading
import time

import extra_api
import general_news_runtime
from providers import YahooProvider

_CACHE_LOCK = threading.Lock()
_CACHE = {"at": 0.0, "value": None}
_CACHE_TTL = 300

_UPCOMING_TERMS = (
    "initial public offering", "ipo", "intention to float", "intention to list",
    "planned listing", "expected to be admitted", "expected listing", "listing on",
    "admission to trading", "commence trading", "offering terms", "terms for the",
)
_LISTING_TERMS = (
    "euronext oslo børs", "euronext oslo bors", "oslo børs", "oslo bors",
    "euronext growth oslo", "euronext growth",
)
_EXCLUDE_TERMS = ("delisting", "de-listing", "suspension", "termination of listing")


def _norm(value):
    return " ".join(str(value or "").lower().split())


def _is_listing_announcement(item):
    if not item.get("official") or item.get("source_type") != "exchange":
        return False
    text = _norm(" ".join([item.get("title") or "", item.get("topic") or "", item.get("summary") or ""]))
    if any(term in text for term in _EXCLUDE_TERMS):
        return False
    return any(term in text for term in _UPCOMING_TERMS) and any(term in text for term in _LISTING_TERMS)


def _listing_type(text):
    text = _norm(text)
    if "spin-off" in text or "demerger" in text:
        return "spin_off"
    if "direct listing" in text:
        return "direct_listing"
    if "transfer" in text:
        return "transfer"
    if "private placement" in text:
        return "private_placement"
    return "ipo"


def _market(text):
    text = _norm(text)
    if "euronext growth" in text:
        return "Euronext Growth Oslo"
    if "oslo børs" in text or "oslo bors" in text or "euronext oslo børs" in text:
        return "Euronext Oslo Børs"
    return "Oslo market"


def _extract_offer_price(text):
    text = str(text or "")
    match = re.search(r"(?:offer(?:ing)? price|fixed price|price)\s*(?:of|at|:)??\s*(?:nok|nkr|kr)\s*([0-9]+(?:[.,][0-9]+)?)", text, re.I)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def _extract_expected_date(text):
    text = str(text or "")
    # Keep the raw announced date rather than guessing timezone/trading status.
    match = re.search(r"(?:commence trading|listing|admitted to (?:listing|trading))[^.]{0,100}?(?:on or about|on|around)\s+([0-3]?\d\s+[A-Za-z]+\s+20\d{2})", text, re.I)
    return match.group(1) if match else None


def classify_listing(item):
    if not _is_listing_announcement(item):
        return None
    text = " ".join([item.get("title") or "", item.get("topic") or "", item.get("summary") or ""])
    ticker = str(item.get("ticker") or "").upper().replace(".OL", "") or None
    return {
        "company": item.get("company"),
        "ticker": ticker,
        "listing_type": _listing_type(text),
        "market": _market(text),
        "expected_listing_date_text": _extract_expected_date(text),
        "offer_price_nok": _extract_offer_price(text),
        "title": item.get("title"),
        "published_at": item.get("published_at"),
        "source_url": item.get("url"),
        "source": "Euronext / Oslo Børs",
        "official": True,
        "status": "watch",
        "data_coverage": "announcement_only",
        "assessment": "Utilstrekkelig data for investeringsvurdering",
    }


def build_ipo_radar(provider=None, limit=20, force=False):
    now = time.time()
    with _CACHE_LOCK:
        if not force and _CACHE["value"] is not None and now - _CACHE["at"] < _CACHE_TTL:
            return dict(_CACHE["value"])

    provider = provider or YahooProvider()
    feed = general_news_runtime.general_market_news(provider=provider, limit=50)
    items = []
    seen = set()
    for raw in feed.get("items") or []:
        listing = classify_listing(raw)
        if not listing:
            continue
        identity = str(listing.get("source_url") or listing.get("title") or "")
        if identity in seen:
            continue
        seen.add(identity)
        items.append(listing)
        if len(items) >= max(1, min(int(limit or 20), 50)):
            break
    items.sort(key=lambda x: str(x.get("published_at") or ""), reverse=True)
    value = {
        "status": "ok" if items else "no_verified_upcoming_listings",
        "market": "Oslo",
        "items": items,
        "count": len(items),
        "source": "Verified Euronext / Oslo Børs announcements",
        "policy": "Discovery and verified listing context only. IPO Radar does not change NordicSignal scores, signals or thresholds.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    with _CACHE_LOCK:
        _CACHE.update({"at": now, "value": value})
    return dict(value)


def install():
    if getattr(extra_api, "_ipo_radar_runtime_v1", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)
        provider = YahooProvider()

        @app.get("/api/ipo-radar")
        def ipo_radar(limit: int = 20, refresh: bool = False):
            return build_ipo_radar(provider=provider, limit=limit, force=refresh)

    extra_api.install = patched_install
    extra_api._ipo_radar_runtime_v1 = True


install()
