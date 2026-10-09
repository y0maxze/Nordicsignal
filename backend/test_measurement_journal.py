import json
import sqlite3
import pytest
import measurement_journal as journal

@pytest.fixture
def db(tmp_path, monkeypatch):
    path=tmp_path/'journal.db'
    def connect():
        c=sqlite3.connect(path);c.row_factory=sqlite3.Row;return c
    monkeypatch.setattr(journal,'connect',connect)
    monkeypatch.setattr(journal,'now',lambda:'2026-10-09T17:00:00+00:00')
    journal.initialize()
    with connect() as c:
        c.executescript('''
        CREATE TABLE opportunity_events(id INTEGER PRIMARY KEY,ticker TEXT,label TEXT,observed_at TEXT,created_at TEXT,payload TEXT);
        CREATE TABLE opportunity_event_versions(event_id INTEGER PRIMARY KEY,signal_model_id TEXT,source TEXT);
        INSERT INTO opportunity_events VALUES(1,'DNB','EARLY_OPPORTUNITY','2026-10-09T17:01:00Z','2026-10-09T17:02:00Z','{"old_price":100}');
        INSERT INTO opportunity_event_versions VALUES(1,'v1:abc','live_verified_fingerprint');
        ''')
    monkeypatch.setattr(journal,'now',lambda:'2026-10-09T17:03:00+00:00')
    return connect

def inputs():
    s={'ticker':'DNB','available_at':'2026-10-09T17:03:00Z'}
    i={'ticker':'DNB','isin':'test-isin','provider':'fixture','symbol':'DNB.OL','exchange':'XOSL','currency':'NOK'}
    c={'source':'fixture/calendar','version':'v1','exchange':'XOSL','coverage_start':'2026-10-09T00:00:00Z','coverage_end':'2026-10-14T23:00:00Z',
       'sessions':[{'date':'2026-10-09','open_at':'2026-10-09T07:00:00Z'}, {'date':'2026-10-12','open_at':'2026-10-12T07:00:00Z'}, {'date':'2026-10-13','open_at':'2026-10-13T07:00:00Z'}]}
    b=dict(i,session_date='2026-10-12',market_at='2026-10-12T07:00:00Z',retrieved_at='2026-10-12T07:05:00Z',price='101.25',price_basis='unadjusted',price_kind='official_session_open',source_ref='fixture/open/1',revision='1')
    return s,i,c,[b],'2026-10-12T08:00:00Z'

def test_prospective_capture_retry_preserves_history(db):
    with db() as c: before=list(c.execute('SELECT * FROM opportunity_events'))
    assert journal.capture(1)
    assert not journal.capture(1)
    journal.initialize()
    with db() as c:
        assert list(c.execute('SELECT * FROM opportunity_events'))==before
        r=c.execute('SELECT * FROM measurement_signals').fetchone()
        assert r['available_at']=='2026-10-09T17:03:00+00:00' and r['model_id']=='v1:abc'
    s=journal.summary()
    assert s['signals']==1 and s['simulated_entries']==0
    assert s['started_at']=='2026-10-09T17:00:00+00:00' and s['net_performance_enabled'] is False

@pytest.mark.parametrize('value',['2026-10-08T00:00:00Z','2026-10-09T16:59:00Z'])
def test_no_legacy_backfill(db,value):
    with db() as c:c.execute('UPDATE opportunity_events SET created_at=?',(value,))
    assert not journal.capture(1)
    assert journal.summary()['signals']==0

def test_unverified_version(db):
    with db() as c:c.execute("UPDATE opportunity_event_versions SET source='legacy'")
    assert not journal.capture(1)

@pytest.mark.parametrize('value',['2026-10-09T17:01:00','invalid','2026-10-09T18:00:00Z'])
def test_invalid_signal_time(db,value):
    with db() as c:c.execute('UPDATE opportunity_events SET observed_at=?',(value,))
    with pytest.raises(ValueError):journal.capture(1)
    assert journal.summary()['signals']==0

