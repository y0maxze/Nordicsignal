"""Paper-trading support for exact global symbols and amount-based fund orders.

Tracked Oslo tickers such as LSG keep the historical `.OL` mapping. Symbols from the
global instrument search (AAPL, OP0001OPBLIR, VOO, etc.) are treated as exact Yahoo
symbols so portfolio valuation and sell validation do not accidentally append `.OL`.

Traditional mutual funds are normally ordered by money amount rather than by a known
number of units. The generic instrument page therefore has a dedicated paper endpoint
that converts the entered amount to estimated units at the currently displayed NAV.
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import BaseModel, Field

import extra_api
from database import connect
from providers import YahooProvider


class InstrumentAmountOrder(BaseModel):
    symbol: str = Field(min_length=1, max_length=64)
    side: str
    amount: float = Field(gt=0)
    price: float = Field(gt=0)
    fee: float = Field(default=0, ge=0)
    currency: str | None = Field(default=None, max_length=12)
    instrument_name: str | None = Field(default=None, max_length=180)


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
    original_install = extra_api.install

    def patched_quote(provider, ticker):
        symbol = str(ticker or "").upper().strip()
        if _is_tracked_oslo(symbol):
            return original_quote(provider, symbol)
        q = _exact_quote(provider, symbol)
        if q.get("price") is None:
            raise HTTPException(502, detail="Live quote unavailable")
        return q

    extra_api._quote = patched_quote

    def patched_install(app):
        original_install(app)
        provider = YahooProvider()

        @app.post("/api/paper/instrument-order")
        def paper_instrument_amount_order(payload: InstrumentAmountOrder):
            side = str(payload.side or "").lower()
            if side not in ("buy", "sell"):
                raise HTTPException(400, detail="side must be buy or sell")
            symbol = payload.symbol.upper().strip()
            amount = float(payload.amount)
            price = float(payload.price)
            fee = float(payload.fee)
            shares = amount / price
            if shares <= 0:
                raise HTTPException(400, detail="Order amount is too small")

            portfolio = extra_api._positions(provider)
            position = next((p for p in portfolio["positions"] if str(p.get("ticker") or "").upper() == symbol), None)
            held = float(position["shares"]) if position else 0.0
            if side == "buy" and portfolio["cash"] < amount + fee:
                raise HTTPException(400, detail="Insufficient paper cash")
            if side == "sell" and held < shares - 1e-10:
                raise HTTPException(400, detail=f"Insufficient paper units; holding {held:g}")

            label = (payload.instrument_name or symbol).strip()
            currency = (payload.currency or "").upper().strip()
            note = f"Amount order: {amount:g} {currency}; estimated units at displayed NAV; {label}"[:240]
            conn = connect()
            try:
                conn.execute(
                    "INSERT INTO paper_trades(account_id,ticker,side,shares,price,fee,executed_at,note) VALUES(1,?,?,?,?,?,?,?)",
                    (symbol, side, shares, price, fee, extra_api._now(), note),
                )
                conn.commit()
            finally:
                conn.close()
            return {
                "status": "ok",
                "symbol": symbol,
                "side": side,
                "order_amount": amount,
                "currency": currency or None,
                "estimated_units": shares,
                "nav_used": price,
                "fee": fee,
                "portfolio": extra_api._positions(provider),
                "settlement_note": "Paper estimate uses the displayed NAV; a real mutual-fund order normally settles later at an unknown NAV.",
            }

    extra_api.install = patched_install
    extra_api._generic_paper_runtime_installed = True
