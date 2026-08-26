"""Official upcoming-event calendar for NordicSignal.

The calendar is deliberately one shared Euronext/Oslo Bors feed rather than one
provider request per stock.  It is then mapped to the tracked universe and filtered
to Holdings when needed.  This keeps the home dashboard useful without creating a
new N-per-position load pattern on Render Free.
"""

from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin
import re
import threading
import time
import unicodedata

import extra_api
import news_runtime
from database import connect

CALENDAR_URL = "https://live.euronext.com/en/listview/financial-events"
_CACHE_TTL = 900
_MAX_PAGES = 7
_CACHE_LOCK = threading.Lock()
_CACHE = {"at": 0.0, "items": None, "errors": []}


class _CalendarTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self._in_row = False
        self._cell_depth = 0
        self._cells = []
        self._cell_text = []
        self._cell_links = []
        self._href = None
        self._link_text = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self._skip += 1
            return
        if tag == "tr":
            self._in_row = True
            self._cells = []
        elif self._in_row and tag in ("td", "th"):
            self._cell_depth += 1
            if self._cell_depth == 1:
                self._cell_text = []
                self._cell_links = []
        if tag == "a" and self._cell_depth:
            self._href = attrs.get("href")
            self._link_text = []

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            label = " ".join(self._link_text).strip()
            if self._href:
                self._cell_links.append((self._href, label))
            self._href = None
            self._link_text = []
        if self._in_row and tag in ("td", "th") and self._cell_depth:
            if self._cell_depth == 1:
                self._cells.append((" ".join(self._cell_text).strip(), list(self._cell_links)))
            self._cell_depth -= 1
        if tag == "tr" and self._in_row:
            if self._cells:
                self.rows.append(list(self._cells))
            self._in_row = False
            self._cell_depth = 0
        if tag in ("script", "style", "noscript"):
            self._skip = max(0, self._skip - 1)

    def handle_data(self, data):
        if self._skip or not self._cell_depth:
            return
        text = " ".join(data.split())
        if not text:
            return
        self._cell_text.append(text)
        if self._href is not None:
            self._link_text.append(text)


def _norm(value):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"\b(?:asa|as|ab|plc|ltd|limited|nv|n v|sa|a s)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _ticker(value):
    raw = str(value or "").strip().upper()
    if raw.endswith(".OL"):
        raw = raw[:-3]
    return raw


def _event_type(label):
    low = _norm(label)
    if "general meeting" in low or "extraordinary meeting" in low or "capital markets day" in low:
        return "meeting"
    if any(x in low for x in ("quarterly report", "half yearly report", "annual report", "interim report", "financial report")):
        return "report"
    if any(x in low for x in ("dividend", "ex date", "payment date")):
        return "dividend"
    if any(x in low for x in ("presentation", "webcast", "conference", "investor day")):
        return "presentation"
    return "event"


def _event_label(kind, raw):
    low = _norm(raw)
    if kind == "meeting":
        if "extraordinary" in low:
            return "Ekstraordinær generalforsamling"
        if "annual general" in low:
            return "Generalforsamling"
        if "capital markets" in low:
            return "Kapitalmarkedsdag"
        return "Møte"
    if kind == "report":
        q = re.search(r"\bq([1-4])\b", low)
        if q:
            return f"Q{q.group(1)}-rapport"
        if "half yearly" in low:
            return "Halvårsrapport"
        if "annual report" in low:
            return "Årsrapport"
        return "Rapport"
    if kind == "dividend":
        return "Utbytte"
    if kind == "presentation":
        return "Presentasjon / møte"
    return raw or "Selskapshendelse"


def parse_calendar_html(html):
    parser = _CalendarTableParser()
    parser.feed(html or "")
    out = []
    for cells in parser.rows:
        if len(cells) < 3:
            continue
        date_text = cells[0][0].strip()
        try:
            event_date = datetime.strptime(date_text, "%d/%m/%Y").date()
        except (TypeError, ValueError):
            continue
        company = cells[1][0].strip()
        raw_event = cells[2][0].strip()
        if not company or not raw_event:
            continue
        href = None
        if cells[2][1]:
            href = cells[2][1][0][0]
        kind = _event_type(raw_event)
        out.append({
            "date": event_date.isoformat(),
            "company": company,
            "event_type": kind,
            "event_label": _event_label(kind, raw_event),
            "event_raw": raw_event,
            "url": urljoin(CALENDAR_URL, href) if href else CALENDAR_URL,
            "source": "Euronext / Oslo Børs financial calendar",
            "official": True,
        })
    return out


