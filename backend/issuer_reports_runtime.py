"""Enrich the report feed from official issuer pages.

Exchange/news aggregators can lag a freshly published quarterly report.  This module
adds a small set of issuer-owned report/news pages as an official fallback for the
canonical ``/api/reports/{ticker}`` route.  It never fabricates report metadata: only
links and titles present on the issuer page are surfaced.
"""

import re

import extra_api
import news_runtime


# Add issuer-owned pages here when a company has a stable page that exposes report
# headlines directly. MPCC's news page publishes the current quarterly result before
# some aggregator feeds have indexed it.
ISSUER_REPORT_SOURCES = {
    "MPCC": "https://www.mpc-container.com/news/",
}


def _norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _is_financial_report(title):
    """Keep actual financial results/reports, not invitations or event notices."""
    low = _norm(title)
    if not low:
        return False
    if any(x in low for x in ("invitation", "earnings call", "conference call", "silent period")):
        return False
    if any(x in low for x in ("annual report", "financial report", "half year report", "half yearly report")):
        return True
    if re.search(r"\bq[1-4]\b.*\b(report|reports|result|results)\b", low):
        return True
    if re.search(r"\b(report|reports|result|results)\b.*\bq[1-4]\b", low):
        return True
    return any(x in low for x in ("quarterly report", "quarterly results", "full year results"))


def issuer_report_items(ticker, company, limit=12):
    ticker = str(ticker or "").upper()
    source_url = ISSUER_REPORT_SOURCES.get(ticker)
    if not source_url:
        return [], None
    html = news_runtime._fetch_text(source_url)
    candidates = news_runtime.parse_ir_html(html, source_url, ticker, company, max(20, min(int(limit or 12) * 3, 40)))
    items = []
    for item in candidates:
        if not _is_financial_report(item.get("title")):
            continue
        row = dict(item)
        row["source_type"] = "issuer_report"
        row["official"] = True
        row["verified_issuer"] = True
        row["category"] = "Rapport"
        items.append(row)
        if len(items) >= max(1, min(int(limit or 12), 30)):
            break
    return items, source_url


def _merge_report_items(primary, extras, limit):
    out = []
    seen_urls = set()
    seen_titles = set()
    for item in list(extras or []) + list(primary or []):
        url = str(item.get("url") or "").split("?", 1)[0].rstrip("/").lower()
        title = _norm(item.get("title"))
        title_key = " ".join(x for x in title.split() if x not in {"asa", "as", "group", "the"})
        if url and url in seen_urls:
            continue
        if title_key and title_key in seen_titles:
            continue
        if url:
            seen_urls.add(url)
        if title_key:
            seen_titles.add(title_key)
        out.append(item)
        if len(out) >= max(1, min(int(limit or 12), 30)):
            break
    return out


def _replace_get_route(app, path, handler):
    for route in getattr(app, "routes", []):
        if getattr(route, "path", None) == path and "GET" in (getattr(route, "methods", None) or set()):
            route.endpoint = handler
            dependant = getattr(route, "dependant", None)
            if dependant is not None:
                dependant.call = handler
            return True
    return False


def install():
    if getattr(extra_api, "_issuer_reports_runtime_v1", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)
        original_reports = None
        for route in getattr(app, "routes", []):
            if getattr(route, "path", None) == "/api/reports/{ticker}" and "GET" in (getattr(route, "methods", None) or set()):
                original_reports = getattr(getattr(route, "dependant", None), "call", None) or getattr(route, "endpoint", None)
                break
        if original_reports is None:
            return

        def issuer_enriched_reports(ticker: str, limit: int = 12):
            ticker = ticker.upper()
            limit = max(1, min(int(limit or 12), 30))
            base = original_reports(ticker, limit)
            company = base.get("company") or extra_api._company_name(ticker)
            extras = []
            source_url = None
            source_error = None
            try:
                extras, source_url = issuer_report_items(ticker, company, limit)
            except Exception as exc:
                source_error = str(exc)
                source_url = ISSUER_REPORT_SOURCES.get(ticker)

            items = _merge_report_items(base.get("items") or [], extras, limit)
            out = dict(base)
            out["items"] = items
            out["status"] = "live_reports" if items else base.get("status", "no_company_reports")
            sources = dict(base.get("sources") or {})
            if source_url:
                sources["issuer_reports"] = {
                    "status": "live" if extras else ("unavailable" if source_error else "no_matches"),
                    "items": len(extras),
                    "url": source_url,
                }
                if source_error:
                    sources["issuer_reports"]["error"] = source_error
            out["sources"] = sources
            return out

        _replace_get_route(app, "/api/reports/{ticker}", issuer_enriched_reports)

    extra_api.install = patched_install
    extra_api._issuer_reports_runtime_v1 = True


install()
