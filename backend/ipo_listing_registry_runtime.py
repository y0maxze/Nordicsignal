"""Official Euronext Oslo listing registry for NordicSignal IPO evidence.

Completed Oslo listings are ingested from Euronext's public IPO table and stored
idempotently. This gives IPO Radar an authoritative listing-date anchor without
reconstructing dates from media reports.
"""
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib

import extra_api
from database import connect
import news_runtime

IPO_URL = "https://live.euronext.com/en/markets/oslo/ipos"
MODEL_VERSION = "ipo_listing_registry_v1"
_MAX_PAGES = 5


def _now():
    return datetime.now(timezone.utc).isoformat()


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self._row_depth = 0
        self._cell_depth = 0
        self._cells = []
        self._parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
            return
        if self._skip:
            return
        if tag == "tr":
            self._row_depth += 1
            if self._row_depth == 1:
                self._cells = []
        elif tag in ("td", "th") and self._row_depth:
            self._cell_depth += 1
            if self._cell_depth == 1:
                self._parts = []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if tag in ("td", "th") and self._cell_depth:
            if self._cell_depth == 1:
                self._cells.append(" ".join(self._parts).strip())
                self._parts = []
            self._cell_depth -= 1
        elif tag == "tr" and self._row_depth:
            if self._row_depth == 1 and self._cells:
                self.rows.append(list(self._cells))
            self._row_depth -= 1

    def handle_data(self, data):
        if self._skip or not self._cell_depth:
            return
        text = " ".join(str(data or "").split())
        if text:
            self._parts.append(text)


def _iso_date(value):
    text = str(value or "").strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def parse_ipo_table(html):
    parser = _TableParser()
    parser.feed(str(html or ""))
    out = []
    seen = set()
    for cells in parser.rows:
        if len(cells) < 6:
            continue
        date = _iso_date(cells[0])
        if not date:
            continue
        company = " ".join(cells[1].split()).strip()
        ticker = " ".join(cells[2].split()).strip().upper()
        isin = " ".join(cells[3].split()).strip().upper()
        location = " ".join(cells[4].split()).strip()
        market = " ".join(cells[5].split()).strip()
        if location.lower() != "oslo" or "euronext" not in market.lower():
            continue
        identity = (date, isin or ticker, company)
        if identity in seen:
            continue
        seen.add(identity)
        listing_id = hashlib.sha256("|".join(identity).encode("utf-8")).hexdigest()[:32]
        out.append({
            "listing_id": listing_id,
            "listing_date": date,
            "company": company,
            "ticker": ticker or None,
            "isin": isin or None,
            "location": location,
            "market": market,
            "source_url": IPO_URL,
            "official": True,
        })
    return out


def _ensure_schema():
    conn = connect()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS ipo_listings (
          listing_id TEXT PRIMARY KEY,
          listing_date TEXT NOT NULL,
          company TEXT NOT NULL,
          ticker TEXT,
          isin TEXT,
          location TEXT NOT NULL,
          market TEXT NOT NULL,
          source_url TEXT NOT NULL,
          first_seen_at TEXT NOT NULL,
          last_seen_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ipo_listings_date ON ipo_listings(listing_date);
        CREATE INDEX IF NOT EXISTS idx_ipo_listings_ticker ON ipo_listings(ticker);
        """)
        conn.commit()
    finally:
        conn.close()


def record_listings(items):
    _ensure_schema()
    now = _now()
    conn = connect()
    inserted = 0
    try:
        for item in items or []:
            if not item.get("official") or not item.get("listing_id"):
                continue
            existing = conn.execute("SELECT listing_id FROM ipo_listings WHERE listing_id=?", (item["listing_id"],)).fetchone()
            if existing:
                conn.execute("UPDATE ipo_listings SET last_seen_at=? WHERE listing_id=?", (now, item["listing_id"]))
                continue
            conn.execute(
                "INSERT INTO ipo_listings(listing_id,listing_date,company,ticker,isin,location,market,source_url,first_seen_at,last_seen_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (item["listing_id"], item["listing_date"], item["company"], item.get("ticker"), item.get("isin"), item["location"], item["market"], item["source_url"], now, now),
            )
            inserted += 1
        conn.commit()
    finally:
        conn.close()
    return inserted


def sync_listings(fetch_text=None, max_pages=_MAX_PAGES):
    fetch = fetch_text or news_runtime._fetch_text
    all_items = []
    seen = set()
    pages_ok = 0
    for page in range(max(1, min(int(max_pages or _MAX_PAGES), 20))):
        url = IPO_URL if page == 0 else f"{IPO_URL}?page={page}"
        try:
            rows = parse_ipo_table(fetch(url))
        except Exception:
            if page == 0:
                return {"status": "unavailable", "inserted": 0, "seen": 0, "pages": 0}
            break
        pages_ok += 1
        added = 0
        for row in rows:
            if row["listing_id"] in seen:
                continue
            seen.add(row["listing_id"])
            all_items.append(row)
            added += 1
        if page > 0 and added == 0:
            break
    inserted = record_listings(all_items)
    return {"status": "ok", "inserted": inserted, "seen": len(all_items), "pages": pages_ok}


def listings(limit=100):
    _ensure_schema()
    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM ipo_listings ORDER BY listing_date DESC,company LIMIT ?", (max(1, min(int(limit or 100), 500)),)).fetchall()
        return [dict(x) for x in rows]
    finally:
        conn.close()


def build_registry(refresh=False, limit=100):
    sync = None
    if refresh:
        try:
            sync = sync_listings()
        except Exception:
            sync = {"status": "unavailable", "inserted": 0}
    rows = listings(limit=limit)
    return {
        "status": "ok" if rows else "collecting",
        "model": MODEL_VERSION,
        "count": len(rows),
        "items": rows,
        "sync": sync,
        "source": "Euronext Oslo IPO register",
        "source_url": IPO_URL,
        "policy": "Official listing-date registry only. No score or threshold changes.",
        "generated_at": _now(),
    }


def install():
    if getattr(extra_api, "_ipo_listing_registry_runtime_v1", False):
        return
    original_install = extra_api.install
    def patched_install(app):
        original_install(app)
        _ensure_schema()
        @app.get("/api/ipo-radar/listings")
        def ipo_listings(refresh: bool = False, limit: int = 100):
            return build_registry(refresh=refresh, limit=limit)
    extra_api.install = patched_install
    extra_api._ipo_listing_registry_runtime_v1 = True

install()
