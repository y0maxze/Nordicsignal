"""Verified multi-source stock-news aggregation for NordicSignal.

The existing Yahoo endpoint remains the fallback. This runtime enriches it with
public Euronext/Oslo Børs company announcements and issuer investor-relations
links, while keeping strict issuer matching and direct original-source URLs.
"""

from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo
import re
import threading
import time
import unicodedata

from curl_cffi import requests

EURONEXT_LATEST = "https://live.euronext.com/en/markets/oslo/equities/company-news"
EURONEXT_ARCHIVE = "https://live.euronext.com/en/markets/oslo/equities/company-news-archive"

IR_URLS = {
    "LSG": "https://www.leroyseafood.com/en/investor/",
    "MPCC": "https://www.mpc-container.com/investors/",
    "ELO": "https://www.elopak.com/investors/",
    "PEXIP": "https://investor.pexip.com/",
    "XPLRA": "https://investor.xplora.com/",
    "EQNR": "https://www.equinor.com/investors",
    "DNB": "https://www.ir.dnb.no/",
    "NHY": "https://www.hydro.com/en/global/investors/",
    "YAR": "https://www.yara.com/investor-relations/",
    "MOWI": "https://mowi.com/investors/",
    "SALM": "https://www.salmar.no/en/investor/",
    "GJF": "https://www.gjensidige.com/group/investor-relations/",
    "TEL": "https://www.telenor.com/investors/",
    "ORK": "https://www.orkla.com/investors/",
    "TOM": "https://www.tomra.com/investor-relations",
    "KOG": "https://www.kongsberg.com/investor-relations/",
    "NAS": "https://www.norwegian.com/us/about/company/investor-relations/",
    "AKRBP": "https://akerbp.com/en/investor/",
    "AKSO": "https://www.akersolutions.com/investors/",
    "SUBC": "https://www.subsea7.com/en/investors.html",
    "BWLPG": "https://www.bwlpg.com/investors/",
    "HAUTO": "https://www.hoeghautoliners.com/investors",
    "CMBTO": "https://cmb.tech/investors",
    "VAR": "https://varenergi.no/en/investor/",
}

_SESSION = requests.Session(impersonate="chrome")
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,nb;q=0.8",
})
_CACHE = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 900


def _norm(value):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _issuer_tokens(company):
    stop = {"asa", "as", "group", "holding", "holdings", "international", "systems", "technologies", "seafood", "limited", "ltd", "plc"}
    return [x for x in _norm(company).split() if len(x) >= 4 and x not in stop]


def _matches_issuer(text, ticker, company):
    normalized = _norm(text)
    company_n = _norm(company)
    if company_n and len(company_n) >= 5 and company_n in normalized:
        return True
    tokens = _issuer_tokens(company)
    if tokens and any(t in normalized for t in tokens):
        return True
    # Never trust short ticker strings as the sole match. Long/distinct tickers are acceptable.
    ticker_n = _norm(ticker)
    return len(ticker_n) >= 5 and re.search(rf"\b{re.escape(ticker_n)}\b", normalized) is not None


def _category(title, topic=""):
    low = _norm(f"{title} {topic}")
    if any(x in low for x in ("primary insider", "mandatory notification", "meldepliktig handel", "primaerinsider", "insider transaction")):
        return "Insider"
    if any(x in low for x in ("annual report", "half year", "quarter", "q1", "q2", "q3", "q4", "financial report", "results", "earnings", "arsrapport")):
        return "Rapport"
    if any(x in low for x in ("dividend", "ex date", "utbytte", "distribution")):
        return "Utbytte"
    if any(x in low for x in ("inside information", "innsideinformasjon", "major shareholding", "flagging", "share buyback", "own shares")):
        return "Børsmelding"
    if any(x in low for x in ("contract", "agreement", "acquisition", "merger", "order", "avtale", "kontrakt")):
        return "Selskap"
    return "Nyhet"


class _RowLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.links = []
        self._row_depth = 0
        self._row_text = []
        self._row_links = []
        self._href = None
        self._link_text = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        if tag == "tr":
            self._row_depth += 1
            if self._row_depth == 1:
                self._row_text, self._row_links = [], []
        if tag == "a":
            self._href = attrs.get("href")
            self._link_text = []

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            text = " ".join(self._link_text).strip()
            record = (self._href, text)
            self.links.append(record)
            if self._row_depth:
                self._row_links.append(record)
            self._href = None
            self._link_text = []
        if tag == "tr" and self._row_depth:
            if self._row_depth == 1:
                self.rows.append((" ".join(self._row_text).strip(), list(self._row_links)))
            self._row_depth -= 1
        if tag in ("script", "style", "noscript"):
            self._skip = max(0, self._skip - 1)

    def handle_data(self, data):
        if self._skip:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self._row_depth:
            self._row_text.append(text)
        if self._href is not None:
            self._link_text.append(text)


