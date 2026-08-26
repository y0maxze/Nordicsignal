"""Value context for insider actor history.

Adds monetary context without inventing transaction prices. If the public disclosure
contains a transaction price, the value is reported as an actual disclosed trade
value. If price is absent, NordicSignal may use Yahoo's daily closing price for the
trade date as a clearly labelled market-value estimate.
"""

from collections import OrderedDict
from datetime import datetime
import threading
import time

from providers import NordicRegulatoryProvider, YahooProvider


_CACHE_TTL = 1800
_CACHE_MAX = 16
_PRICE_CACHE = OrderedDict()
_LOCK = threading.RLock()


def _num(value):
    return float(value) if isinstance(value, (int, float)) else None


def _day(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except (TypeError, ValueError):
        return None


def _price_cache_get(ticker):
    now = time.monotonic()
    with _LOCK:
        row = _PRICE_CACHE.get(ticker)
        if not row:
            return None
        expires, prices = row
        if expires <= now:
            _PRICE_CACHE.pop(ticker, None)
            return None
        _PRICE_CACHE.move_to_end(ticker)
        return dict(prices)


def _price_cache_put(ticker, prices):
    with _LOCK:
        _PRICE_CACHE[ticker] = (time.monotonic() + _CACHE_TTL, dict(prices))
        _PRICE_CACHE.move_to_end(ticker)
        while len(_PRICE_CACHE) > _CACHE_MAX:
            _PRICE_CACHE.popitem(last=False)


def _historical_prices(ticker):
    cached = _price_cache_get(ticker)
    if cached is not None:
        return cached
    prices = {}
    try:
        rows = YahooProvider().historical(ticker, "1y")
        for row in rows or []:
            d = _day(row.get("date"))
            close = _num(row.get("close"))
            if d and close is not None and close > 0:
                prices[d] = close
    except Exception:
        prices = {}
    _price_cache_put(ticker, prices)
    return prices


def _reference_close(trade_date, prices):
    target = _day(trade_date)
    if not target or not prices:
        return None
    if target in prices:
        return prices[target]
    # A disclosure can refer to a transaction around a holiday/weekend boundary.
    # Use only a very close trading day and keep it explicitly labelled as estimate.
    candidates = [(abs((d - target).days), d, price) for d, price in prices.items() if abs((d - target).days) <= 3]
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1]))
    return candidates[0][2]


def _value_for_trade(row, prices):
    shares = _num(row.get("shares"))
    if shares is None:
        return None, None, None
    price = _num(row.get("price"))
    if price is not None and price > 0:
        return shares * price, "reported_transaction_price", price
    ref = _reference_close(row.get("trade_date") or row.get("date"), prices)
    if ref is not None:
        return shares * ref, "market_close_estimate", ref
    return None, None, None


def _aggregate_timeline(timeline, action, prices):
    trades = [x for x in timeline or [] if x.get("action") == action]
    if not trades:
        return 0.0, None, 0, 0
    total = 0.0
    valued = 0
    actual = 0
    estimated = 0
    for trade in trades:
        value, basis, reference_price = _value_for_trade(trade, prices)
        if value is None:
            continue
        total += value
        valued += 1
        if basis == "reported_transaction_price":
            actual += 1
        else:
            estimated += 1
        trade["value"] = value
        trade["value_basis"] = basis
        if basis == "market_close_estimate":
            trade["reference_close_price"] = reference_price
    if not valued:
        return 0.0, None, actual, estimated
    basis = "reported_transaction_price" if estimated == 0 else "market_close_estimate" if actual == 0 else "mixed"
    return total, basis, actual, estimated


def enrich_result(result, ticker, prices=None):
    out = dict(result or {})
    histories = [dict(x) for x in (out.get("actor_history") or [])]
    items = [dict(x) for x in (out.get("items") or [])]
    needs_reference = any(
        _num(x.get("shares")) is not None and _num(x.get("price")) is None
        for x in items
    ) or any(
        any(_num(t.get("shares")) is not None and _num(t.get("price")) is None for t in (h.get("timeline") or []))
        for h in histories
    )
    if prices is None:
        prices = _historical_prices(ticker) if needs_reference else {}

    for item in items:
        value, basis, reference_price = _value_for_trade(item, prices)
        if value is not None:
            item["display_transaction_value"] = value
            item["transaction_value_basis"] = basis
            if basis == "market_close_estimate":
                item["reference_close_price"] = reference_price

    for history in histories:
        timeline = [dict(x) for x in (history.get("timeline") or [])]
        history["timeline"] = timeline
        buy_value, buy_basis, buy_actual, buy_estimated = _aggregate_timeline(timeline, "buy", prices)
        sell_value, sell_basis, sell_actual, sell_estimated = _aggregate_timeline(timeline, "sell", prices)
        history["observed_buy_value"] = buy_value if buy_basis else None
        history["observed_buy_value_basis"] = buy_basis
        history["observed_sell_value"] = sell_value if sell_basis else None
        history["observed_sell_value_basis"] = sell_basis
        history["valued_buy_trade_count"] = buy_actual + buy_estimated
        history["valued_sell_trade_count"] = sell_actual + sell_estimated
        history["estimated_buy_trade_count"] = buy_estimated
        history["estimated_sell_trade_count"] = sell_estimated

    out["items"] = items
    out["actor_history"] = histories
    out["insider_value_note"] = (
        "Handelsverdi er eksakt bare når offentlig melding oppgir transaksjonskurs. "
        "Når kurs mangler kan NordicSignal vise et tydelig merket estimat basert på sluttkurs rundt handelsdagen."
    )
    out["insider_value_version"] = "2026-08-27-v1"
    return out


def install():
    if getattr(NordicRegulatoryProvider, "_insider_value_runtime_v1", False):
        return
    original = NordicRegulatoryProvider.insider

    def insider(self, ticker, company_name=""):
        symbol = str(ticker or "").upper().strip()
        return enrich_result(original(self, symbol, company_name), symbol)

    NordicRegulatoryProvider.insider = insider
    NordicRegulatoryProvider._insider_value_runtime_v1 = True


install()
