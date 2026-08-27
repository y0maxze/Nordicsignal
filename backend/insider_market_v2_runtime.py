"""Resilient market-wide insider feed for Euronext Oslo Børs.

The Euronext company-news table is authoritative for the existence, timestamp,
issuer and topic of a release. Current rows use modal/data-node-nid links. The
modal itself loads the official release from /ajax/node/company-press-release/{id},
which NordicSignal uses as the primary detail source. If detail enrichment fails,
the official list event remains visible instead of disappearing.

This runtime uses Euronext's own topic filter for "Mandatory notification of trade
primary insiders" (taxonomy id 1081), paginates the filtered list, enriches from
the official modal endpoint first, then uses the hardened per-company provider and
syndicated issuer releases as fallbacks.
"""

from collections import OrderedDict
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus, urljoin
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

_DETAIL_CACHE_LOCK = threading.RLock()
_DETAIL_CACHE = OrderedDict()
_DETAIL_CACHE_TTL = 6 * 3600
_DETAIL_CACHE_MAX = 256

EURONEXT_INSIDER_LIST = "https://live.euronext.com/en/listview/company-press-releases-by-mkt/1061/all"
EURONEXT_INSIDER_TOPIC_ID = "1081"
EURONEXT_PAGE_SIZE = 50
MAX_EURONEXT_PAGES = 8
MAX_EURONEXT_DETAIL_FETCHES = 40
MAX_SYNDICATION_ENRICH = 12


def _norm(value):
    return insider_runtime.norm(str(value or ""))


def _ticker_for_company(company):
    needle = _norm(company)
    if not needle:
        return None
    best = None
    best_len = 0
    for ticker, (name, aliases) in insider_runtime.ISSUERS.items():
        for candidate in (name, *aliases):
            candidate_n = _norm(candidate)
            if not candidate_n:
                continue
            if needle == candidate_n or (len(candidate_n) >= 5 and (candidate_n in needle or needle in candidate_n)):
                if len(candidate_n) > best_len:
                    best, best_len = ticker, len(candidate_n)
    return best


def _date_only(value):
    return str(value or "")[:10] or None


def _announcement_key(item):
    node_id = str(item.get("node_id") or "").strip()
    if node_id:
        return ("node", node_id)
    url = str(item.get("url") or "").strip()
    if url:
        return ("url", url)
    return (
        "row",
        _norm(item.get("company")),
        _date_only(item.get("published_at")),
        _norm(item.get("title")),
    )


def _insider_page_url(page):
    page = max(0, int(page or 0))
    return (
        f"{EURONEXT_INSIDER_LIST}?"
        f"field_company_press_releases_target_id%5B{EURONEXT_INSIDER_TOPIC_ID}%5D="
        f"{EURONEXT_INSIDER_TOPIC_ID}&page={page}"
    )


def _legacy_announcements(cutoff):
    """Fallback used only if the dedicated Euronext insider filter is unavailable."""
    found = []
    seen = set()
    for source_url in (news_runtime.EURONEXT_LATEST, news_runtime.EURONEXT_ARCHIVE):
        try:
            html = news_runtime._fetch_text(source_url)
            rows = general_news_runtime.parse_general_euronext_html(html, 60)
        except Exception:
            continue
        for raw in rows:
            if not base._is_insider_title(raw.get("title"), raw.get("category")):
                continue
            published = base._parse_iso(raw.get("published_at"))
            if published and published < cutoff:
                continue
            item = dict(raw)
            item["ticker"] = item.get("ticker") or _ticker_for_company(item.get("company"))
            key = _announcement_key(item)
            if key in seen:
                continue
            seen.add(key)
            found.append(item)
    return found


