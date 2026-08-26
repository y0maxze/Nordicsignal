"""History-derived analytics for generic stocks, funds and ETFs.

The metrics in this module are descriptive calculations from the instrument's own
Yahoo price/NAV history. They are deliberately separate from the NordicSignal Oslo
equity score so funds and ETFs do not receive a fabricated stock score.
"""
from datetime import datetime, timezone
from math import sqrt
from statistics import pstdev

import extra_api
from instrument_detail_runtime import _chart
from providers import YahooProvider


def _rows(result):
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    out = []
    for i, ts in enumerate(timestamps):
        if i >= len(closes) or closes[i] is None:
            continue
        out.append((int(ts), float(closes[i])))
    return out


def _return_from(rows, cutoff_ts):
    if len(rows) < 2:
        return None
    start = next(((ts, p) for ts, p in rows if ts >= cutoff_ts), rows[0])
    end = rows[-1]
    if not start[1]:
        return None
    return (end[1] / start[1] - 1.0) * 100.0


def _cagr(rows, years):
    if len(rows) < 2:
        return None
    end_ts, end_price = rows[-1]
    cutoff = end_ts - int(years * 365.25 * 86400)
    candidates = [(ts, p) for ts, p in rows if ts >= cutoff]
    if not candidates:
        return None
    start_ts, start_price = candidates[0]
    actual_years = (end_ts - start_ts) / (365.25 * 86400)
    if actual_years < years * 0.8 or start_price <= 0 or end_price <= 0:
        return None
    return ((end_price / start_price) ** (1.0 / actual_years) - 1.0) * 100.0


def _volatility(rows):
    prices = [p for _, p in rows[-253:] if p > 0]
    if len(prices) < 20:
        return None
    returns = [(prices[i] / prices[i - 1] - 1.0) for i in range(1, len(prices)) if prices[i - 1] > 0]
    return pstdev(returns) * sqrt(252.0) * 100.0 if len(returns) >= 10 else None


def _max_drawdown(rows):
    prices = [p for _, p in rows[-253:] if p > 0]
    if len(prices) < 2:
        return None
    peak = prices[0]
    worst = 0.0
    for price in prices:
        peak = max(peak, price)
        drawdown = (price / peak - 1.0) * 100.0
        worst = min(worst, drawdown)
    return worst


def calculate_analytics(rows, now_ts=None):
    """Pure calculation helper used by the API and unit tests."""
    rows = sorted([(int(ts), float(price)) for ts, price in rows if price is not None], key=lambda x: x[0])
    if len(rows) < 2:
        return {"data_points": len(rows)}
    end_ts, current = rows[-1]
    ref_ts = int(now_ts or end_ts)
    year = datetime.fromtimestamp(ref_ts, timezone.utc).year
    year_start = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp())
    last_52 = [(ts, p) for ts, p in rows if ts >= end_ts - int(365.25 * 86400)] or rows
    last_50 = [p for _, p in rows[-50:]]
    last_200 = [p for _, p in rows[-200:]]
    sma50 = sum(last_50) / len(last_50) if last_50 else None
    sma200 = sum(last_200) / len(last_200) if len(last_200) >= 100 else None
    return {
        "data_points": len(rows),
        "as_of": datetime.fromtimestamp(end_ts, timezone.utc).isoformat(),
        "current": current,
        "return_1m_pct": _return_from(rows, end_ts - 30 * 86400),
        "return_3m_pct": _return_from(rows, end_ts - 91 * 86400),
        "return_ytd_pct": _return_from(rows, year_start),
        "return_1y_pct": _return_from(rows, end_ts - int(365.25 * 86400)),
        "cagr_3y_pct": _cagr(rows, 3),
        "cagr_5y_pct": _cagr(rows, 5),
        "volatility_1y_pct": _volatility(rows),
        "max_drawdown_1y_pct": _max_drawdown(rows),
        "high_52w": max(p for _, p in last_52),
        "low_52w": min(p for _, p in last_52),
        "sma_50": sma50,
        "sma_200": sma200,
        "above_sma_200": (current >= sma200) if sma200 is not None else None,
        "source": "Yahoo Finance price/NAV history",
    }


def instrument_analytics(provider, symbol):
    result = _chart(provider, symbol, {"range": "5y", "interval": "1d", "events": "div,splits"})
    return {"symbol": symbol, **calculate_analytics(_rows(result))}


def install():
    if getattr(extra_api, "_instrument_analytics_runtime_installed", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)
        provider = YahooProvider()

        @app.get("/api/instrument/{symbol}/analytics")
        def instrument_analytics_route(symbol: str):
            return instrument_analytics(provider, symbol)

    extra_api.install = patched_install
    extra_api._instrument_analytics_runtime_installed = True
