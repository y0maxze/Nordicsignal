"""Fresh, normalized fallback for recent primary-insider disclosures.

Euronext remains the primary regulatory source. Some issuer/Euronext pages are
rendered or cached in ways that can lag the latest release, so an issuer-scoped
GlobeNewswire fallback is merged afterwards. Every returned trade still has to be
parsed from a real issuer release and pass issuer + primary-insider checks.

GlobeNewswire release pages also contain navigation and Recommended Reading cards.
Those can repeat transactions from adjacent releases. This layer therefore cleans
actor names, rejects impossible future trade dates relative to a release URL and
collapses language/feed duplicates into one economic transaction.
"""

from collections import OrderedDict
from datetime import datetime, timezone
import re
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


FRESH_ISSUER_FEEDS = {
    "LSG": (
        # The normal organisation page currently exposes the full recent release
        # set and is the cleanest fallback for several days of transactions.
        "https://www.globenewswire.com/en/search/organization/Ler%C3%B8y%2520Seafood%2520Group%2520ASA?page=1",
        # The category load-more view is an independent path for the newest release.
        "https://rss.globenewswire.com/news/consumer-products-services/food-beverage/load/more?page=1&pageSize=50",
    ),
}

_CACHE_TTL = 60
_CACHE_MAX = 16
_CACHE = OrderedDict()
_LOCK = threading.RLock()

_NOISE_PREFIX = re.compile(
    r"\b(?:primary\s+insider\s+transactions?|"
    r"prim(?:æ|ae)rinsidetransaksjoner?|"
    r"mandatory\s+notification\s+of\s+trade(?:\s+by\s+primary\s+insider)?|"
    r"notification\s+of\s+trade\s+by\s+primary\s+insider)\b[:\s\-–—]*",
    re.I,
)
_RELEASE_DATE = re.compile(r"/news-release/(20\d{2})/(\d{1,2})/(\d{1,2})/")


def _issuer_terms(ticker):
    name, aliases = ISSUERS.get(ticker, (ticker, ()))
    return tuple(norm(x) for x in (name, *aliases, ticker) if x)


def _url_mentions_issuer(url, ticker):
    hay = norm(unquote(str(url or "")))
    return any(term and term in hay for term in _issuer_terms(ticker))


def discover_release_links(html, base_url, ticker):
    """Find issuer release links from an organisation or mixed fresh-news page."""
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
        priority = 0 if _is_insider_label(label) else 1
        seen.add(canonical)
        out.append((priority, full, label))
    out.sort(key=lambda x: x[0])
    return [(url, label) for _, url, label in out]


def _release_date_from_url(url):
    match = _RELEASE_DATE.search(str(url or ""))
    if not match:
        return None
    try:
        return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3))).date()
    except ValueError:
        return None


def _trade_date(row):
    raw = row.get("trade_date") or row.get("date")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw)[:10]).date()
    except (TypeError, ValueError):
        return None


def _clean_actor(value, ticker):
    """Remove page/title boilerplate without inventing a new identity."""
    text = " ".join(str(value or "").split()).strip(" ,:;-–—")
    if not text:
        return None
    issuer_name = ISSUERS.get(ticker, (ticker, ()))[0]
    if issuer_name:
        text = re.sub(re.escape(issuer_name), " ", text, flags=re.I)
    text = _NOISE_PREFIX.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" ,:;-–—")
    return text or None


def _sanitize_row(row, ticker):
    item = dict(row or {})
    person = _clean_actor(item.get("person"), ticker)
    entity = _clean_actor(item.get("entity"), ticker)
    insider = _clean_actor(item.get("insider"), ticker)

    if person:
        item["person"] = person
        item["entity"] = None
        item["insider"] = person
        item["actor_type"] = "person"
    elif entity:
        item["person"] = None
        item["entity"] = entity
        item["insider"] = entity
        item["actor_type"] = "company"
    elif insider:
        item["insider"] = insider

    # A Recommended Reading card from a newer release may be present in an older
    # article page. A transaction cannot occur after the article's own publish date,
    # so such a row is safely identifiable as page noise.
    published = _release_date_from_url(item.get("url"))
    traded = _trade_date(item)
    if published and traded and traded > published:
        return None
    return item


