"""Yahoo chart metadata interpretation; never equate retrieval time with trade time."""
from datetime import datetime, timezone


def quote_snapshot(result, now=None):
    now = now or datetime.now(timezone.utc)
    meta = result.get('meta') or {}
    stamp = meta.get('regularMarketTime')
    market_time = datetime.fromtimestamp(stamp, timezone.utc) if isinstance(stamp, (int, float)) and stamp > 0 else None
    price = meta.get('regularMarketPrice')
    previous = meta.get('previousClose')
    # chartPreviousClose can be the beginning of a multi-day range. Do not use it.
    rows = list(zip(result.get('timestamp') or [], ((result.get('indicators') or {}).get('quote') or [{}])[0].get('close') or []))
    if previous is None and market_time:
        from zoneinfo import ZoneInfo
        zone = ZoneInfo(meta.get('exchangeTimezoneName') or 'UTC')
        day = market_time.astimezone(zone).date()
        completed = [(t, p) for t, p in rows if p is not None and datetime.fromtimestamp(t, zone).date() < day]
        if completed:
            previous = max(completed)[1]
    period = (meta.get('currentTradingPeriod') or {}).get('regular') or {}
    start, end = period.get('start'), period.get('end')
    valid = isinstance(start, (int,float)) and isinstance(end, (int,float))
    session = 'ÅPEN' if valid and start <= now.timestamp() < end else 'STENGT' if valid else 'UKJENT'
    change = (price / previous - 1) * 100 if price is not None and previous else None
    age = (now - market_time).total_seconds() if market_time else None
    return {'price':price, 'previous_close':previous, 'change_pct':change,
            'market_time':market_time.isoformat() if market_time else None,
            'market_status':session, 'session_source':'Yahoo currentTradingPeriod' if valid else None,
            'data_status':'UTILGJENGELIG' if price is None else 'FORSINKET' if age is not None and 0 <= age <= 3600 else 'LAGRET',
            'realtime_verified':False, 'captured_at':now.isoformat()}