def _load_reference_companies():
    conn = connect()
    try:
        stocks = conn.execute("SELECT ticker,name FROM stocks WHERE active=1").fetchall()
        holdings = conn.execute("SELECT DISTINCT ticker FROM holdings").fetchall()
    except Exception:
        stocks, holdings = [], []
    finally:
        try:
            conn.close()
        except Exception:
            pass
    stock_rows = [{"ticker": _ticker(row["ticker"]), "name": row["name"]} for row in stocks]
    holding_tickers = {_ticker(row["ticker"]) for row in holdings}
    return stock_rows, holding_tickers


def _match_stock(company, stocks):
    target = _norm(company)
    if not target:
        return None
    exact = [x for x in stocks if _norm(x.get("name")) == target]
    if exact:
        return exact[0]
    target_words = {x for x in target.split() if len(x) >= 4 and x not in {"group", "holding", "holdings", "international"}}
    best = None
    best_score = 0.0
    for stock in stocks:
        name = _norm(stock.get("name"))
        words = {x for x in name.split() if len(x) >= 4 and x not in {"group", "holding", "holdings", "international"}}
        if not words or not target_words:
            continue
        overlap = len(words & target_words)
        score = overlap / max(1, min(len(words), len(target_words)))
        if score > best_score:
            best, best_score = stock, score
    return best if best_score >= 0.75 else None


def _fetch_calendar_pages():
    now = time.time()
    with _CACHE_LOCK:
        if _CACHE["items"] is not None and now - _CACHE["at"] < _CACHE_TTL:
            return list(_CACHE["items"]), list(_CACHE["errors"])

    items = []
    errors = []
    seen = set()
    for page in range(_MAX_PAGES):
        url = CALENDAR_URL if page == 0 else f"{CALENDAR_URL}?page={page}"
        try:
            parsed = parse_calendar_html(news_runtime._fetch_text(url))
        except Exception as exc:
            errors.append(f"page {page}: {exc}")
            continue
        if not parsed and page > 0:
            break
        for row in parsed:
            key = (row["date"], _norm(row["company"]), _norm(row["event_raw"]))
            if key in seen:
                continue
            seen.add(key)
            items.append(row)

    items.sort(key=lambda x: (x.get("date") or "", _norm(x.get("company")), _norm(x.get("event_raw"))))
    with _CACHE_LOCK:
        _CACHE.update({"at": now, "items": list(items), "errors": list(errors)})
    return items, errors


def build_calendar(days=90, limit=120, holdings_only=False, today=None):
    days = max(1, min(int(days or 90), 366))
    limit = max(1, min(int(limit or 120), 250))
    start = today or date.today()
    end = start + timedelta(days=days)
    raw, errors = _fetch_calendar_pages()
    stocks, holding_tickers = _load_reference_companies()
    rows = []
    for item in raw:
        try:
            d = date.fromisoformat(item["date"])
        except Exception:
            continue
        if d < start or d > end:
            continue
        row = dict(item)
        match = _match_stock(row.get("company"), stocks)
        row["ticker"] = match.get("ticker") if match else None
        row["tracked"] = bool(match)
        row["in_holdings"] = bool(match and match.get("ticker") in holding_tickers)
        row["days_until"] = (d - start).days
        row["importance"] = "high" if row["event_type"] in ("report", "meeting") else "normal"
        if holdings_only and not row["in_holdings"]:
            continue
        rows.append(row)
    rows.sort(key=lambda x: (x["date"], 0 if x.get("in_holdings") else 1, x.get("ticker") or "", x.get("company") or ""))
    return {
        "status": "live" if rows else ("partial" if errors else "no_upcoming_events"),
        "scope": "holdings" if holdings_only else "market",
        "days": days,
        "items": rows[:limit],
        "event_count": len(rows),
        "source": "Euronext / Oslo Børs financial calendar",
        "source_url": CALENDAR_URL,
        "official": True,
        "errors": errors,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def install():
    if getattr(extra_api, "_market_calendar_runtime_v1", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)

        @app.get("/api/calendar")
        def calendar(days: int = 90, limit: int = 120):
            return build_calendar(days, limit, False)

        @app.get("/api/holdings/calendar")
        def holdings_calendar(days: int = 90, limit: int = 24):
            return build_calendar(days, limit, True)

    extra_api.install = patched_install
    extra_api._market_calendar_runtime_v1 = True


install()
