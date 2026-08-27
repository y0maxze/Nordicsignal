"""Resilient market-wide insider feed for current Euronext modal rows.

Euronext's Oslo company-news list now uses empty hrefs plus data-node-nid modal
links. The list is authoritative for the existence/date/company/topic of a
release, while details may be protected by WAF. This layer keeps the market feed
visible and enriches it through the already hardened per-issuer provider and
syndicated issuer copies. A blocked detail page must never make the entire pulse
look empty.
"""

from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus
import re
import threading
import time

import extra_api
import general_news_runtime
import insider_market_runtime as base
import insider_runtime
import news_runtime
from providers import NordicRegulatoryProvider

_CACHE_LOCK = threading.RLock()
_CACHE = {"at": 0.0, "value": None}
_CACHE_TTL = 120
_PROVIDER = NordicRegulatoryProvider()


def _norm(value):
    return insider_runtime.norm(str(value or ""))


def _ticker_for_company(company):
    needle = _norm(company)
    if not needle:
        return None
    best = None
    best_len = 0
    for ticker, (name, aliases) in insider_runtime.ISSUERS.items():
        candidates = (name, *aliases)
        for candidate in candidates:
            c = _norm(candidate)
            if not c:
                continue
            if needle == c or (len(c) >= 5 and (c in needle or needle in c)):
                if len(c) > best_len:
                    best, best_len = ticker, len(c)
    return best


def _date_only(value):
    return str(value or "")[:10] or None


def _announcement_key(item):
    return str(item.get("node_id") or item.get("url") or "") or (
        _norm(item.get("company")),
        _date_only(item.get("published_at")),
        _norm(item.get("title")),
    )


def _announcements(days):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    found = []
    seen = set()
    for source_url in (news_runtime.EURONEXT_LATEST, news_runtime.EURONEXT_ARCHIVE):
        try:
            html = news_runtime._fetch_text(source_url)
            rows = general_news_runtime.parse_general_euronext_html(html, 60)
        except Exception:
            continue
        for raw in rows:
            item = dict(raw)
            if not base._is_insider_title(item.get("title"), item.get("category")):
                continue
            published = base._parse_iso(item.get("published_at"))
            if published and published < cutoff:
                continue
            item["ticker"] = item.get("ticker") or _ticker_for_company(item.get("company"))
            key = _announcement_key(item)
            if key in seen:
                continue
            seen.add(key)
            found.append(item)
    found.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    return found


def _company_matches(company, text):
    company_n = _norm(company)
    hay = _norm(text)
    if not company_n or not hay:
        return False
    if company_n in hay:
        return True
    tokens = [x for x in company_n.split() if len(x) >= 5 and x not in {"group", "holding", "holdings", "international"}]
    return bool(tokens and sum(token in hay for token in tokens) >= min(2, len(tokens)))


def _normalise_row(raw, announcement, ticker=None, company=None, source=None):
    row = dict(raw or {})
    company = company or announcement.get("company") or row.get("company") or ticker or "Oslo Børs-selskap"
    ticker = ticker or announcement.get("ticker") or row.get("ticker") or _ticker_for_company(company)
    segment = row.get("summary") or row.get("title") or ""
    activity_type, signal_eligible = base._activity_type(segment, row)
    currency = base._currency(segment, row.get("price"))
    if currency is None:
        currency = base._currency(row.get("summary") or "", row.get("price"))
    value = row.get("transaction_value")
    date = row.get("trade_date") or row.get("date") or _date_only(announcement.get("published_at"))
    row.update({
        "ticker": ticker,
        "company": company,
        "date": date,
        "trade_date": row.get("trade_date") or date,
        "published_at": announcement.get("published_at"),
        "activity_type": activity_type,
        "signal_eligible": bool(signal_eligible),
        "currency": currency,
        "display_value": value,
        "value_basis": "reported_transaction_price" if value is not None else row.get("value_basis"),
        "official": True,
        "source": source or row.get("source") or "Euronext Oslo Børs Newspoint",
        "url": row.get("url") or announcement.get("url"),
        "node_id": announcement.get("node_id"),
        "details_pending": False,
    })
    return row


def _rows_from_known_provider(announcement, cache):
    ticker = announcement.get("ticker")
    if not ticker:
        return []
    company = announcement.get("company") or insider_runtime.ISSUERS.get(ticker, (ticker, ()))[0]
    if ticker not in cache:
        try:
            cache[ticker] = _PROVIDER.insider(ticker, company) or {}
        except Exception:
            cache[ticker] = {}
    data = cache[ticker]
    date = _date_only(announcement.get("published_at"))
    candidates = []
    for raw in data.get("items") or []:
        raw_date = _date_only(raw.get("trade_date") or raw.get("date"))
        # Use the same release-day rows when possible. If the disclosure does not
        # expose a parseable date, retain it only when this is the issuer's latest
        # announcement so we do not manufacture cross-release matches.
        if date and raw_date and raw_date != date:
            continue
        candidates.append(_normalise_row(raw, announcement, ticker=ticker, company=company))
    return candidates


