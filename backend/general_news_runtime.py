"""General market-news feed and cleanup for the public News page.

The stock-specific endpoint remains strict per issuer. This runtime adds a lightweight
/api/news market feed and removes generic investor-relations navigation links that
must never masquerade as fresh company news.
"""

from datetime import datetime, timezone
from urllib.parse import quote_plus, urljoin
import re
import threading
import time

import extra_api
import news_runtime
from providers import YahooProvider

_CACHE_LOCK = threading.Lock()
_CACHE = {"at": 0.0, "value": None}
_CACHE_TTL = 120

_GENERIC_IR_TITLES = {
    "annual reports",
    "annual report",
    "financial calendar",
    "reports and webcast",
    "reports webcast",
    "reports presentations",
    "reports and presentations",
    "stock exchange notices",
    "stock exchange announcements",
    "sustainability reports",
    "sustainability report",
    "webcast",
    "webcasts",
    "presentations",
    "financial reports",
    "quarterly reports",
    "investor relations",
}


def _is_generic_ir_navigation(item):
    if str(item.get("source_type") or "") != "issuer_ir":
        return False
    title = news_runtime._norm(item.get("title"))
    if title in _GENERIC_IR_TITLES:
        return True
    # Navigation labels are commonly short, undated category names. Actual report
    # headlines normally contain a year, quarter, result wording or a dated release.
    if item.get("published_at") is None and not re.search(r"\b(?:19|20)\d{2}\b|\bq[1-4]\b", title):
        generic_words = {
            "calendar", "reports", "report", "webcast", "webcasts", "presentations",
            "presentation", "notices", "announcements", "sustainability",
        }
        words = set(title.split())
        if words and words.issubset(generic_words | {"annual", "financial", "quarterly", "stock", "exchange", "and"}):
            return True
    return False


def _clean_company_news(data):
    result = dict(data or {})
    items = [dict(x) for x in (result.get("items") or []) if not _is_generic_ir_navigation(x)]
    result["items"] = items
    result["official_count"] = sum(1 for x in items if x.get("official"))
    result["media_count"] = sum(1 for x in items if not x.get("official"))
    return result


def _ticker_from_title(title):
    match = re.match(r"^\s*([A-Z0-9]{2,10})\s*:\s+", str(title or ""))
    return match.group(1) if match else None


def parse_general_euronext_html(html, limit=30):
    """Parse latest Oslo Børs company announcements without an issuer filter."""
    parser = news_runtime._RowLinkParser()
    parser.feed(html)
    items = []
    seen = set()
    for row_text, links in parser.rows:
        announcement = None
        for href, text in links:
            if "/products/equities/company-news/" in (href or "") and str(text or "").strip():
                announcement = (href, " ".join(str(text).split()).strip())
                break
        if not announcement:
            continue
        href, title = announcement
        url = urljoin("https://live.euronext.com", href)
        if url in seen:
            continue
        seen.add(url)
        items.append({
            "ticker": _ticker_from_title(title),
            "title": title,
            "publisher": "Euronext / Oslo Børs",
            "url": url,
            "published_at": news_runtime._parse_euronext_date(row_text),
            "category": news_runtime._category(title, row_text),
            "summary": title,
            "source_type": "exchange",
            "official": True,
            "verified_issuer": True,
        })
        if len(items) >= max(1, min(int(limit or 30), 60)):
            break
    return items


def _general_yahoo_items(provider, limit):
    items = []
    try:
        data = provider._get(
            f"{provider.BASE}/v1/finance/search?q={quote_plus('Oslo Børs Norway stocks')}&quotesCount=5&newsCount={min(max(limit * 2, 20), 80)}"
        )
        for row in data.get("news") or []:
            title = " ".join(str(row.get("title") or "").split()).strip()
            if not title:
                continue
            ts = row.get("providerPublishTime")
            related = [str(x).upper() for x in (row.get("relatedTickers") or [])]
            oslo = next((x[:-3] for x in related if x.endswith(".OL")), None)
            items.append({
                "ticker": oslo,
                "title": title,
                "publisher": row.get("publisher") or "Markedsnyheter",
                "url": row.get("link") or "",
                "published_at": datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None,
                "category": news_runtime._category(title),
                "summary": title,
                "source_type": "media",
                "official": False,
                "verified_issuer": bool(oslo),
                "related_tickers": related,
            })
            if len(items) >= limit:
                break
        return items, {"status": "live" if items else "no_matches", "items": len(items)}
    except Exception as exc:
        return [], {"status": "unavailable", "items": 0, "error": str(exc)}


def general_market_news(provider=None, limit=30):
    limit = max(1, min(int(limit or 30), 50))
    now = time.time()
    with _CACHE_LOCK:
        if _CACHE["value"] is not None and now - _CACHE["at"] < _CACHE_TTL:
            cached = dict(_CACHE["value"])
            cached["items"] = list(cached.get("items") or [])[:limit]
            return cached

    provider = provider or YahooProvider()
    items = []
    sources = {}
    try:
        exchange = parse_general_euronext_html(news_runtime._fetch_text(news_runtime.EURONEXT_LATEST), 40)
        items.extend(exchange)
        sources["euronext"] = {
            "status": "live" if exchange else "no_matches",
            "items": len(exchange),
            "url": news_runtime.EURONEXT_LATEST,
        }
    except Exception as exc:
        sources["euronext"] = {"status": "unavailable", "items": 0, "error": str(exc)}

    media, media_status = _general_yahoo_items(provider, 30)
    items.extend(media)
    sources["media"] = media_status

    merged = news_runtime._dedupe(items, 50)
    value = {
        "scope": "market",
        "market": "Oslo Børs",
        "items": merged,
        "status": "live_general_news" if merged else "no_market_news",
        "source": "Euronext / Oslo Børs + markedsnyheter",
        "sources": sources,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    with _CACHE_LOCK:
        _CACHE.update({"at": now, "value": value})
    result = dict(value)
    result["items"] = merged[:limit]
    return result


def _route_handler(app, path):
    for route in getattr(app, "routes", []):
        if getattr(route, "path", None) == path and "GET" in (getattr(route, "methods", None) or set()):
            return getattr(getattr(route, "dependant", None), "call", None) or getattr(route, "endpoint", None)
    return None


def _replace_route(app, path, handler):
    for route in getattr(app, "routes", []):
        if getattr(route, "path", None) == path and "GET" in (getattr(route, "methods", None) or set()):
            route.endpoint = handler
            dependant = getattr(route, "dependant", None)
            if dependant is not None:
                dependant.call = handler
            return True
    return False


def install():
    if getattr(extra_api, "_general_news_runtime_v1", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)
        provider = YahooProvider()
        stock_handler = _route_handler(app, "/api/news/{ticker}")
        if stock_handler:
            def cleaned_stock_news(ticker: str, limit: int = 20):
                return _clean_company_news(stock_handler(ticker, limit))
            _replace_route(app, "/api/news/{ticker}", cleaned_stock_news)

        @app.get("/api/news")
        def market_news(limit: int = 30):
            return general_market_news(provider, limit)

    extra_api.install = patched_install
    extra_api._general_news_runtime_v1 = True


install()
