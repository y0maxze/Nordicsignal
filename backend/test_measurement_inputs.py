from datetime import datetime
import json
import pytest
import measurement_inputs as inputs
import measurement_journal as journal
from test_measurement_journal import db

@pytest.fixture
def ready(db,monkeypatch):
    monkeypatch.setattr(inputs,'connect',db)
    inputs.initialize()
    return db

@pytest.mark.parametrize('stamp,day,utc',[('2026-10-09T17:00:00Z','2026-10-12','07:00:00'),('2026-10-12T06:59:59Z','2026-10-12','07:00:00'),('2026-10-12T07:00:00Z','2026-10-13','07:00:00'),('2026-10-23T16:00:00Z','2026-10-26','08:00:00'),('2026-04-01T12:00:00Z','2026-04-07','07:00:00'),('2026-12-23T18:00:00Z','2026-12-28','08:00:00')])
def test_reviewed_calendar_weekend_holidays_and_dst(stamp,day,utc):
    s=inputs.scheduled_session_after(stamp)
    assert s['date']==day and utc in s['scheduled_open_at']
    assert s['verified_execution_time'] is False

@pytest.mark.parametrize('stamp',['2027-01-01T00:00:00Z','2026-12-30T12:00:00Z','2026-10-09T17:00:00'])
def test_calendar_unknown_year_or_naive_time_rejected(stamp):
    with pytest.raises(ValueError): inputs.scheduled_session_after(stamp)

def test_half_day_is_not_closed():
    assert inputs.scheduled_session_after('2026-03-31T18:00:00Z')['half_day'] is True

def test_gap_repair_uses_current_availability_and_is_idempotent(ready):
    r=inputs.reconcile();assert r['captured']==1 and r['status']=='ok'
    assert inputs.reconcile()['captured']==0
    with ready() as c:
        row=c.execute('SELECT * FROM measurement_signals').fetchone()
        assert row['available_at']=='2026-10-09T17:03:00+00:00'
        assert c.execute('SELECT COUNT(*) FROM measurement_entries').fetchone()[0]==0
    assert inputs.health()['status']=='ok'

def test_unknown_version_visible_and_no_legacy_backfill(ready):
    with ready() as c:
        c.execute("UPDATE opportunity_event_versions SET source='legacy'")
    r=inputs.reconcile();assert r['unversioned']==1 and r['status']=='partial'
    assert journal.summary()['signals']==0
    with ready() as c:c.execute("UPDATE opportunity_events SET created_at='2026-10-08T12:00:00Z'")
    assert inputs.reconcile()['unversioned']==0

def test_truncation_and_stale_health_never_claim_complete(ready,monkeypatch):
    monkeypatch.setattr(inputs,'_LIMIT',0)
    assert inputs.reconcile()['truncated'] is True
    assert inputs.health()['status']=='partial'
    monkeypatch.setattr(journal,'now',lambda:'2026-10-09T18:00:00Z')
    assert inputs.health()['status']=='stale'

def test_error_is_visible_without_rewriting_source(ready,monkeypatch):
    monkeypatch.setattr(journal,'capture',lambda _:(_ for _ in ()).throw(ValueError('bad')))
    r=inputs.reconcile();assert r['failed']==1 and r['gap_event_ids']==[1]
    assert inputs.health()['status']=='partial'

def test_missing_health_is_unknown(ready):
    r=inputs.health();assert r['status']=='stale' and r['checked_at'] is None

def test_persistent_gap_does_not_starve_newer_signals(ready, monkeypatch):
    monkeypatch.setattr(inputs, '_LIMIT', 1)
    with ready() as c:
        c.execute("UPDATE opportunity_event_versions SET source='legacy'")
        c.execute("INSERT INTO opportunity_events SELECT 2,ticker,label,observed_at,created_at,payload FROM opportunity_events WHERE id=1")
        c.execute("INSERT INTO opportunity_event_versions VALUES(2,'v1:abc','live_verified_fingerprint')")
    r=inputs.reconcile()
    assert r['unversioned']==1 and r['unreviewed']==1 and r['status']=='partial'
    r=inputs.reconcile()
    assert r['captured']==1 and r['unversioned']==1 and r['status']=='partial'
    assert journal.summary()['recent_signals'][0]['event_id']==2
    with ready() as c: c.execute("UPDATE opportunity_event_versions SET source='live_verified_fingerprint' WHERE event_id=1")
    r=inputs.reconcile()
    assert r['captured']==1 and r['status']=='ok'

