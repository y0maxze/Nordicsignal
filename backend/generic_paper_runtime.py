"""Make the existing paper-trading ledger price exact global market symbols safely.

Tracked Oslo tickers such as LSG keep the historical `.OL` mapping. Symbols from the
global instrument search (AAPL, OP0001OPBLIR, VOO, etc.) are treated as exact Yahoo
symbols so portfolio valuation and sell validation do not accidentally append `.OL`.
"""
from datetime import datetime, timezone

import extra_api
from database import connect


def _is_tracked_oslo(ticker):
    ticker = str(ticker or "").upper()
    if not ticker or "." in ticker or ticker.startswith("^"):
        return False
    conn = connect()
    try:
        return bool(conn.execute("SELECT 1 FROM stocks WHERE ticker=? AND active=1 LIMIT 1", (ticker,)).fetchone())
    finally:
        conn.close()


def _exact_quote(provider, symbol):
    last = None
    for base in tuple(dict.fromkeys(getattr(provider, "BASES", ()) or (provider.BASE,))):
        try:
            data = provider._get(f"{base}/v8/finance/chart/{symbol}", {"range": "5d", "interval": "1d"})
            result = ((data.get("chart") or {}).get("result") or [None])[0]
            if not result:
                raise RuntimeError("Yahoo returned no chart result")
            meta = result.get("meta") or {}
            price = meta.get("regularMarketPrice")
            if price is None:
                price = meta.get("previousClose")
            if price is None:
                raise RuntimeError("Yahoo returned no price")
            previous = meta.get("previousClose")
            change = ((float(price) - float(previous)) / float(previous) * 100.0) if previous else None
            volumes = ((result.get("indicators", {}).get("quote") or [{}])[0].get("volume") or [])
            return {
                "ticker": symbol,
                "symbol": symbol,
                "price": price,
                "previous_close": previous,
                "change_pct": change,
                "volume": volumes[-1] if volumes else None,
                "currency": meta.get("currency"),
                "exchange": meta.get("fullExchangeName") or meta.get("exchangeName") or meta.get("exchange"),
                "source": "Yahoo Finance exact symbol",
                "captured_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            last = exc
    raise RuntimeError(f"Exact-symbol quote failed for {symbol}: {last}")


def install():
    if getattr(extra_api, "_generic_paper_runtime_installed", False):
        return
    original_quote = extra_api._quote

    def patched_quote(provider, ticker):
        symbol = str(ticker or "").upper().strip()
        if _is_tracked_oslo(symbol):
            return original_quote(provider, symbol)
        q = _exact_quote(provider, symbol)
        if q.get("price") is None:
            from fastapi import HTTPException
            raise HTTPException(502, detail="Live quote unavailable")
        return q

    extra_api._quote = patched_quote
    extra_api._generic_paper_runtime_installed = True
