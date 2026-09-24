"""Read-only product snapshot. No provider calls, writes or score calculations."""
from datetime import datetime, timezone
import json
import logging
from database import connect

log = logging.getLogger(__name__)


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
        row.update(price=quote.get('price') or metrics.get('close'),
                   change_pct=quote.get('change_pct'),
                   quote_as_of=quote.get('captured_at') or metrics.get('close_date'),
                   data_status='LAGRET' if quote.get('price') or metrics.get('close') else 'UTILGJENGELIG',
                   trend=reversal.get('regime'), volume_ratio=metrics.get('raw_volume_ratio'),
                   relative_strength=None, opportunity=payload.get('opportunity'),
                   opportunity_observed_at=saved.get('observed_at'),
                   insider_coverage=insider.get('evidence_coverage') == 'verified_detail' and int(insider.get('evidence_item_count') or 0) > 0,
                   ownership_status='unavailable')
        result.append(row)
    return {'items':result, 'count':len(result), 'status':'partial' if warnings else 'ok',
            'unavailable_sources':warnings, 'generated_at':datetime.now(timezone.utc).isoformat(),
            'policy':'Stored observations only; score and Opportunity rules unchanged. No daily ownership feed.'}