def test_immutable_policy_and_signal(db,monkeypatch):
    journal.capture(1)
    with db() as c:c.execute("UPDATE opportunity_events SET payload='revised'")
    with pytest.raises(ValueError,match='immutable_signal'):journal.capture(1)
    monkeypatch.setitem(journal.POLICY,'entry_rule','lookahead')
    with pytest.raises(ValueError,match='frozen_policy'):journal.initialize()

def test_weekend_next_open():
    r=journal.select_entry(*inputs())
    assert r['entry']['session_date']=='2026-10-12' and r['entry']['price']=='101.25'

def test_exact_open_requires_later_session():
    s,i,c,b,t=inputs();s['available_at']='2026-10-12T07:00:00Z'
    assert journal.select_entry(s,i,c,b,t)['status']=='awaiting_next_session'

def test_missing_first_bar_not_skipped():
    s,i,c,b,t=inputs();b[0]['session_date']='2026-10-13'
    r=journal.select_entry(s,i,c,b,'2026-10-13T08:00:00Z')
    assert r['status']=='awaiting_verified_open' and r['session_date']=='2026-10-12'

@pytest.mark.parametrize('field,value',[('price',0),('price',-1),('price',True),('price',None),('price','NaN'),('price','Infinity'),('price','oops'),('currency','USD'),('isin','wrong'),('symbol','OTHER'),('provider','other'),('exchange','XNYS'),('price_basis','adjusted'),('price_kind','close'),('market_at','2026-10-12T08:00:00Z'),('market_at','2026-10-12T07:00:00'),('retrieved_at','2026-10-12T06:59:00Z'),('retrieved_at','2026-10-12T09:00:00Z'),('revision',''),('source_ref','')])
def test_bad_evidence_fails_closed(field,value):
    s,i,c,b,t=inputs();b[0][field]=value
    with pytest.raises(ValueError):journal.select_entry(s,i,c,b,t)

def test_calendar_and_price_ambiguity():
    s,i,c,b,t=inputs()
    with pytest.raises(ValueError,match='ambiguous'):journal.select_entry(s,i,c,b+b,t)
    c['coverage_start']='2026-10-10T00:00:00Z'
    with pytest.raises(ValueError,match='coverage'):journal.select_entry(s,i,c,b,t)
    s,i,c,b,t=inputs();c['sessions'].append(dict(c['sessions'][0]))
    with pytest.raises(ValueError,match='duplicate'):journal.select_entry(s,i,c,b,t)

def test_timezone_equivalence_and_dst():
    s,i,c,b,t=inputs();s['available_at']='2026-10-09T19:03:00+02:00';b[0]['market_at']='2026-10-12T09:00:00+02:00'
    assert journal.select_entry(s,i,c,b,t)['entry']['market_at']=='2026-10-12T07:00:00+00:00'
    s['available_at']='2026-10-23T18:00:00+02:00';c['coverage_start']='2026-10-23T00:00:00Z';c['coverage_end']='2026-10-27T23:00:00Z'
    c['sessions']=[{'date':'2026-10-26','open_at':'2026-10-26T09:00:00+01:00'}]
    b[0].update(session_date='2026-10-26',market_at='2026-10-26T08:00:00Z',retrieved_at='2026-10-26T08:05:00Z')
    assert journal.select_entry(s,i,c,b,'2026-10-26T09:00:00Z')['entry']['market_at']=='2026-10-26T08:00:00+00:00'

def test_persist_entry_retry_and_revision_conflict(db,monkeypatch):
    journal.capture(1);s,i,c,b,t=inputs();monkeypatch.setattr(journal,'now',lambda:t)
    assert journal.record_entry(1,i,c,b)['status']=='simulated_entry'
    assert journal.record_entry(1,i,c,b)['status']=='already_recorded'
    b[0]['price']='102'
    with pytest.raises(ValueError,match='immutable_entry'):journal.record_entry(1,i,c,b)
    with db() as conn:
        row=conn.execute('SELECT * FROM measurement_entries').fetchone()
        assert row['price']=='101.25'
        assert json.loads(row['evidence_json'])['observation']['revision']=='1'
    assert journal.summary()['simulated_entries']==1