def _syndicated_rows(announcement):
    company = announcement.get("company") or ""
    if not company:
        return []
    query = quote_plus(f'{company} "mandatory notification" primary insider transaction')
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=3&newsCount=20"
    try:
        response = news_runtime._SESSION.get(url, timeout=12, allow_redirects=True)
        if response.status_code >= 400:
            return []
        data = response.json()
    except Exception:
        return []

    target_date = _date_only(announcement.get("published_at"))
    for news in data.get("news") or []:
        title = " ".join(str(news.get("title") or "").split()).strip()
        link = news.get("link") or ""
        if not link or not base._is_insider_title(title, news_runtime._category(title)):
            continue
        if not _company_matches(company, title + " " + " ".join(news.get("relatedTickers") or [])):
            # A generic title is acceptable only after the article body verifies issuer.
            title_may_be_generic = _norm(title) in {
                "mandatory notification of trade", "primary insider transaction",
                "mandatory notification of trade primary insiders",
            }
        else:
            title_may_be_generic = True
        if not title_may_be_generic:
            continue
        try:
            html = news_runtime._fetch_text(link)
            parser = insider_runtime._Parser()
            parser.feed(html)
            body = parser.text
        except Exception:
            continue
        if not _company_matches(company, title + " " + body):
            continue
        if not any(_norm(x) in _norm(body) for x in base._INSIDER_WORDS):
            continue
        parse_symbol = announcement.get("ticker") or company
        rows = insider_runtime.parse_trades(
            body,
            parse_symbol,
            title or announcement.get("title") or "Primary insider transaction",
            "Syndikert issuer-melding",
            link,
        )
        normalised = []
        for raw in rows:
            row_date = _date_only(raw.get("trade_date") or raw.get("date"))
            if target_date and row_date and row_date != target_date:
                continue
            normalised.append(_normalise_row(
                raw, announcement, ticker=announcement.get("ticker"), company=company,
                source="Syndikert issuer-melding",
            ))
        if normalised:
            return normalised
    return []


def _pending_row(announcement):
    company = announcement.get("company") or announcement.get("ticker") or "Oslo Børs-selskap"
    date = _date_only(announcement.get("published_at"))
    return {
        "ticker": announcement.get("ticker") or _ticker_for_company(company),
        "company": company,
        "date": date,
        "trade_date": date,
        "published_at": announcement.get("published_at"),
        "title": announcement.get("title") or "Mandatory notification of trade",
        "direction": "unknown",
        "transaction_type": "other",
        "shares": None,
        "price": None,
        "transaction_value": None,
        "display_value": None,
        "value_basis": None,
        "insider": None,
        "person": None,
        "entity": None,
        "role": None,
        "activity_type": "details_pending",
        "signal_eligible": False,
        "details_pending": True,
        "official": True,
        "source": "Euronext Oslo Børs Newspoint",
        "url": announcement.get("url"),
        "node_id": announcement.get("node_id"),
        "summary": "Offisiell primærinsidermelding funnet på Euronext. Detaljberikelse venter.",
    }


def _identity(row):
    if row.get("details_pending"):
        return (
            "pending", row.get("node_id") or row.get("url") or "",
            _norm(row.get("company")), _date_only(row.get("published_at") or row.get("date")),
        )
    return base._trade_identity(row)


def market_insider_feed(limit=60, days=14, refresh=False):
    limit = max(1, min(int(limit or 60), 100))
    days = max(1, min(int(days or 14), 90))
    now = time.time()
    with _CACHE_LOCK:
        if not refresh and _CACHE["value"] is not None and now - _CACHE["at"] < _CACHE_TTL:
            cached = dict(_CACHE["value"])
            cached["items"] = list(cached.get("items") or [])[:limit]
            return cached

    announcements = _announcements(days)
    provider_cache = {}
    rows = []
    errors = []
    for announcement in announcements:
        enriched = []
        try:
            enriched = _rows_from_known_provider(announcement, provider_cache)
        except Exception as exc:
            errors.append(type(exc).__name__)
        if not enriched:
            try:
                enriched = _syndicated_rows(announcement)
            except Exception as exc:
                errors.append(type(exc).__name__)
        rows.extend(enriched or [_pending_row(announcement)])

    dedup = {}
    for row in rows:
        key = _identity(row)
        current = dedup.get(key)
        if current is None:
            dedup[key] = row
            continue
        if current.get("details_pending") and not row.get("details_pending"):
            dedup[key] = row
        elif current.get("display_value") is None and row.get("display_value") is not None:
            dedup[key] = row
    items = list(dedup.values())
    items.sort(key=lambda x: (
        x.get("trade_date") or x.get("date") or x.get("published_at") or "",
        not bool(x.get("details_pending")),
    ), reverse=True)

    pulses = base._pulse_groups(items)
    eligible_count = sum(1 for x in items if x.get("signal_eligible"))
    pending_count = sum(1 for x in items if x.get("details_pending"))
    non_signal_count = sum(1 for x in items if not x.get("signal_eligible") and not x.get("details_pending"))
    value = {
        "scope": "oslo_bors_market",
        "status": "live" if announcements else "no_recent_disclosures",
        "source": "Euronext Oslo Børs Newspoint + issuer/syndication enrichment",
        "items": items,
        "pulses": pulses,
        "disclosure_count": len(announcements),
        "eligible_trade_count": eligible_count,
        "pending_detail_count": pending_count,
        "excluded_non_signal_count": non_signal_count,
        "days": days,
        "errors": errors[:8],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": "Euronext-listen determines that an insider disclosure exists. Ordinary share purchases/sales are only signalled after transaction details are verified. A blocked detail page remains visible as details_pending instead of disappearing.",
        "runtime": "insider-market-v2",
    }
    with _CACHE_LOCK:
        _CACHE.update({"at": now, "value": value})
    result = dict(value)
    result["items"] = items[:limit]
    return result


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
    if getattr(extra_api, "_insider_market_v2_runtime", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)

        def insider_market(limit: int = 60, days: int = 14, refresh: bool = False):
            return market_insider_feed(limit=limit, days=days, refresh=refresh)

        if not _replace_route(app, "/api/insider-market", insider_market):
            app.get("/api/insider-market")(insider_market)

    extra_api.install = patched_install
    extra_api._insider_market_v2_runtime = True


install()
