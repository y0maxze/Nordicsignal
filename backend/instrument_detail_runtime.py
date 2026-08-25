"""Generic instrument intelligence for globally searchable stocks, funds and ETFs.

Tracked Oslo equities keep their richer NordicSignal stock model.  This module gives
all Yahoo-covered search results a real detail page with exact-symbol quote/history,
news and distribution data instead of redirecting users to Holdings.
"""
from datetime import datetime, timezone
import logging

from fastapi import HTTPException

import extra_api
from providers import YahooProvider
from portfolio_instruments_runtime import asset_class_for

log = logging.getLogger("nordicsignal.instrument_detail")

_PERIODS = {
    "now": ("1d", "5m"), "1d": ("1d", "5m"), "1w": ("5d", "1h"),
    "1m": ("1mo", "1d"), "3m": ("3mo", "1d"), "6m": ("6mo", "1d"),
    "1y": ("1y", "1d"), "5y": ("5y", "1wk"), "10y": ("10y", "1mo"),
    "max": ("max", "1mo"),
}


def _chart(provider, symbol, params):
    symbol = str(symbol or "").strip()
    if not symbol:
        raise HTTPException(400, detail="Missing market symbol")
    last = None
    for base in tuple(dict.fromkeys(getattr(provider, "BASES", ()) or (provider.BASE,))):
        try:
            data = provider._get(f"{base}/v8/finance/chart/{symbol}", params)
            result = ((data.get("chart") or {}).get("result") or [None])[0]
            if result:
                return result
            last = RuntimeError("Yahoo returned no chart result")
        except Exception as exc:
            last = exc
    raise HTTPException(502, detail=f"Market data unavailable for {symbol}: {last}")


def _search_exact(provider, symbol):
    params = {"q": symbol, "quotesCount": 8, "newsCount": 0, "enableFuzzyQuery": "false"}
    for base in tuple(dict.fromkeys(getattr(provider, "BASES", ()) or (provider.BASE,))):
        try:
            data = provider._get(f"{base}/v1/finance/search", params)
            rows = data.get("quotes") or []
            exact = next((x for x in rows if str(x.get("symbol") or "").upper() == symbol.upper()), None)
            if exact:
                return exact
        except Exception:
            continue
    return {}


def instrument_snapshot(provider, symbol, name=None, quote_type=None, exchange=None, currency=None):
    result = _chart(provider, symbol, {"range": "5d", "interval": "1d", "events": "div,splits"})
    meta = result.get("meta") or {}
    exact = _search_exact(provider, symbol)
    price = meta.get("regularMarketPrice")
    if price is None:
        price = meta.get("previousClose")
    previous = meta.get("previousClose")
    change = ((float(price) - float(previous)) / float(previous) * 100) if price is not None and previous else None
    qtype = str(quote_type or exact.get("quoteType") or meta.get("instrumentType") or "").upper() or None
    asset = asset_class_for(qtype)
    if asset == "Øvrig" and qtype == "EQUITY":
        asset = "Aksjer"
    quote_rows = (result.get("indicators", {}).get("quote") or [{}])[0]
    volumes = quote_rows.get("volume") or []
    return {
        "symbol": symbol,
        "ticker": symbol,
        "name": name or exact.get("longname") or exact.get("shortname") or meta.get("longName") or meta.get("shortName") or symbol,
        "quote_type": qtype,
        "asset_class": asset,
        "exchange": exchange or exact.get("exchDisp") or meta.get("fullExchangeName") or meta.get("exchangeName") or meta.get("exchange"),
        "currency": currency or exact.get("currency") or meta.get("currency"),
        "price": price,
        "previous_close": previous,
        "change_pct": change,
        "volume": volumes[-1] if volumes else None,
        "day_high": meta.get("regularMarketDayHigh"),
        "day_low": meta.get("regularMarketDayLow"),
        "fifty_two_week_high": meta.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": meta.get("fiftyTwoWeekLow"),
        "regular_market_time": meta.get("regularMarketTime"),
        "source": "Yahoo Finance",
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }


