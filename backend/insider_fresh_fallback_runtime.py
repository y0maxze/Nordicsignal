"""Fresh fallback for recent primary-insider disclosures.

Some issuer/Euronext archive pages are rendered or cached in ways that can lag the
latest regulated releases. Keep Euronext as the primary source, but merge a small,
issuer-scoped fresh publisher feed when available. The fallback never fabricates a
trade: every returned row must still be parsed from a real issuer release and pass
issuer + primary-insider checks.
"""

from collections import OrderedDict
from datetime import datetime, timezone
import threading
import time
from urllib.parse import unquote, urljoin

from curl_cffi import requests

from insider_runtime import (
    ISSUERS,
    PHRASES,
    _Parser,
    _is_insider_label,
    canonical_url,
    fetch,
    issuer_ok,
    norm,
    parse_trades,
)
from insider_enrichment_runtime import enrich_item
from providers import NordicRegulatoryProvider


# Use two independent GlobeNewswire views for Lerøy. The organisation-scoped feed is
# preferred because it is low-noise; the category feed is a second path if the search
# index is lagging. A minute cache-buster is added at request time because CDN copies
# of these pages can otherwise remain stale even while new releases already exist.
FRESH_ISSUER_FEEDS = {
    "LSG": (
        "https://rss.globenewswire.com/en/search/organization/Ler%C3%B8y%2520Seafood%2520Group%2520ASA/load/more?page=1&pageSize=50",
        "https://rss.globenewswire.com/news/consumer-products-services/food-beverage/load/more?page=1&pageSize=50",
    ),
}

_CACHE_TTL = 120
_CACHE_MAX = 16
_CACHE = OrderedDict()
_LOCK = threading.RLock()


def _issuer_terms(ticker):
    name, aliases = ISSUERS.get(ticker, (ticker, ()))
    return tuple(norm(x) for x in (name, *aliases, ticker) if x)


def _url_mentions_issuer(url, ticker):
    hay = norm(unquote(str(url or "")))
    return any(term and term in hay for term in _issuer_terms(ticker))


def discover_release_links(html, base_url, ticker):
    """Find issuer release links from a mixed fresh-news page."""
    parser = _Parser()
    parser.feed(html or "")
    out = []
    seen = set()
    terms = _issuer_terms(ticker)
    for href, label in parser.links:
        full = urljoin(base_url, href or "")
        if not href or "/news-release/" not in full:
            continue
        canonical = canonical_url(full)
        if canonical in seen:
            continue
        label_norm = norm(label)
        issuer_match = _url_mentions_issuer(full, ticker) or any(term and term in label_norm for term in terms)
        if not issuer_match:
            continue
        # Prefer insider-labelled releases, but retain issuer URLs because some
        # cards expose the headline outside the anchor. The detail page is verified
        # before it can become a returned event.
        priority = 0 if _is_insider_label(label) else 1
        seen.add(canonical)
        out.append((priority, full, label))
    out.sort(key=lambda x: x[0])
    return [(url, label) for _, url, label in out]


def _cache_get(ticker):
    now = time.monotonic()
    with _LOCK:
        row = _CACHE.get(ticker)
        if not row:
            return None
        expires, items = row
        if expires <= now:
            _CACHE.pop(ticker, None)
            return None
        _CACHE.move_to_end(ticker)
        return [dict(x) for x in items]


def _cache_put(ticker, items):
    # Never pin an empty upstream result. If a CDN/provider briefly serves a stale
    # page, the next request should be allowed to try again immediately.
    if not items:
        with _LOCK:
            _CACHE.pop(ticker, None)
        return
    with _LOCK:
        _CACHE[ticker] = (time.monotonic() + _CACHE_TTL, [dict(x) for x in items])
        _CACHE.move_to_end(ticker)
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)