def _economic_key(row):
    actor = norm(row.get("person") or row.get("entity") or row.get("insider"))
    direction = row.get("direction") or row.get("transaction_type") or "unknown"
    date = row.get("trade_date") or row.get("date")
    shares = row.get("shares")
    if actor or shares is not None:
        return (date, direction, shares, actor)
    return (canonical_url(row.get("url") or ""), norm(row.get("title")))


def _row_quality(row):
    """Prefer the release closest to the actual trade and richer structured data."""
    score = 0
    actor = row.get("person") or row.get("entity") or row.get("insider")
    if actor:
        score += 20
    if row.get("role"):
        score += 8
    if row.get("shares") is not None:
        score += 12
    if row.get("price") is not None:
        score += 6
    if row.get("verified_detail"):
        score += 5

    published = _release_date_from_url(row.get("url"))
    traded = _trade_date(row)
    if published and traded and published >= traded:
        lag = (published - traded).days
        score += max(0, 20 - min(lag, 20))
    if "recommended reading" not in str(row.get("summary") or "").lower():
        score += 4
    return score


def normalize_items(rows, ticker):
    """Return one clean row per disclosed economic transaction."""
    dedup = {}
    for raw in rows or []:
        row = _sanitize_row(raw, ticker)
        if not row:
            continue
        key = _economic_key(row)
        current = dedup.get(key)
        if current is None or _row_quality(row) > _row_quality(current):
            dedup[key] = row
    return sorted(
        dedup.values(),
        key=lambda x: x.get("trade_date") or x.get("date") or "",
        reverse=True,
    )[:12]


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
    # Never pin an empty upstream result. A temporary CDN/provider stale page should
    # be retried on the next request rather than becoming a false "no activity" state.
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
            for row in parse_trades(
                body,
                ticker,
                label or "Primary insider transaction",
                "GlobeNewswire fresh issuer feed",
                url,
            ):
                enriched = enrich_item(row, ticker)
                if enriched.get("verified_detail"):
                    items.append(enriched)

    result = normalize_items(items, ticker)
    _cache_put(ticker, result)
    return result


def merge_insider_result(base, fresh, ticker):
    out = dict(base or {})
    fresh_normalized = normalize_items(fresh, ticker)
    items = normalize_items(
        [dict(x) for x in (out.get("items") or [])] + [dict(x) for x in fresh_normalized],
        ticker,
    )
    out["ticker"] = ticker
    out["items"] = items
    out["buy_count"] = sum((x.get("direction") or x.get("transaction_type")) == "buy" for x in items)
    out["sell_count"] = sum((x.get("direction") or x.get("transaction_type")) == "sell" for x in items)
    out["unknown_count"] = len(items) - out["buy_count"] - out["sell_count"]
    out["verified_detail_count"] = sum(bool(x.get("verified_detail")) for x in items)
    out["fresh_fallback_supported"] = ticker in FRESH_ISSUER_FEEDS
    out["fresh_fallback_checked_at"] = datetime.now(timezone.utc).isoformat()
    out["fresh_fallback_count"] = len(fresh_normalized)
    out["insider_runtime_version"] = "2026-08-27-v3"

    if fresh_normalized:
        out["status"] = "live"
        out["signal"] = (
            "buying" if out["buy_count"] > out["sell_count"]
            else "selling" if out["sell_count"] > out["buy_count"]
            else "activity"
        )
        current_source = str(out.get("source") or "Euronext Oslo Børs Newspoint")
        if "GlobeNewswire fresh issuer feed" not in current_source:
            out["source"] = current_source + " + GlobeNewswire fresh issuer feed"
    elif items and out["verified_detail_count"]:
        out["status"] = "live"
    return out


def install():
    if getattr(NordicRegulatoryProvider, "_fresh_insider_fallback_v3", False):
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
    NordicRegulatoryProvider._fresh_insider_fallback_v3 = True


install()
