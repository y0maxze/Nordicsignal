"""Prospective, append-only research journal. No broker or strategy side effects.

Only explicit, provenance-bearing inputs can produce a simulated entry. Existing
provider closes are deliberately not adapted into execution-quality observations.
"""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
import hashlib
import json
import math

from database import connect

SERIES_ID = 'opportunity-prospective-v1'
POLICY = {
    'version': SERIES_ID,
    'entry_rule': 'next_verified_session_open_after_capture',
    'execution_mode': 'research_simulation',
    'price_basis': 'unadjusted',
    'cost_model': 'not_configured',
    'net_performance_enabled': False,
    'historical_backfill': False,
}


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def timestamp(value):
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('timezone_required')
    return parsed.astimezone(timezone.utc)


def positive(value):
    if value is None or isinstance(value, bool):
        raise ValueError('invalid_price')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('invalid_price') from exc
    if not result.is_finite() or result <= 0:
        raise ValueError('invalid_price')
    return result


def required(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + '_required')
    return value


def initialize():
    """Deployment-time schema only; importing this module never writes."""
    policy = canonical(POLICY)
    conn = connect()
    try:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS measurement_series (
          series_id TEXT PRIMARY KEY, started_at TEXT NOT NULL,
          policy_json TEXT NOT NULL, policy_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS measurement_signals (
          series_id TEXT NOT NULL, event_id BIGINT NOT NULL,
          ticker TEXT NOT NULL, label TEXT NOT NULL, model_id TEXT NOT NULL,
          signal_at TEXT NOT NULL, event_created_at TEXT NOT NULL,
          available_at TEXT NOT NULL, captured_at TEXT NOT NULL,
          source_hash TEXT NOT NULL,
          PRIMARY KEY(series_id,event_id)
        );
        CREATE TABLE IF NOT EXISTS measurement_entries (
          series_id TEXT NOT NULL, event_id BIGINT NOT NULL,
          session_date TEXT NOT NULL, market_at TEXT NOT NULL,
          recorded_at TEXT NOT NULL, price TEXT NOT NULL,
          evidence_json TEXT NOT NULL, evidence_hash TEXT NOT NULL,
          PRIMARY KEY(series_id,event_id)
        );
        CREATE TABLE IF NOT EXISTS measurement_signal_evidence (
          series_id TEXT NOT NULL, event_id BIGINT NOT NULL,
          captured_at TEXT NOT NULL, source_json TEXT NOT NULL,
          PRIMARY KEY(series_id,event_id)
        );
        ''')
        conn.execute('INSERT INTO measurement_series VALUES(?,?,?,?) ON CONFLICT(series_id) DO NOTHING',
                     (SERIES_ID, now(), policy, hashlib.sha256(policy.encode()).hexdigest()))
        row = conn.execute('SELECT policy_json FROM measurement_series WHERE series_id=?', (SERIES_ID,)).fetchone()
        if row['policy_json'] != policy:
            raise ValueError('frozen_policy_changed_create_new_series')
        conn.commit()
    finally:
        conn.close()


def capture(event_id):
    """Copy a newly versioned event once; never relabel legacy events as live."""
    captured = now()
    conn = connect()
    try:
        series = conn.execute('SELECT * FROM measurement_series WHERE series_id=?', (SERIES_ID,)).fetchone()
        if not series:
            return False
        row = conn.execute('SELECT e.id,e.ticker,e.label,e.observed_at,e.created_at,e.payload,'
                           'v.signal_model_id,v.source FROM opportunity_events e '
                           'JOIN opportunity_event_versions v ON v.event_id=e.id WHERE e.id=?', (event_id,)).fetchone()
        if not row or row['source'] != 'live_verified_fingerprint':
            return False
        row = dict(row)
        created, observed, current = timestamp(row['created_at']), timestamp(row['observed_at']), timestamp(captured)
        if created < timestamp(series['started_at']):
            return False
        if created > current or observed > current:
            raise ValueError('signal_timestamp_in_future')
        model = required(row['signal_model_id'], 'model_id')
        # Capture time is the conservative availability boundary, not a stale close.
        digest = hashlib.sha256(canonical(row).encode()).hexdigest()
        existing = conn.execute('SELECT source_hash FROM measurement_signals WHERE series_id=? AND event_id=?',
                                (SERIES_ID, event_id)).fetchone()
        if existing and existing['source_hash'] != digest:
            raise ValueError('immutable_signal_conflict')
        cur = conn.execute('INSERT INTO measurement_signals VALUES(?,?,?,?,?,?,?,?,?,?) '
                           'ON CONFLICT(series_id,event_id) DO NOTHING',
                           (SERIES_ID, event_id, row['ticker'], row['label'], model,
                            observed.isoformat(), created.isoformat(), captured, captured, digest))
        inserted = cur.rowcount == 1
        if inserted:
            # Same transaction as the signal. Never reconstruct old snapshots
            # from a mutable event on retry or during schema initialization.
            conn.execute('INSERT INTO measurement_signal_evidence VALUES(?,?,?,?)',
                         (SERIES_ID, event_id, captured, canonical(row)))
        conn.commit()
        return inserted
    finally:
        conn.close()


def select_entry(signal, instrument, sessions, observations, as_of):
    """Select exactly the next certified session open, never skip a missing bar.

    Adapter must supply a complete calendar covering availability through as_of;
    a calendar assertion alone is not independently verified by this function.
    Timestamps refer to UTC instants; dates are exchange-local session dates.
    """
    available, current = timestamp(signal['available_at']), timestamp(as_of)
    if current < available:
        raise ValueError('as_of_before_signal')
    for field in ('isin', 'currency', 'provider', 'symbol', 'exchange'):
        required(instrument.get(field), field)
    if instrument.get('ticker') != signal['ticker']:
        raise ValueError('instrument_mismatch')
    required(sessions.get('source'), 'calendar_source')
    required(sessions.get('version'), 'calendar_version')
    if sessions.get('exchange') != instrument['exchange']:
        raise ValueError('calendar_exchange_mismatch')
    if instrument['exchange'] != 'XOSL':
        raise ValueError('unsupported_exchange')
    if timestamp(sessions['coverage_start']) > available or timestamp(sessions['coverage_end']) < current:
        raise ValueError('calendar_coverage_missing')
    opens = []
    dates = set()
    instants = set()
    for session in sessions['sessions']:
        day = date.fromisoformat(session['date']).isoformat()
        opened = timestamp(session['open_at'])
        if opened.astimezone(ZoneInfo('Europe/Oslo')).date().isoformat() != day:
            raise ValueError('calendar_session_date_mismatch')
        if day in dates or opened in instants:
            raise ValueError('duplicate_calendar_session')
        dates.add(day); instants.add(opened)
        opens.append((opened, day))
    eligible = sorted(x for x in opens if available < x[0] <= current)
    if not eligible:
        return {'status': 'awaiting_next_session', 'entry': None}
    opened, day = eligible[0]
    matching = [x for x in observations if x.get('session_date') == day]
    if not matching:
        return {'status': 'awaiting_verified_open', 'entry': None, 'session_date': day}
    if len(matching) != 1:
        raise ValueError('ambiguous_open_observations')
    bar = matching[0]
    for field in ('isin', 'currency', 'provider', 'symbol', 'exchange'):
        if bar.get(field) != instrument[field]:
            raise ValueError('observation_identity_mismatch')
    if bar.get('price_basis') != 'unadjusted' or bar.get('price_kind') != 'official_session_open':
        raise ValueError('unverified_price_basis')
    if timestamp(bar['market_at']) != opened:
        raise ValueError('open_timestamp_mismatch')
    if not opened <= timestamp(bar['retrieved_at']) <= current:
        raise ValueError('observation_retrieval_time_invalid')
    required(bar.get('source_ref'), 'source_ref')
    required(bar.get('revision'), 'revision')
    price = str(positive(bar['price']))
    evidence = {'instrument': dict(instrument), 'observation': dict(bar),
                'calendar': {'source': sessions['source'], 'version': sessions['version'],
                             'coverage_start': sessions['coverage_start'], 'coverage_end': sessions['coverage_end'],
                             'sessions': sessions['sessions']},
                'available_at': signal['available_at'], 'as_of': as_of,
                'entry_rule': POLICY['entry_rule']}
    canonical(evidence)
    return {'status': 'simulated_entry', 'entry': {'session_date': day,
            'market_at': opened.isoformat(), 'price': price, 'evidence': evidence}}


def record_entry(event_id, instrument, sessions, observations):
    """Internal adapter boundary; no HTTP write route or provider guessing."""
    recorded = now()
    conn = connect()
    try:
        signal = conn.execute('SELECT * FROM measurement_signals WHERE series_id=? AND event_id=?',
                              (SERIES_ID, event_id)).fetchone()
        if not signal:
            raise ValueError('signal_not_captured')
        result = select_entry(dict(signal), instrument, sessions, observations, recorded)
        entry = result['entry']
        if entry is None:
            return result
        evidence = canonical(entry['evidence'])
        # Retry timestamps and a widening calendar do not alter original evidence.
        old = conn.execute('SELECT evidence_json FROM measurement_entries WHERE series_id=? AND event_id=?',
                           (SERIES_ID, event_id)).fetchone()
        if old:
            prior = json.loads(old['evidence_json'])
            if (prior['instrument'] != instrument or prior['observation'] != entry['evidence']['observation']
                    or any(prior['calendar'][k] != sessions[k] for k in ('source', 'version'))):
                raise ValueError('immutable_entry_conflict')
            return {'status': 'already_recorded', 'entry': None}
        cur = conn.execute('INSERT INTO measurement_entries VALUES(?,?,?,?,?,?,?,?) '
                           'ON CONFLICT(series_id,event_id) DO NOTHING',
                           (SERIES_ID, event_id, entry['session_date'], entry['market_at'], recorded,
                            entry['price'], evidence, hashlib.sha256(evidence.encode()).hexdigest()))
        if cur.rowcount != 1:
            raise ValueError('concurrent_entry_retry_required')
        conn.commit()
        return result
    finally:
        conn.close()


def decision_evidence(row):
    """Bounded public projection of the original capture, never current analysis."""
    raw = row.get('source_json')
    if raw is None:
        return {'status': 'not_captured'}
    if hashlib.sha256(raw.encode()).hexdigest() != row['source_hash']:
        return {'status': 'integrity_error'}
    try:
        source = json.loads(raw)
        payload = json.loads(source['payload'])
        opportunity = payload.get('opportunity')
        if not isinstance(opportunity, dict):
            return {'status': 'unavailable'}
        components = opportunity.get('components')
        components = components if isinstance(components, dict) else {}
        reasons = opportunity.get('reasons')
        reasons = reasons if isinstance(reasons, list) else []
        def number(value):
            return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None
        def text(value):
            return value[:300] if isinstance(value, str) else None
        return {'status': 'captured', 'score': number(opportunity.get('score')),
                'confidence': text(opportunity.get('confidence')),
                'reasons': [r[:300] for r in reasons[:20] if isinstance(r, str)],
                'reasons_truncated': len(reasons) > 20,
                'components': {k: number(components.get(k)) for k in
                               ('reversal_score', 'volume_ratio', 'independent_buyers', 'buy_value_nok')},
                'insider_label': text(components.get('insider_label')),
                'source_hash': row['source_hash']}
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return {'status': 'unavailable'}


def summary():
    """Read-only status. Absence is not a successful empty journal."""
    conn = connect()
    try:
        series = conn.execute('SELECT * FROM measurement_series WHERE series_id=?', (SERIES_ID,)).fetchone()
        if not series:
            return {'status': 'not_started'}
        counts = conn.execute('SELECT COUNT(*) AS signals,COUNT(e.event_id) AS entries '
                              'FROM measurement_signals s LEFT JOIN measurement_entries e '
                              'ON e.series_id=s.series_id AND e.event_id=s.event_id WHERE s.series_id=?', (SERIES_ID,)).fetchone()
        recent = []
        for item in conn.execute('SELECT s.event_id,s.ticker,s.label,s.model_id,s.available_at,s.signal_at,'
                  's.source_hash,d.source_json FROM measurement_signals s LEFT JOIN measurement_signal_evidence d '
                  'ON d.series_id=s.series_id AND d.event_id=s.event_id '
                  'WHERE s.series_id=? ORDER BY s.available_at DESC,s.event_id DESC LIMIT 20', (SERIES_ID,)).fetchall():
            row = dict(item)
            row['decision_evidence'] = decision_evidence(row)
            row.pop('source_json')
            recent.append(row)
        return {'status': 'collecting_signals', 'series_id': SERIES_ID,
                'started_at': series['started_at'], 'policy_hash': series['policy_hash'],
                'signals': counts['signals'], 'simulated_entries': counts['entries'],
                'entry_adapter': 'not_connected', 'net_performance_enabled': False,
                'recent_signals': recent, 'recent_limit': 20}
    finally:
        conn.close()
