"""Canonical global instrument search for the NordicSignal dashboard.

The dashboard search must never depend exclusively on an external provider. Tracked
NordicSignal stocks are searched locally first, then enriched with Yahoo-covered
stocks, funds and ETFs when that upstream is available.
"""

import logging

import extra_api
from database import connect
from providers import YahooProvider
from portfolio_instruments_runtime import search_instruments

log = logging.getLogger("nordicsignal.search")


def _clean(value):
    return " ".join(str(value or "").strip().split())


def _local_search(query, limit=20):
    q = _clean(query)
    if not q:
        return []
    like = f"%{q.lower()}%"
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT ticker,name,sector,exchange
            FROM stocks
            WHERE active=1
              AND (LOWER(ticker) LIKE ? OR LOWER(name) LIKE ?)
            ORDER BY CASE WHEN LOWER(ticker)=? THEN 0 WHEN LOWER(name)=? THEN 1 ELSE 2 END,
                     name
            LIMIT ?
            """,
            (like, like, q.lower(), q.lower(), max(1, min(int(limit or 20), 50))),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "ticker": str(row["ticker"]).upper(),
            "symbol": str(row["ticker"]).upper(),
            "market_symbol": f"{str(row['ticker']).upper()}.OL",
            "name": row["name"],
            "sector": row["sector"],
            "exchange": row["exchange"] or "Oslo Børs",
            "currency": "NOK",
            "quote_type": "EQUITY",
            "asset_class": "Aksjer",
            "tracked": True,
            "has_signal": True,
            "source": "NordicSignal universe",
        }
        for row in rows
    ]


def _merge_results(local_items, global_items, limit=20):
    out = []
    seen = set()
    tracked_tickers = {str(x.get("ticker") or "").upper() for x in local_items}
    for item in list(local_items) + list(global_items):
        symbol = str(item.get("symbol") or item.get("market_symbol") or item.get("ticker") or "").upper()
        if not symbol:
            continue
        base = symbol[:-3] if symbol.endswith(".OL") else symbol
        key = symbol
        if key in seen or (base in tracked_tickers and item not in local_items):
            continue
        seen.add(key)
        normalized = dict(item)
        normalized.setdefault("ticker", base)
        normalized.setdefault("symbol", symbol)
        normalized.setdefault("market_symbol", symbol)
        normalized.setdefault("asset_class", "Øvrig")
        normalized.setdefault("tracked", base in tracked_tickers)
        normalized.setdefault("has_signal", base in tracked_tickers)
        out.append(normalized)
        if len(out) >= max(1, min(int(limit or 20), 50)):
            break
    return out


def search_all(provider, query, limit=20):
    q = _clean(query)
    if not q:
        return {"query": q, "items": [], "sources": []}
    limit = max(1, min(int(limit or 20), 50))
    local_items = _local_search(q, limit)
    sources = ["NordicSignal universe"]
    global_items = []
    warning = None
    try:
        global_items = search_instruments(provider, q, max(limit, 12))
        sources.append("Yahoo Finance Search")
    except Exception as exc:
        warning = f"Global instrument search temporarily unavailable: {exc}"
        log.warning("Global search upstream unavailable for %r: %s", q, exc)
    return {
        "query": q,
        "items": _merge_results(local_items, global_items, limit),
        "sources": sources,
        "warning": warning,
    }


def install():
    if getattr(extra_api, "_global_search_runtime_installed", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)
        provider = YahooProvider()

        @app.get("/api/search")
        def global_search(q: str = "", limit: int = 20):
            return search_all(provider, q, limit)

    extra_api.install = patched_install
    extra_api._global_search_runtime_installed = True