def instrument_history(provider, symbol, period="1y"):
    rng, interval = _PERIODS.get(period, _PERIODS["1y"])
    result = _chart(provider, symbol, {"range": rng, "interval": interval, "events": "div,splits"})
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    opens, highs, lows, volumes = quote.get("open") or [], quote.get("high") or [], quote.get("low") or [], quote.get("volume") or []
    items = []
    for i, ts in enumerate(timestamps):
        if i >= len(closes) or closes[i] is None:
            continue
        items.append({
            "timestamp": int(ts), "date": datetime.fromtimestamp(ts, timezone.utc).isoformat(),
            "open": opens[i] if i < len(opens) else None,
            "high": highs[i] if i < len(highs) else None,
            "low": lows[i] if i < len(lows) else None,
            "close": closes[i], "volume": volumes[i] if i < len(volumes) else None,
        })
    return {"symbol": symbol, "period": period, "items": items, "source": "Yahoo Finance Chart"}


def instrument_news(provider, symbol, name=None, limit=20):
    query = (name or symbol).strip()
    params = {"q": query, "quotesCount": 0, "newsCount": max(5, min(int(limit or 20), 40)), "enableFuzzyQuery": "true"}
    last = None
    data = None
    for base in tuple(dict.fromkeys(getattr(provider, "BASES", ()) or (provider.BASE,))):
        try:
            data = provider._get(f"{base}/v1/finance/search", params)
            break
        except Exception as exc:
            last = exc
    if data is None:
        return {"symbol": symbol, "items": [], "status": "unavailable", "detail": str(last), "source": "Yahoo Finance Search"}
    items = []
    for x in data.get("news") or []:
        title = x.get("title")
        if not title:
            continue
        ts = x.get("providerPublishTime")
        published = datetime.fromtimestamp(ts, timezone.utc).isoformat() if isinstance(ts, (int, float)) else None
        items.append({
            "title": title,
            "publisher": x.get("publisher"),
            "published_at": published,
            "url": x.get("link"),
            "category": "Nyhet",
            "source": "Yahoo Finance Search",
        })
    return {"symbol": symbol, "query": query, "items": items[:limit], "status": "ok", "source": "Yahoo Finance Search"}


def instrument_distributions(provider, symbol, years=10):
    result = _chart(provider, symbol, {"range": "max" if years >= 10 else f"{years}y", "interval": "1d", "events": "div,splits"})
    raw = ((result.get("events") or {}).get("dividends") or {})
    rows = raw.values() if isinstance(raw, dict) else raw if isinstance(raw, list) else []
    items = []
    for x in rows:
        if not isinstance(x, dict) or x.get("amount") is None:
            continue
        ts = x.get("date")
        items.append({
            "timestamp": ts,
            "date": datetime.fromtimestamp(ts, timezone.utc).date().isoformat() if isinstance(ts, (int, float)) else None,
            "amount": float(x["amount"]),
        })
    items.sort(key=lambda x: x.get("timestamp") or 0, reverse=True)
    return {
        "symbol": symbol, "items": items,
        "event_count": len(items), "latest": items[0] if items else None,
        "total_per_unit": sum(x["amount"] for x in items),
        "source": "Yahoo Finance Chart events",
    }


def install():
    if getattr(extra_api, "_instrument_detail_runtime_installed", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)
        provider = YahooProvider()

        @app.get("/api/instrument/{symbol}")
        def instrument_detail(symbol: str, name: str | None = None, quote_type: str | None = None, exchange: str | None = None, currency: str | None = None):
            return instrument_snapshot(provider, symbol, name, quote_type, exchange, currency)

        @app.get("/api/instrument/{symbol}/history")
        def instrument_history_route(symbol: str, period: str = "1y"):
            return instrument_history(provider, symbol, period)

        @app.get("/api/instrument/{symbol}/news")
        def instrument_news_route(symbol: str, name: str | None = None, limit: int = 20):
            return instrument_news(provider, symbol, name, limit)

        @app.get("/api/instrument/{symbol}/distributions")
        def instrument_distribution_route(symbol: str, years: int = 10):
            return instrument_distributions(provider, symbol, years)

    extra_api.install = patched_install
    extra_api._instrument_detail_runtime_installed = True