def _fresh_items(session, ticker, company_name):
    cached = _cache_get(ticker)
    if cached is not None:
        return cached

    items = []
    seen_urls = set()
    cache_buster = int(time.time() // 60)
    for feed in FRESH_ISSUER_FEEDS.get(ticker, ()):
        try:
            html = fetch(session, feed, {"_ns": cache_buster})
        except Exception:
            continue
        for url, label in discover_release_links(html, feed, ticker)[:30]:
            canonical = canonical_url(url)
            if canonical in seen_urls:
                continue
            seen_urls.add(canonical)
            try:
                detail = fetch(session, url)
                parser = _Parser()
                parser.feed(detail)
                body = parser.text
            except Exception:
                continue
            low = norm(body)
            if not issuer_ok(body, ticker, company_name, label):
                continue
            if not any(norm(phrase) in low for phrase in PHRASES):
                continue
            for row in parse_trades(body, ticker, label or "Primary insider transaction", "GlobeNewswire fresh issuer feed", url):
                enriched = enrich_item(row, ticker)
                if enriched.get("verified_detail"):
                    items.append(enriched)

    dedup = {}
    for row in items:
        actor = norm(row.get("person") or row.get("entity") or row.get("insider"))
        key = (row.get("date"), row.get("direction"), row.get("shares"), actor, canonical_url(row.get("url") or ""))
        dedup.setdefault(key, row)
    result = sorted(dedup.values(), key=lambda x: x.get("date") or "", reverse=True)[:12]
    _cache_put(ticker, result)
    return result


def merge_insider_result(base, fresh, ticker):
    out = dict(base or {})
    rows = [dict(x) for x in (out.get("items") or [])] + [dict(x) for x in (fresh or [])]
    dedup = {}
    for row in rows:
        actor = norm(row.get("person") or row.get("entity") or row.get("insider"))
        if actor or row.get("shares") is not None:
            key = (row.get("date") or row.get("trade_date"), row.get("direction") or row.get("transaction_type"), row.get("shares"), actor)
        else:
            key = (canonical_url(row.get("url") or ""), norm(row.get("title")))
        if key not in dedup:
            dedup[key] = row
    items = sorted(dedup.values(), key=lambda x: x.get("date") or x.get("trade_date") or "", reverse=True)[:12]
    out["ticker"] = ticker
    out["items"] = items
    out["buy_count"] = sum((x.get("direction") or x.get("transaction_type")) == "buy" for x in items)
    out["sell_count"] = sum((x.get("direction") or x.get("transaction_type")) == "sell" for x in items)
    out["unknown_count"] = len(items) - out["buy_count"] - out["sell_count"]
    out["verified_detail_count"] = sum(bool(x.get("verified_detail")) for x in items)
    out["fresh_fallback_supported"] = ticker in FRESH_ISSUER_FEEDS
    out["fresh_fallback_checked_at"] = datetime.now(timezone.utc).isoformat()
    out["fresh_fallback_count"] = len(fresh or [])
    if fresh:
        out["status"] = "live"
        out["signal"] = "buying" if out["buy_count"] > out["sell_count"] else "selling" if out["sell_count"] > out["buy_count"] else "activity"
        current_source = str(out.get("source") or "Euronext Oslo Børs Newspoint")
        if "GlobeNewswire fresh issuer feed" not in current_source:
            out["source"] = current_source + " + GlobeNewswire fresh issuer feed"
    return out


def install():
    if getattr(NordicRegulatoryProvider, "_fresh_insider_fallback_v2", False):
        return
    original = NordicRegulatoryProvider.insider

    def insider(self, ticker, company_name=""):
        symbol = str(ticker or "").upper().strip()
        base = original(self, symbol, company_name)
        if symbol not in FRESH_ISSUER_FEEDS:
            return base
        name = company_name or ISSUERS.get(symbol, (symbol, ()))[0]
        session = getattr(self, "session", None) or requests.Session(impersonate="chrome")
        try:
            fresh = _fresh_items(session, symbol, name)
        except Exception:
            fresh = []
        return merge_insider_result(base, fresh, symbol)

    NordicRegulatoryProvider.insider = insider
    NordicRegulatoryProvider._fresh_insider_fallback_v2 = True


install()