def _fetch_text(url):
    now = time.time()
    with _CACHE_LOCK:
        cached = _CACHE.get(url)
        if cached and now - cached[0] < _CACHE_TTL:
            return cached[1]
    response = _SESSION.get(url, timeout=12, allow_redirects=True)
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code} from {urlparse(url).netloc}")
    text = response.text
    with _CACHE_LOCK:
        _CACHE[url] = (now, text)
    return text


def _parse_euronext_date(text):
    match = re.search(r"\b(\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4})\s+(\d{2}:\d{2})\s+(?:CEST|CET)?", text)
    if not match:
        return None
    try:
        local = datetime.strptime(f"{match.group(1)} {match.group(2)}", "%d %b %Y %H:%M").replace(tzinfo=ZoneInfo("Europe/Oslo"))
        return local.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def parse_euronext_html(html, ticker, company, limit=20):
    parser = _RowLinkParser(); parser.feed(html)
    items = []
    for row_text, links in parser.rows:
        if not _matches_issuer(row_text, ticker, company):
            continue
        announcement = None
        for href, text in links:
            if "/products/equities/company-news/" in (href or "") and text.strip():
                announcement = (href, text.strip())
                break
        if not announcement:
            continue
        href, title = announcement
        items.append({
            "ticker": ticker.upper(),
            "title": title,
            "publisher": "Euronext / Oslo Børs",
            "url": urljoin("https://live.euronext.com", href),
            "published_at": _parse_euronext_date(row_text),
            "category": _category(title, row_text),
            "summary": title,
            "source_type": "exchange",
            "official": True,
            "verified_issuer": True,
        })
        if len(items) >= limit:
            break
    return items


def parse_ir_html(html, base_url, ticker, company, limit=10):
    parser = _RowLinkParser(); parser.feed(html)
    candidates, seen = [], set()
    host = urlparse(base_url).netloc.lower()
    keywords = ("result", "report", "quarter", "annual", "presentation", "webcast", "financial", "stock exchange", "press release", "investor update", "trading update")
    for href, text in parser.links:
        if not href or not text:
            continue
        label = " ".join(text.split()).strip()
        norm = _norm(label)
        if len(label) < 6 or not any(k in norm for k in keywords):
            continue
        absolute = urljoin(base_url, href)
        target = urlparse(absolute)
        if target.scheme not in ("http", "https"):
            continue
        # Allow same issuer domain and direct PDF/CDN document links only.
        if target.netloc.lower() != host and not absolute.lower().endswith(".pdf"):
            continue
        key = (norm, absolute.split("#", 1)[0])
        if key in seen:
            continue
        seen.add(key)
        candidates.append({
            "ticker": ticker.upper(),
            "title": label,
            "publisher": f"{company} Investor Relations",
            "url": absolute,
            "published_at": None,
            "category": _category(label),
            "summary": label,
            "source_type": "issuer_ir",
            "official": True,
            "verified_issuer": True,
        })
        if len(candidates) >= limit:
            break
    return candidates


def _dedupe(items, limit):
    out, seen_url, seen_title = [], set(), set()
    priority = {"exchange": 0, "issuer_ir": 1, "media": 2, "aggregator": 3}
    items = sorted(items, key=lambda x: (priority.get(x.get("source_type"), 9), x.get("published_at") is None, x.get("published_at") or ""))
    # Restore newest-first inside the same source class.
    grouped = {}
    for item in items:
        grouped.setdefault(priority.get(item.get("source_type"), 9), []).append(item)
    ordered = []
    for p in sorted(grouped):
        ordered.extend(sorted(grouped[p], key=lambda x: x.get("published_at") or "", reverse=True))
    for item in ordered:
        url = (item.get("url") or "").split("?utm_", 1)[0].rstrip("/")
        title = _norm(item.get("title"))
        # Strip common issuer/legal words to catch Norwegian/English source duplicates with the same headline core.
        title_key = " ".join(x for x in title.split() if x not in {"asa", "as", "group", "the"})
        if url and url in seen_url:
            continue
        if title_key and title_key in seen_title:
            continue
        if url: seen_url.add(url)
        if title_key: seen_title.add(title_key)
        out.append(item)
        if len(out) >= limit:
            break
    # User-facing feed should be chronologically useful while keeping undated IR resources after dated news.
    dated = sorted([x for x in out if x.get("published_at")], key=lambda x: x["published_at"], reverse=True)
    undated = [x for x in out if not x.get("published_at")]
    return (dated + undated)[:limit]


