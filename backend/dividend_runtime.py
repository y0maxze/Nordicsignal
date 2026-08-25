from datetime import datetime, timezone


def _extract_events(data):
    try:
        result = ((data.get("chart") or {}).get("result") or [None])[0]
    except AttributeError:
        return []
    if not isinstance(result, dict):
        return []
    events = result.get("events") or {}
    raw = events.get("dividends") or {}
    if isinstance(raw, dict):
        items = raw.items()
    elif isinstance(raw, list):
        items = enumerate(raw)
    else:
        return []

    out = []
    for key, item in items:
        if not isinstance(item, dict):
            continue
        amount = item.get("amount")
        if amount is None:
            continue
        try:
            ts = int(item.get("date") or key)
            amount = float(amount)
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue
        out.append({
            "timestamp": ts,
            "date": datetime.fromtimestamp(ts, timezone.utc).date().isoformat(),
            "amount": amount,
        })
    return out


def fetch_dividend_events(provider, ticker, start_ts, end_ts):
    """Fetch dividend events from Yahoo with provider/parameter fallbacks.

    Yahoo's chart endpoint normally returns events.dividends as a timestamp-keyed
    object. Some symbols/hosts have returned an empty event block for a bounded
    period even though the same symbol exposes the events through another Yahoo
    host or a max-range request. Try those variants before declaring no dividends.
    """
    symbol = provider.symbol(ticker)
    bases = tuple(getattr(provider, "BASES", (provider.BASE,)))
    variants = [
        ({
            "period1": int(start_ts) - 86400,
            "period2": int(end_ts) + 86400,
            "interval": "1d",
            "events": "div|split",
        }),
        ({
            "period1": int(start_ts) - 86400,
            "period2": int(end_ts) + 86400,
            "interval": "1d",
            "events": "div,splits",
        }),
    ]

    found = {}
    for base in bases:
        for params in variants:
            try:
                data = provider._get(f"{base}/v8/finance/chart/{symbol}", params)
                for item in _extract_events(data):
                    found[(item["timestamp"], item["amount"])] = item
            except Exception:
                continue
        if found:
            break

    # Last resort: request the complete daily event history and filter locally.
    if not found:
        for base in bases:
            try:
                data = provider._get(
                    f"{base}/v8/finance/chart/{symbol}",
                    {"range": "max", "interval": "1d", "events": "div|split"},
                )
                for item in _extract_events(data):
                    if int(start_ts) - 86400 <= item["timestamp"] <= int(end_ts) + 86400:
                        found[(item["timestamp"], item["amount"])] = item
                if found:
                    break
            except Exception:
                continue

    return sorted(found.values(), key=lambda x: x["timestamp"])


def install():
    import backtest_runtime
    backtest_runtime.fetch_dividend_events = fetch_dividend_events