def test_false_capture_is_not_silently_successful(ready,monkeypatch):
    monkeypatch.setattr(journal,'capture',lambda _:False)
    assert inputs.reconcile()['failed']==1

def test_pre_series_rows_rotate_out_of_the_way(ready,monkeypatch):
    monkeypatch.setattr(inputs,'_LIMIT',1)
    with ready() as c:
        c.execute("INSERT INTO opportunity_events SELECT 2,ticker,label,observed_at,created_at,payload FROM opportunity_events WHERE id=1")
        c.execute("INSERT INTO opportunity_event_versions VALUES(2,'v1:abc','live_verified_fingerprint')")
        c.execute("UPDATE opportunity_events SET created_at='2026-10-09T16:00:00Z' WHERE id=1")
    assert inputs.reconcile()['captured']==0
    assert inputs.reconcile()['captured']==1

def test_missing_creation_time_is_visible(ready):
    with ready() as c:c.execute('UPDATE opportunity_events SET created_at=NULL')
    assert inputs.reconcile()['invalid']==1

def test_candidate_search_rotates_even_when_older_data_is_missing(ready,monkeypatch):
    journal.capture(1)
    with ready() as c:
        c.execute("INSERT INTO measurement_signals SELECT series_id,2,ticker,label,model_id,signal_at,event_created_at,'2026-10-12T17:00:00Z',captured_at,source_hash FROM measurement_signals")
    monkeypatch.setattr(inputs,'_LIMIT',1)
    monkeypatch.setattr(journal,'now',lambda:'2026-10-13T18:00:00Z')
    rows=[{'timestamp':datetime.fromisoformat('2026-10-13T07:00:00+00:00').timestamp(),'open':101}]
    assert inputs.capture_candidates('DNB',rows)==0
    assert inputs.capture_candidates('DNB',rows)==1
    assert journal.summary()['simulated_entries']==0

def test_candidate_is_quarantined_never_promoted_and_revisions_preserved(ready,monkeypatch):
    journal.capture(1)
    monkeypatch.setattr(journal,'now',lambda:'2026-10-12T18:00:00Z')
    rows=[{'timestamp':datetime.fromisoformat('2026-10-12T07:00:00+00:00').timestamp(),'open':101}]
    assert inputs.capture_candidates('DNB',rows)==1
    assert inputs.capture_candidates('DNB',rows)==0
    rows[0]['open']=102
    assert inputs.capture_candidates('DNB',rows)==1
    with ready() as c:
        data=[json.loads(r['evidence_json']) for r in c.execute('SELECT * FROM measurement_price_candidates')]
        assert all(x['price_basis']=='unknown' and x['status']=='quarantined' for x in data)
        assert c.execute('SELECT COUNT(*) FROM measurement_entries').fetchone()[0]==0
    assert inputs.health()['candidate_events']==1

@pytest.mark.parametrize('price',[None,True,-1,0,float('nan'),float('inf')])
def test_invalid_candidate_not_recorded(ready,monkeypatch,price):
    journal.capture(1);monkeypatch.setattr(journal,'now',lambda:'2026-10-12T18:00:00Z')
    assert inputs.capture_candidates('DNB',[{'timestamp':datetime.fromisoformat('2026-10-12T07:00:00+00:00').timestamp(),'open':price}])==0

def test_future_or_wrong_session_not_substituted(ready):
    journal.capture(1)
    assert inputs.capture_candidates('DNB',[{'timestamp':datetime.fromisoformat('2026-10-12T07:00:00+00:00').timestamp(),'open':100}])==0
    assert inputs.capture_candidates('OTHER',[{'timestamp':datetime.fromisoformat('2026-10-12T07:00:00+00:00').timestamp(),'open':100}])==0
