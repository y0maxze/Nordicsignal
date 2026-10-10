"""Bounded, read-only audit of stored outcomes. Never settles or changes models."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from statistics import median
import json
import math
import logging

from database import connect
import corporate_action_evidence

HORIZONS = (1, 5, 10, 20, 60)
MAX_EVENTS = 1000
log = logging.getLogger(__name__)


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def entry_date(payload):
    try:
        value = json.loads(payload or '{}')['reversal']['metrics']['close_date']
        return date.fromisoformat(str(value)).isoformat()
    except (ValueError, TypeError, KeyError):
        return None


def oslo_day(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return stamp.astimezone(ZoneInfo('Europe/Oslo')).date().isoformat() if stamp.tzinfo else None
    except (TypeError, ValueError):
        return None


def summarize(events, outcomes):
    """Arithmetic per-event diagnostics, never compounded portfolio performance."""
    groups = {}
    for label in ['ALL'] + sorted({x['label'] for x in events}):
        selected = [e for e in events if label == 'ALL' or e['label'] == label]
        ids = {e['id'] for e in selected}
        horizons = []
        for horizon in HORIZONS:
            settled = [r for r in outcomes if r['event_id'] in ids and r['horizon_days'] == horizon and r['return_pct'] is not None]
            paired = [r for r in settled if r['benchmark_return_pct'] is not None]
            diffs = [r['return_pct'] - r['benchmark_return_pct'] for r in paired]
            mean = lambda values: round(sum(values) / len(values), 3) if values else None
            horizons.append({'days': horizon, 'events': len(selected), 'settled': len(settled),
                             'unsettled': len(selected) - len(settled), 'pairs': len(paired),
                             'raw_mean_pct': mean([r['return_pct'] for r in settled]),
                             'paired_mean_pct': mean([r['return_pct'] for r in paired]),
                             'benchmark_mean_pct': mean([r['benchmark_return_pct'] for r in paired]),
                             'difference_pp': mean(diffs),
                             'median_difference_pp': round(median(diffs), 3) if diffs else None,
                             'positive_difference_count': sum(x > 0 for x in diffs),
                             'unique_tickers': len({r['ticker'] for r in paired}),
                             'flagged_pairs': sum(bool(r['flags']) for r in paired)})
        groups[label] = horizons
    return groups


def snapshot():
    errors = []
    def read(sql):
        conn = connect()
        try:
            return [dict(x) for x in conn.execute(sql).fetchall()]
        finally:
            conn.close()
    def optional(sql, source):
        try:
            return read(sql)
        except Exception:
            log.exception('Results audit unavailable: %s', source)
            errors.append(source)
            return []

    raw = optional(f'SELECT id,ticker,label,created_at,observed_at,entry_price,payload FROM opportunity_events ORDER BY id DESC LIMIT {MAX_EVENTS + 1}', 'events')
    truncated = len(raw) > MAX_EVENTS
    raw = raw[:MAX_EVENTS]
    versions = optional(f'SELECT v.event_id,v.signal_version,v.source FROM opportunity_event_versions v JOIN (SELECT id FROM opportunity_events ORDER BY id DESC LIMIT {MAX_EVENTS}) e ON e.id=v.event_id', 'versions')
    returns = optional(f"SELECT r.*,b.benchmark_return_pct,b.excess_return_pct FROM opportunity_forward_returns r JOIN (SELECT id FROM opportunity_events ORDER BY id DESC LIMIT {MAX_EVENTS}) e ON e.id=r.event_id LEFT JOIN opportunity_benchmark_evidence b ON b.event_id=r.event_id AND b.horizon_days=r.horizon_days AND b.benchmark_id='OSEBX' ORDER BY r.event_id DESC,r.horizon_days LIMIT {MAX_EVENTS * 5 + 1}", 'outcomes')
    profiles = optional('SELECT status,COUNT(*) AS n FROM company_context_profiles GROUP BY status', 'profiles')
    version_map = {v['event_id']: v for v in versions}
    events = []
    for row in raw:
        start, observed = entry_date(row.get('payload')), oslo_day(row.get('observed_at'))
        flags = []
        if not start or not observed:
            flags.append('entry_time_unknown')
        elif start < observed:
            flags.append('entry_before_signal_day')
        elif start > observed:
            flags.append('entry_after_signal_day')
        version = version_map.get(row['id'], {})
        if version.get('source') != 'live_verified_fingerprint':
            flags.append('version_unverified')
        events.append({k: row.get(k) for k in ('id', 'ticker', 'label', 'created_at', 'observed_at')} | {
            'entry_price': number(row.get('entry_price')), 'entry_date': start,
            'version': version.get('signal_version'), 'flags': flags})
    counts = {}
    for e in events:
        key = (e['ticker'], e['entry_date'], e['label'])
        counts[key] = counts.get(key, 0) + 1
    for e in events:
        if e['entry_date'] and counts[(e['ticker'], e['entry_date'], e['label'])] > 1:
            e['flags'].append('repeated_entry_basis')
    event_map = {e['id']: e for e in events}
    outcomes = []
    actions = corporate_action_evidence.snapshot()
    truncated = truncated or len(returns) > MAX_EVENTS * 5
    for row in returns[:MAX_EVENTS * 5]:
        event = event_map.get(row['event_id'])
        if not event or row['horizon_days'] not in HORIZONS:
            continue
        own, bench = number(row.get('return_pct')), number(row.get('benchmark_return_pct'))
        flags = list(event['flags'])
        if own is not None and abs(own) >= 40:
            flags.append('large_price_move_review')
        if own is None:
            flags.append('invalid_return')
        if bench is None:
            flags.append('benchmark_missing')
        context = corporate_action_evidence.window_context(actions['items'], event['ticker'], event['entry_date'], row.get('target_date'))
        if context:
            flags.append('reviewed_corporate_action_in_window')
        stored = number(row.get('excess_return_pct'))
        if own is not None and bench is not None and (stored is None or abs(own - bench - stored) > .001):
            flags.append('stored_difference_mismatch')
        outcomes.append({'event_id': event['id'], 'ticker': event['ticker'], 'label': event['label'],
                         'horizon_days': row['horizon_days'], 'target_date': row.get('target_date'),
                         'settled_at': row.get('settled_at'), 'return_pct': own,
                         'benchmark_return_pct': bench,
                         'difference_pp': round(own - bench, 3) if own is not None and bench is not None else None,
                         'corporate_actions': context, 'flags': flags})
    recorded = sorted(e['created_at'] for e in events if e.get('created_at'))
    return {'status': 'partial' if errors or truncated else 'ok', 'unavailable_sources': errors,
            'truncated': truncated, 'event_limit': MAX_EVENTS, 'generated_at': datetime.now(timezone.utc).isoformat(),
            'verdict': 'not_established', 'market_beaten': None, 'measurement': 'stored_raw_event_diagnostics',
            'benchmark': 'OSEBX', 'benchmark_return_type': 'gross_return',
            'benchmark_source': 'https://live.euronext.com/en/product/indices/NO0007035327-XOSL',
            'first_recorded_at': recorded[0] if recorded else None, 'last_recorded_at': recorded[-1] if recorded else None,
            'events': events, 'outcomes': outcomes, 'groups': summarize(events, outcomes),
            'corporate_action_coverage': {k: v for k, v in actions.items() if k != 'items'},
            'profiles': profiles, 'policy': 'read_only_no_model_or_history_changes',
            'limitations': ['price_vs_total_return', 'benchmark_dates_not_persisted', 'execution_not_verified',
                            'costs_not_included', 'overlapping_events', 'small_sample', 'not_portfolio_return']}