def test_missing_signal_and_series(db):
    s,i,c,b,t=inputs()
    with pytest.raises(ValueError,match='signal_not_captured'):journal.record_entry(1,i,c,b)
    with db() as c:c.execute('DELETE FROM measurement_series')
    assert journal.summary()=={'status':'not_started'}
    assert not journal.capture(1)

def test_calendar_date_must_match_exchange_local_open():
    s,i,c,b,t=inputs();c['sessions'][1]['date']='2026-10-11'
    with pytest.raises(ValueError,match='session_date_mismatch'):journal.select_entry(s,i,c,b,t)

@pytest.mark.parametrize('kind,previous',[(None,'WATCH_CONFLUENCE'),('first_observed_qualifying_state',None)])
def test_capture_hook_uses_exact_event_key(monkeypatch,kind,previous):
    import opportunity_versioned_learning_runtime as versioned
    calls=[]
    class Conn:
        def execute(self,sql,args):
            calls.append(args);return self
        def fetchone(self):return {'id':42,'ticker':'DNB'}
        def close(self):pass
    monkeypatch.setattr(versioned,'_BASE_RECORD',lambda *a:{'emitted':True,'label':'EARLY_OPPORTUNITY','previous_label':previous,'event_kind':kind})
    monkeypatch.setattr(versioned.tracking,'connect',Conn)
    monkeypatch.setattr(versioned,'_stamp_live_event',lambda event:calls.append(event['id']))
    monkeypatch.setattr(versioned,'_latest_event',lambda *a:pytest.fail('racy latest-event lookup'))
    versioned._record_versioned({'ticker':'DNB','generated_at':'2026-10-09T17:00:00Z'})
    prior='FIRST_OBSERVED' if kind else previous
    assert calls==[('DNB',f'2026-10-09:{prior}->EARLY_OPPORTUNITY'),42]

def test_real_first_observation_is_versioned_and_captured(tmp_path,monkeypatch):
    import opportunity_tracking_runtime as tracking
    import opportunity_data_coverage_runtime as coverage
    import opportunity_versioned_learning_runtime as versioned
    path=tmp_path/'integration.db'
    def connect():
        conn=sqlite3.connect(path);conn.row_factory=sqlite3.Row;return conn
    monkeypatch.setattr(tracking,'connect',connect)
    monkeypatch.setattr(journal,'connect',connect)
    monkeypatch.setattr(journal,'now',lambda:'2026-10-09T17:00:00Z')
    journal.initialize();tracking._ensure_schema();versioned._ensure_schema()
    monkeypatch.setattr(tracking,'_now',lambda:'2026-10-09T17:02:00Z')
    monkeypatch.setattr(journal,'now',lambda:'2026-10-09T17:03:00Z')
    monkeypatch.setattr(versioned,'_BASE_RECORD',coverage._record_first_observed)
    monkeypatch.setattr(versioned,'_current_identity',lambda:{'signal_version':'v1','signal_fingerprint':'abc','signal_model_id':'v1:abc','learning_policy_id':'policy1'})
    result={'ticker':'TEST','status':'ok','generated_at':'2026-10-09T17:01:00Z','opportunity':{'label':'EARLY_OPPORTUNITY','score':85,'components':{}},'reversal':{'metrics':{'close':100,'close_date':'2026-10-08'}}}
    assert versioned._record_versioned(result,'Test ASA')['emitted'] is True
    assert journal.summary()['signals']==1
    with connect() as c:
        row=c.execute('SELECT * FROM measurement_signals').fetchone()
        assert row['available_at']=='2026-10-09T17:03:00Z'
        assert row['model_id']=='v1:abc'
        assert c.execute('SELECT COUNT(*) FROM measurement_entries').fetchone()[0]==0