def _yahoo_items(old_news, ticker, company, limit):
    try:
        data = old_news(ticker, max(limit, 12))
    except Exception as exc:
        return [], {"status": "unavailable", "error": str(exc)}
    out = []
    for item in data.get("items") or []:
        cloned = dict(item)
        cloned.update({"source_type": "media", "official": False, "verified_issuer": True})
        out.append(cloned)
    return out, {"status": data.get("status", "unknown"), "source": data.get("source", "Yahoo Finance search")}


def aggregate_news(old_news, ticker, company, limit=20):
    ticker = ticker.upper(); limit = max(1, min(int(limit), 40)); items = []; sources = {}
    yahoo, yahoo_status = _yahoo_items(old_news, ticker, company, limit)
    items.extend(yahoo); sources["media"] = yahoo_status

    exchange_items = []
    exchange_errors = []
    for source_url in (EURONEXT_LATEST, EURONEXT_ARCHIVE):
        try:
            exchange_items.extend(parse_euronext_html(_fetch_text(source_url), ticker, company, limit))
        except Exception as exc:
            exchange_errors.append(str(exc))
    items.extend(exchange_items)
    sources["euronext"] = {"status": "live" if exchange_items else ("unavailable" if exchange_errors else "no_matches"), "items": len(exchange_items), "url": EURONEXT_LATEST}
    if exchange_errors:
        sources["euronext"]["errors"] = exchange_errors

    ir_url = IR_URLS.get(ticker)
    ir_items = []
    if ir_url:
        try:
            ir_items = parse_ir_html(_fetch_text(ir_url), ir_url, ticker, company, min(limit, 10))
            sources["issuer_ir"] = {"status": "live", "items": len(ir_items), "url": ir_url}
        except Exception as exc:
            sources["issuer_ir"] = {"status": "unavailable", "items": 0, "url": ir_url, "error": str(exc)}
        items.extend(ir_items)
    else:
        sources["issuer_ir"] = {"status": "not_configured", "items": 0}

    merged = _dedupe(items, limit)
    return {
        "ticker": ticker,
        "company": company,
        "items": merged,
        "status": "live_multi_source" if merged else "no_company_news",
        "source": "Euronext / issuer IR / verified media",
        "sources": sources,
        "strict_issuer_filter": True,
        "official_count": sum(1 for x in merged if x.get("official")),
        "media_count": sum(1 for x in merged if not x.get("official")),
    }


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
    try:
        import extra_api
    except Exception:
        return
    if getattr(extra_api, "_multi_source_news_patch_v1", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)
        old_news = None
        for route in getattr(app, "routes", []):
            if getattr(route, "path", None) == "/api/news/{ticker}" and "GET" in (getattr(route, "methods", None) or set()):
                old_news = getattr(getattr(route, "dependant", None), "call", None) or getattr(route, "endpoint", None)
                break
        if old_news is None:
            return

        def multi_source_news(ticker: str, limit: int = 20):
            company = extra_api._company_name(ticker.upper())
            return aggregate_news(old_news, ticker, company, limit)

        _replace_route(app, "/api/news/{ticker}", multi_source_news)

        # Reports should use the same trusted source pool rather than a separate Yahoo-only query.
        def multi_source_reports(ticker: str, limit: int = 12):
            data = multi_source_news(ticker, max(limit * 3, 20))
            report_items = [x for x in data.get("items") or [] if x.get("category") == "Rapport"][:max(1, min(limit, 30))]
            return {
                "ticker": ticker.upper(),
                "company": data.get("company"),
                "items": report_items,
                "status": "live_reports" if report_items else "no_company_reports",
                "source": data.get("source"),
                "sources": data.get("sources"),
                "strict_issuer_filter": True,
            }

        _replace_route(app, "/api/reports/{ticker}", multi_source_reports)

    extra_api.install = patched_install
    extra_api._multi_source_news_patch_v1 = True


install()
