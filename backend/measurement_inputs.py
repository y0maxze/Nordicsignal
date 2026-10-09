"""Bounded scheduled journal reconciliation and quarantined price observations.

Daily Yahoo bars are research candidates, never certified auction executions.
Calendar is a reviewed 2026 schedule, not live instrument trading status.
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import hashlib
import json
import logging
import threading

from database import connect
import measurement_journal as journal

log = logging.getLogger(__name__)
CALENDAR_SOURCE = 'https://live.euronext.com/en/resources/trading-hours-holidays'
CALENDAR_VERSION = 'xosl-2026-reviewed-2026-10-09'
CLOSED = frozenset(('2026-01-01','2026-04-02','2026-04-03','2026-04-06',
                    '2026-05-01','2026-05-14','2026-05-25','2026-12-24','2026-12-25','2026-12-31'))
HALF_DAYS = frozenset(('2026-04-01',))
OSLO = ZoneInfo('Europe/Oslo')
_LOCK = threading.Lock()
_LIMIT = 100


def scheduled_session_after(available_at):
    """Planning only: 09:00 local scheduled open, NOT a verified auction time."""
    available = journal.timestamp(available_at)
    day = available.astimezone(OSLO).date()
    if day.year != 2026:
        raise ValueError('calendar_year_not_reviewed')
    while day.year == 2026:
        opened = datetime.combine(day, time(9), OSLO)
        if day.weekday() < 5 and day.isoformat() not in CLOSED and opened > available:
            return {'date':day.isoformat(), 'scheduled_open_at':opened.astimezone(timezone.utc).isoformat(),
                    'half_day':day.isoformat() in HALF_DAYS, 'source':CALENDAR_SOURCE,
                    'version':CALENDAR_VERSION, 'verified_execution_time':False}
        day += timedelta(days=1)
    raise ValueError('calendar_year_not_reviewed')


def initialize():
    conn = connect()
    try:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS measurement_input_health (
          series_id TEXT PRIMARY KEY, checked_at TEXT NOT NULL, report_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS measurement_price_candidates (
          series_id TEXT NOT NULL, event_id BIGINT NOT NULL, session_date TEXT NOT NULL,
          evidence_hash TEXT NOT NULL, recorded_at TEXT NOT NULL, evidence_json TEXT NOT NULL,
          PRIMARY KEY(series_id,event_id,evidence_hash)
        );
        ''')
        conn.commit()
    finally:
        conn.close()


def reconcile():
    """Repair missing captures using NOW, never the original signal availability.

    Unversioned events remain gaps; bounded work never reports full coverage when
    truncated. Oldest gaps first, so repeated successful work drains the backlog.
    """
    conn = connect()
    try:
        series = conn.execute('SELECT started_at FROM measurement_series WHERE series_id=?', (journal.SERIES_ID,)).fetchone()
        if not series:
            return {'status':'not_started'}
        start = journal.timestamp(series['started_at'])
        # One-day slack for ISO offset representations; exact comparison below.
        lower = (start.date()-timedelta(days=1)).isoformat()
        rows = [dict(r) for r in conn.execute('SELECT e.id,e.created_at,v.source FROM opportunity_events e '
            'LEFT JOIN opportunity_event_versions v ON v.event_id=e.id '
            'LEFT JOIN measurement_signals s ON s.event_id=e.id AND s.series_id=? '
            'WHERE s.event_id IS NULL AND e.created_at>=? ORDER BY e.id LIMIT ?',
            (journal.SERIES_ID,lower,_LIMIT+1)).fetchall()]
    finally:
        conn.close()
    report = {'status':'ok','captured':0,'unversioned':0,'invalid':0,'failed':0,
              'truncated':len(rows)>_LIMIT,'gap_event_ids':[]}
    for row in rows[:_LIMIT]:
        try:
            if journal.timestamp(row['created_at']) < start:
                continue
        except (ValueError,TypeError):
            report['invalid']+=1
            report['gap_event_ids'].append(row['id'])
            continue
        if row['source'] != 'live_verified_fingerprint':
            report['unversioned']+=1;report['gap_event_ids'].append(row['id']);continue
        try:
            if journal.capture(row['id']): report['captured']+=1
        except Exception:
            log.exception('Measurement capture reconciliation failed for event %s',row['id'])
            report['failed']+=1;report['gap_event_ids'].append(row['id'])
    if report['truncated'] or report['gap_event_ids']: report['status']='partial'
    report['gap_event_ids']=report['gap_event_ids'][:20]
    conn=connect()
    try:
        conn.execute('INSERT INTO measurement_input_health VALUES(?,?,?) ON CONFLICT(series_id) '
                     'DO UPDATE SET checked_at=excluded.checked_at,report_json=excluded.report_json',
                     (journal.SERIES_ID,journal.now(),journal.canonical(report)))
        conn.commit()
    finally: conn.close()
    return report


def capture_candidates(ticker, rows):
    """Reuse existing refresh data without another network call or inferred ISIN."""
    conn=connect()
    try:
        signals=[dict(r) for r in conn.execute('SELECT s.event_id,s.available_at FROM measurement_signals s '
            'LEFT JOIN measurement_entries e ON e.event_id=s.event_id AND e.series_id=s.series_id '
            'WHERE s.series_id=? AND s.ticker=? AND e.event_id IS NULL ORDER BY s.event_id LIMIT ?',
            (journal.SERIES_ID,ticker,_LIMIT)).fetchall()]
        written=0
        for signal in signals:
            try: session=scheduled_session_after(signal['available_at'])
            except ValueError: continue
            matches=[]
            for row in rows:
                try:
                    epoch=row['timestamp']
                    if isinstance(epoch,bool) or not isinstance(epoch,(float,int)):continue
                    market_at=datetime.fromtimestamp(epoch,timezone.utc)
                    if market_at.astimezone(OSLO).date().isoformat()!=session['date']:continue
                    price=str(journal.positive(row.get('open')))
                    if market_at>journal.timestamp(journal.now()):continue
                    matches.append({'timestamp':epoch,'open':price})
                except (ValueError,TypeError,KeyError,OverflowError,OSError):continue
            if not matches:continue
            evidence={'provider':'Yahoo Finance','symbol':ticker+'.OL','session':session,
                      'observations':matches,'price_basis':'unknown','isin':None,
                      'status':'quarantined','reason':'official_open_identity_and_adjustment_unverified'}
            payload=journal.canonical(evidence);digest=hashlib.sha256(payload.encode()).hexdigest()
            cur=conn.execute('INSERT INTO measurement_price_candidates VALUES(?,?,?,?,?,?) '
                'ON CONFLICT(series_id,event_id,evidence_hash) DO NOTHING',
                (journal.SERIES_ID,signal['event_id'],session['date'],digest,journal.now(),payload))
            written+=cur.rowcount
        conn.commit()
        return written
    finally:conn.close()


def schedule_reconciliation():
    if not _LOCK.acquire(blocking=False):return 'running'
    def work():
        try:reconcile()
        except Exception:log.exception('Measurement reconciliation unavailable')
        finally:_LOCK.release()
    try:threading.Thread(target=work,daemon=True,name='measurement-reconcile').start()
    except Exception:
        _LOCK.release();raise
    return 'scheduled'


def health():
    conn=connect()
    try:
        row=conn.execute('SELECT * FROM measurement_input_health WHERE series_id=?',(journal.SERIES_ID,)).fetchone()
        count=conn.execute('SELECT COUNT(DISTINCT event_id) AS n FROM measurement_price_candidates WHERE series_id=?',
                           (journal.SERIES_ID,)).fetchone()['n']
        checked=row['checked_at'] if row else None
        stale=not checked or (journal.timestamp(journal.now())-journal.timestamp(checked)).total_seconds()>1800
        report=json.loads(row['report_json']) if row else None
        return {'status':'stale' if stale else report['status'],'checked_at':checked,'reconciliation':report,
                'candidate_events':count,'entry_adapter':'quarantined_candidates_only',
                'calendar_version':CALENDAR_VERSION,'calendar_source':CALENDAR_SOURCE,
                'calendar_valid_through':'2026-12-31','automatic_entries_enabled':False}
    finally:conn.close()
