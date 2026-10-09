import json
import sqlite3
import pytest
import results_audit as audit


@pytest.fixture
def db(monkeypatch):
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
    CREATE TABLE opportunity_events(id INTEGER PRIMARY KEY,ticker TEXT,label TEXT,created_at TEXT,observed_at TEXT,entry_price REAL,payload TEXT);
    CREATE TABLE opportunity_event_versions(event_id INTEGER PRIMARY KEY,signal_version TEXT,source TEXT);
    CREATE TABLE opportunity_forward_returns(event_id INTEGER,horizon_days INTEGER,target_date TEXT,target_price REAL,return_pct REAL,settled_at TEXT);
    CREATE TABLE opportunity_benchmark_evidence(event_id INTEGER,horizon_days INTEGER,benchmark_id TEXT,benchmark_return_pct REAL,excess_return_pct REAL);
    CREATE TABLE company_context_profiles(status TEXT);
    ''')
    class ReadOnly:
        def execute(self, sql):
            assert sql.startswith('SELECT '), sql
            return conn.execute(sql)
        def close(self):
            pass
    monkeypatch.setattr(audit, 'connect', ReadOnly)
    yield conn
    conn.close()


def event(db, identity, ticker='AAA', label='EARLY_OPPORTUNITY', close='2026-09-01', observed='2026-09-02T22:30:00Z'):
    payload=json.dumps({'reversal':{'metrics':{'close_date':close}}})
    db.execute('INSERT INTO opportunity_events VALUES(?,?,?,?,?,?,?)',(identity,ticker,label,observed,observed,100,payload))
    db.execute('INSERT INTO opportunity_event_versions VALUES(?,?,?)',(identity,'v1','live_verified_fingerprint'))


def outcome(db, identity, own, bench=None, horizon=20):
    db.execute('INSERT INTO opportunity_forward_returns VALUES(?,?,?,?,?,?)',(identity,horizon,'2026-10-01',110,own,'2026-10-01T16:00:00Z'))
    if bench is not None:
        db.execute('INSERT INTO opportunity_benchmark_evidence VALUES(?,?,?,?,?)',(identity,horizon,'OSEBX',bench,own-bench))


def test_read_only_empty_history_never_claims_outperformance(db):
    d=audit.snapshot()
    assert d['status']=='ok' and d['market_beaten'] is None
    assert d['groups']['ALL'][3]['difference_pp'] is None
    assert d['verdict']=='not_established'


def test_same_paired_population_and_watch_separation(db):
    event(db,1);event(db,2,'BBB');event(db,3,'CCC','WATCH_CONFLUENCE')
    outcome(db,1,10,2);outcome(db,2,100);outcome(db,3,-8,2)
    d=audit.snapshot();row=d['groups']['ALL'][3]
    assert row['settled']==3 and row['pairs']==2
    assert row['paired_mean_pct']==1 and row['benchmark_mean_pct']==2 and row['difference_pp']==-1
    assert d['groups']['EARLY_OPPORTUNITY'][3]['difference_pp']==8
    assert d['groups']['WATCH_CONFLUENCE'][3]['difference_pp']==-10
    assert d['market_beaten'] is None


def test_stale_and_repeated_entry_basis_and_large_moves_are_visible_not_removed(db):
    event(db,1);event(db,2);outcome(db,1,-90,1);outcome(db,2,2,1)
    d=audit.snapshot()
    assert 'entry_before_signal_day' in d['events'][0]['flags']
    assert 'repeated_entry_basis' in d['events'][0]['flags']
    assert 'large_price_move_review' in next(r for r in d['outcomes'] if r['event_id']==1)['flags']
    assert d['groups']['ALL'][3]['pairs']==2
    assert d['groups']['ALL'][3]['difference_pp']==-45


def test_unknown_future_and_nonfinite_data_do_not_turn_into_zero(db):
    event(db,1,close='bad',observed='2026-09-02T22:30:00')
    event(db,2,close='2026-09-05')
    outcome(db,1,float('inf'));outcome(db,2,0,0)
    d=audit.snapshot()
    assert 'entry_time_unknown' in next(e for e in d['events'] if e['id']==1)['flags']
    assert 'entry_after_signal_day' in next(e for e in d['events'] if e['id']==2)['flags']
    assert d['groups']['ALL'][3]['settled']==1
    assert d['groups']['ALL'][3]['difference_pp']==0
    json.dumps(d,allow_nan=False)


def test_missing_sources_are_partial_not_zero_evidence(db):
    event(db,1);db.execute('DROP TABLE opportunity_benchmark_evidence')
    d=audit.snapshot()
    assert d['status']=='partial' and 'outcomes' in d['unavailable_sources']
    assert len(d['events'])==1 and d['market_beaten'] is None


def test_window_cap_is_explicit_and_no_duplicate_counterpart_join(db,monkeypatch):
    monkeypatch.setattr(audit,'MAX_EVENTS',1)
    event(db,1);event(db,2);outcome(db,1,8,2);outcome(db,2,10,3)
    d=audit.snapshot()
    assert d['truncated'] and d['status']=='partial'
    assert len(d['events'])==1 and d['events'][0]['id']==2
    assert d['groups']['ALL'][3]['difference_pp']==7


def test_stored_difference_corruption_is_flagged_without_overwriting(db):
    event(db,1);outcome(db,1,10,2)
    db.execute('UPDATE opportunity_benchmark_evidence SET excess_return_pct=99')
    d=audit.snapshot()
    assert d['outcomes'][0]['difference_pp']==8
    assert 'stored_difference_mismatch' in d['outcomes'][0]['flags']
    assert db.execute('SELECT excess_return_pct FROM opportunity_benchmark_evidence').fetchone()[0]==99


def test_oslo_signal_date_and_nullable_numeric_contract():
    assert audit.oslo_day('2026-09-01T22:30:00Z')=='2026-09-02'
    for value in (None,False,'',float('nan'),float('inf')):
        assert audit.number(value) is None
    assert audit.number(0)==0
