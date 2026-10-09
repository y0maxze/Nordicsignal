"""Read-only product snapshot. No provider calls, writes or score calculations."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import json
import logging
from database import connect

log = logging.getLogger(__name__)


def trade_time(value):
    """Only dated, timezone-aware, non-future trade evidence can rank freshness."""
    try:
        stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if stamp.tzinfo is not None and stamp <= datetime.now(timezone.utc):
            return stamp
    except (ValueError, TypeError):
        pass
    return None


def read_rows(sql):
    conn = connect()
    try:
        return [dict(row) for row in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def snapshot(stocks):
    warnings = []
    def optional(sql, name):
        try:
            return read_rows(sql)
        except Exception:
            log.exception('Market snapshot source unavailable: %s', name)
            warnings.append(name)
            return []
    quotes = {r['ticker']: r for r in optional(
        'SELECT q.* FROM quotes q JOIN (SELECT ticker,MAX(id) id FROM quotes GROUP BY ticker) z ON q.id=z.id', 'quotes')}
    states = {r['ticker']: r for r in optional('SELECT ticker,payload,observed_at FROM opportunity_state', 'opportunity')}
    result = []
    for stock in stocks:
        row = dict(stock)
        saved = states.get(row['ticker'], {})
        try:
            payload = json.loads(saved.get('payload') or '{}')
        except (ValueError, TypeError):
            payload = {}
        reversal = payload.get('reversal') or {}
        metrics = reversal.get('metrics') or {}
        insider = payload.get('insider_signal_v2') or {}
        quote = quotes.get(row['ticker']) or {}
        # An old saved quote must not mask a newer dated price observation.
        market_time = trade_time(quote.get('market_time'))
        quote_day = market_time.astimezone(ZoneInfo('Europe/Oslo')).date().isoformat() if market_time else ''
        close_day = str(metrics.get('close_date') or '')[:10]
        use_quote = quote.get('price') is not None and (not close_day or bool(quote_day) and quote_day >= close_day)
        price = quote.get('price') if use_quote else metrics.get('close')
        row.update(price=price,
                   change_pct=quote.get('change_pct') if use_quote and market_time else None,
                   quote_as_of=market_time.isoformat() if use_quote and market_time else None if use_quote else metrics.get('close_date'),
                   quote_captured_at=quote.get('captured_at') if use_quote else None,
                   quote_time_kind='trade' if use_quote and market_time else 'unknown' if use_quote else 'daily_close',
                   data_status='LAGRET' if price is not None else 'UTILGJENGELIG',
                   trend=reversal.get('regime'), volume_ratio=metrics.get('raw_volume_ratio'),
                   relative_strength=None, opportunity=payload.get('opportunity'),
                   opportunity_observed_at=saved.get('observed_at'),
                   insider_coverage=insider.get('evidence_coverage') == 'verified_detail' and int(insider.get('evidence_item_count') or 0) > 0,
                   ownership_status='unavailable')
        result.append(row)
    return {'items':result, 'count':len(result), 'status':'partial' if warnings else 'ok',
            'unavailable_sources':warnings, 'generated_at':datetime.now(timezone.utc).isoformat(),
            'policy':'Stored observations only; score and Opportunity rules unchanged. No daily ownership feed.'}
