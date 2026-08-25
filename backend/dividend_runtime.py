from datetime import datetime, timezone


def _extract_events(data):
    try:
        result = ((data.get("chart") or {}).get("result") or [None])[0]
    except AttributeError:
        return []
    if not isinstance(result, dict):
        return []
    raw = (result.get("events") or {}).get("dividends") or {}
    items = raw.items() if isinstance(raw, dict) else enumerate(raw) if isinstance(raw, list) else []
    out = []
    for key, item in items:
        if not isinstance(item, dict) or item.get("amount") is None:
            continue
        try:
            ts = int(item.get("date") or key)
            amount = float(item["amount"])
        except (TypeError, ValueError):
            continue
        if amount > 0:
            out.append({"timestamp": ts, "date": datetime.fromtimestamp(ts, timezone.utc).date().isoformat(), "amount": amount})
    return out


def fetch_dividend_events(provider, ticker, start_ts, end_ts):
    """Return dividend events from Yahoo chart, with bounded and max-range fallbacks."""
    symbol = provider.symbol(ticker)
    bases = tuple(getattr(provider, "BASES", (getattr(provider, "BASE", "https://query1.finance.yahoo.com"),)))
    windows = [
        {"period1": int(start_ts) - 7 * 86400, "period2": int(end_ts) + 7 * 86400, "interval": "1d", "events": "div|split"},
        {"period1": int(start_ts) - 7 * 86400, "period2": int(end_ts) + 7 * 86400, "interval": "1d", "events": "div,splits"},
    ]
    found = {}
    for base in bases:
        for params in windows:
            try:
                for item in _extract_events(provider._get(f"{base}/v8/finance/chart/{symbol}", params)):
                    if int(start_ts) - 7 * 86400 <= item["timestamp"] <= int(end_ts) + 7 * 86400:
                        found[(item["timestamp"], item["amount"])] = item
            except Exception:
                pass
        if found:
            break
    if not found:
        for base in bases:
            try:
                data = provider._get(f"{base}/v8/finance/chart/{symbol}", {"range": "max", "interval": "1d", "events": "div|split"})
                for item in _extract_events(data):
                    if int(start_ts) - 7 * 86400 <= item["timestamp"] <= int(end_ts) + 7 * 86400:
                        found[(item["timestamp"], item["amount"])] = item
                if found:
                    break
            except Exception:
                pass
    return sorted(found.values(), key=lambda x: x["timestamp"])