def _announcements(days):
    """Return every recent primary-insider disclosure from Euronext's topic feed."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    found = []
    seen = set()
    pages_scanned = 0
    rows_scanned = 0
    filter_live = False

    for page in range(MAX_EURONEXT_PAGES):
        try:
            html = news_runtime._fetch_text(_insider_page_url(page))
            parsed = general_news_runtime.parse_general_euronext_html(html, 60)
        except Exception:
            if page == 0:
                break
            continue

        pages_scanned += 1
        rows_scanned += len(parsed)
        if not parsed:
            break

        filtered_rows = [
            row for row in parsed
            if base._is_insider_title(row.get("title"), row.get("category"))
        ]
        if filtered_rows:
            filter_live = True

        crossed_cutoff = False
        dated_rows = 0
        for raw in filtered_rows:
            published = base._parse_iso(raw.get("published_at"))
            if published:
                dated_rows += 1
                if published < cutoff:
                    crossed_cutoff = True
                    continue

            item = dict(raw)
            item["ticker"] = item.get("ticker") or _ticker_for_company(item.get("company"))
            key = _announcement_key(item)
            if key in seen:
                continue
            seen.add(key)
            found.append(item)

        if crossed_cutoff and dated_rows:
            break
        if len(parsed) < EURONEXT_PAGE_SIZE:
            break

    if not found and not filter_live:
        found = _legacy_announcements(cutoff)

    found.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    return found, {
        "mode": "euronext_topic_1081" if filter_live else "legacy_fallback",
        "pages_scanned": pages_scanned,
        "rows_scanned": rows_scanned,
        "filter_live": filter_live,
    }


def _company_matches(company, text):
    company_n = _norm(company)
    hay = _norm(text)
    if not company_n or not hay:
        return False
    if company_n in hay:
        return True
    tokens = [
        token for token in company_n.split()
        if len(token) >= 5 and token not in {"group", "holding", "holdings", "international"}
    ]
    return bool(tokens and sum(token in hay for token in tokens) >= min(2, len(tokens)))


def _normalise_row(raw, announcement, ticker=None, company=None, source=None, source_url=None):
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
        "url": source_url or row.get("url") or announcement.get("url"),
        "node_id": announcement.get("node_id"),
        "details_pending": False,
    })
    return row


def _detail_cache_get(node_id):
    node_id = str(node_id or "").strip()
    if not node_id:
        return None
    now = time.time()
    with _DETAIL_CACHE_LOCK:
        cached = _DETAIL_CACHE.get(node_id)
        if not cached:
            return None
        if now - cached[0] >= _DETAIL_CACHE_TTL:
            _DETAIL_CACHE.pop(node_id, None)
            return None
        _DETAIL_CACHE.move_to_end(node_id)
        return [dict(row) for row in cached[1]]


def _detail_cache_put(node_id, rows):
    node_id = str(node_id or "").strip()
    if not node_id:
        return
    with _DETAIL_CACHE_LOCK:
        _DETAIL_CACHE[node_id] = (time.time(), [dict(row) for row in (rows or [])])
        _DETAIL_CACHE.move_to_end(node_id)
        while len(_DETAIL_CACHE) > _DETAIL_CACHE_MAX:
            _DETAIL_CACHE.popitem(last=False)


def _html_field(html, label):
    label_re = re.escape(label)
    match = re.search(
        rf"<h3[^>]*>\s*{label_re}\s*</h3>\s*<p[^>]*>\s*(?:<span[^>]*>)?\s*([^<]+)",
        html or "",
        re.I | re.S,
    )
    return " ".join(match.group(1).split()).strip() if match else None


def _associated_actor(segment):
    text = " ".join(str(segment or "").split())
    patterns = (
        r"(?P<entity>[A-ZÆØÅ][A-Za-zÀ-ÿ0-9& .'-]{1,100}\s(?:AS|ASA|AB|A/S|Ltd\.?|Limited|PLC)),\s+(?:an\s+)?associated\s+(?:entity|party)\s+of\s+(?P<context>.{0,120}?)primary insider\s+(?P<person>[A-ZÆØÅ][A-Za-zÀ-ÿ .'-]{2,80}?)(?=,|\s+on\s+\d)",
        r"(?P<entity>[A-ZÆØÅ][A-Za-zÀ-ÿ0-9& .'-]{1,100}\s(?:AS|ASA|AB|A/S|Ltd\.?|Limited|PLC)),\s+(?:et\s+)?nærstående\s+(?:selskap|foretak|part)\s+til\s+(?P<context>.{0,100}?)(?:primærinnsider|primaerinnsider)\s+(?P<person>[A-ZÆØÅ][A-Za-zÀ-ÿ .'-]{2,80}?)(?=,|\s+den\s+\d)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        entity = match.group("entity").strip(" ,.-–—")
        person = match.group("person").strip(" ,.-–—")
        context = " ".join((match.groupdict().get("context") or "").split()).strip(" ,.-–—")
        role = f"Tilknyttet {person}"
        if context:
            role += f" · {context[:80]}"
        return entity, person, role
    return None, None, None


def _euronext_ajax_rows(announcement, allow_network=True):
    node_id = str(announcement.get("node_id") or "").strip()
    if not node_id:
        return [], False
    cached = _detail_cache_get(node_id)
    if cached is not None:
        return cached, False
    if not allow_network:
        return [], False

    ajax_url = f"https://live.euronext.com/ajax/node/company-press-release/{node_id}"
    response = news_runtime._SESSION.get(ajax_url, timeout=12, allow_redirects=True)
    if response.status_code >= 400:
        raise RuntimeError(f"Euronext detail HTTP {response.status_code}")
    html = response.text
    parser = insider_runtime._Parser()
    parser.feed(html)
    body = parser.text
    low = _norm(body)
    if not any(_norm(word) in low for word in base._INSIDER_WORDS):
        _detail_cache_put(node_id, [])
        return [], True

    symbol = (_html_field(html, "Symbol") or announcement.get("ticker") or "").upper().strip() or None
    company = _html_field(html, "Company Name") or _html_field(html, "Issuer") or announcement.get("company") or symbol
    canonical_match = re.search(r'data-node-path=["\']([^"\']+)["\']', html, re.I)
    canonical_url = urljoin("https://live.euronext.com", canonical_match.group(1)) if canonical_match else announcement.get("url")
    newsweb_match = re.search(r'href=["\'](https://newsweb\.oslobors\.no/message/\d+)["\']', html, re.I)
    newsweb_url = newsweb_match.group(1) if newsweb_match else None
    title_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    title = re.sub(r"<[^>]+>", " ", title_match.group(1)).strip() if title_match else announcement.get("title") or "Primary insider transaction"

    raw_rows = insider_runtime.parse_trades(
        body,
        symbol or company or "UNKNOWN",
        title,
        "Euronext Oslo Børs Newspoint",
        canonical_url or ajax_url,
    )
    rows = []
    target_date = _date_only(announcement.get("published_at"))
    for raw in raw_rows:
        meaningful = (
            raw.get("direction") in {"buy", "sell"}
            or raw.get("shares") is not None
            or raw.get("person")
            or raw.get("entity")
            or raw.get("insider")
        )
        if not meaningful:
            continue
        row_date = _date_only(raw.get("trade_date") or raw.get("date"))
        if target_date and row_date and abs((datetime.fromisoformat(row_date) - datetime.fromisoformat(target_date)).days) > 3:
            continue
        if not (raw.get("person") or raw.get("entity") or raw.get("insider")):
            entity, person, role = _associated_actor(raw.get("summary") or body)
            if entity:
                raw["entity"] = entity
                raw["insider"] = entity
                raw["actor_type"] = "company"
                raw["role"] = raw.get("role") or role
                raw["related_primary_insider"] = person
        row = _normalise_row(
            raw,
            announcement,
            ticker=symbol,
            company=company,
            source="Euronext Oslo Børs Newspoint",
            source_url=canonical_url or ajax_url,
        )
        if newsweb_url:
            row["newsweb_url"] = newsweb_url
        row["detail_source"] = "euronext_ajax"
        rows.append(row)

    _detail_cache_put(node_id, rows)
    return [dict(row) for row in rows], True


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
    release_date = _date_only(announcement.get("published_at"))
    candidates = []
    for raw in data.get("items") or []:
        raw_date = _date_only(raw.get("trade_date") or raw.get("date"))
        if release_date and raw_date and raw_date != release_date:
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
        company_hit = _company_matches(company, title + " " + " ".join(news.get("relatedTickers") or []))
        generic_title = _norm(title) in {
            "mandatory notification of trade",
            "primary insider transaction",
            "mandatory notification of trade primary insiders",
        }
        if not (company_hit or generic_title):
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
        if not any(_norm(word) in _norm(body) for word in base._INSIDER_WORDS):
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
                raw,
                announcement,
                ticker=announcement.get("ticker"),
                company=company,
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
            "pending",
            row.get("node_id") or row.get("url") or "",
            _norm(row.get("company")),
            _date_only(row.get("published_at") or row.get("date")),
        )
    return base._trade_identity(row)


def market_insider_feed(limit=60, days=14, refresh=False):
    limit = max(1, min(int(limit or 60), 100))
    days = max(1, min(int(days or 14), 90))
    now = time.time()
    with _CACHE_LOCK:
        cached_value = _CACHE.get("value")
        if (
            not refresh
            and cached_value is not None
            and cached_value.get("days") == days
            and now - _CACHE["at"] < _CACHE_TTL
        ):
            cached = dict(cached_value)
            cached["items"] = list(cached.get("items") or [])[:limit]
            return cached

    announcements, source_meta = _announcements(days)
    provider_cache = {}
    rows = []
    errors = []
    detail_budget = MAX_EURONEXT_DETAIL_FETCHES
    detail_network_fetches = 0
    syndication_budget = MAX_SYNDICATION_ENRICH

    for announcement in announcements:
        enriched = []
        try:
            node_id = announcement.get("node_id")
            cached_detail = _detail_cache_get(node_id) if node_id else None
            if cached_detail is not None:
                enriched = cached_detail
            elif detail_budget > 0:
                enriched, used_network = _euronext_ajax_rows(announcement, allow_network=True)
                if used_network:
                    detail_budget -= 1
                    detail_network_fetches += 1
        except Exception as exc:
            errors.append(type(exc).__name__)

        if not enriched:
            try:
                enriched = _rows_from_known_provider(announcement, provider_cache)
            except Exception as exc:
                errors.append(type(exc).__name__)

        if not enriched and syndication_budget > 0:
            try:
                enriched = _syndicated_rows(announcement)
            except Exception as exc:
                errors.append(type(exc).__name__)
            syndication_budget -= 1

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
    items.sort(
        key=lambda item: (
            item.get("trade_date") or item.get("date") or item.get("published_at") or "",
            not bool(item.get("details_pending")),
        ),
        reverse=True,
    )

    pulses = base._pulse_groups(items)
    eligible_count = sum(1 for item in items if item.get("signal_eligible"))
    pending_count = sum(1 for item in items if item.get("details_pending"))
    non_signal_count = sum(
        1 for item in items
        if not item.get("signal_eligible") and not item.get("details_pending")
    )
    source_meta = dict(source_meta or {})
    source_meta.update({
        "detail_source": "euronext_ajax",
        "detail_network_fetches": detail_network_fetches,
        "detail_cache_entries": len(_DETAIL_CACHE),
    })
    value = {
        "scope": "oslo_bors_market",
        "status": "live" if announcements else "no_recent_disclosures",
        "source": "Euronext Oslo Børs Newspoint + official AJAX detail + issuer fallbacks",
        "items": items,
        "pulses": pulses,
        "disclosure_count": len(announcements),
        "eligible_trade_count": eligible_count,
        "pending_detail_count": pending_count,
        "excluded_non_signal_count": non_signal_count,
        "days": days,
        "errors": errors[:8],
        "source_meta": source_meta,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": (
            "Euronext's official insider-topic list determines that a disclosure exists. "
            "The official Euronext modal AJAX endpoint is used for transaction details. "
            "Ordinary purchases/sales are only signalled after transaction details are verified."
        ),
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
