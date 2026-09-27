import json
import sqlite3
from datetime import timedelta

import pytest
import company_context as cc
import company_evidence as evidence
from test_company_context import AT, event, Provider


@pytest.fixture
def db(tmp_path, monkeypatch):
    def connect():
        c = sqlite3.connect(tmp_path/'history.db')
        c.row_factory = sqlite3.Row
        return c
    monkeypatch.setattr(cc, 'connect', connect)
    monkeypatch.setattr(cc, 'now', lambda: AT)
    cc.ensure_schema()
    c = connect()
    c.executescript("CREATE TABLE stocks(ticker TEXT,name TEXT,sector TEXT,active INTEGER); INSERT INTO stocks VALUES('TECH','Techstep ASA','Technology',1);")
    c.commit(); c.close()
    return connect


def test_repeated_capture_deduplicates_but_reversal_is_preserved(db):
    c = db()
    for n, title in enumerate(['A', 'A', 'B', 'A']):
        evidence.record(c, 'doc', 'TECH', 'techstep', 'financing_document',
                        {'title': title, 'document': {'captured_at': str(n)}}, AT+timedelta(hours=n))
    c.commit()
    rows = c.execute('SELECT * FROM company_evidence_versions ORDER BY revision').fetchall()
    assert [json.loads(r['payload'])['title'] for r in rows] == ['A','B','A']
    assert [r['revision'] for r in rows] == [1,2,3]
    c.close()


def test_source_correction_invalidates_terms_and_keeps_previous_version(db):
    c = db()
    first = cc.event_for(event(), {'techstep':['TECH']}, AT)
    first['document'] = {'terms': {'subscription_price': {'value':'NOK 2'}}}
    cc.save_event(c, first, AT)
    # Same feed evidence retains terms and adds no new version.
    cc.save_event(c, cc.event_for(event(), {'techstep':['TECH']}, AT), AT)
    assert c.execute('SELECT COUNT(*) FROM company_evidence_versions').fetchone()[0] == 1
    corrected = cc.event_for(event(title='Cancellation of rights issue'), {'techstep':['TECH']}, AT)
    cc.save_event(c, corrected, AT+timedelta(hours=1))
    c.commit()
    current = json.loads(c.execute('SELECT payload FROM company_context_events').fetchone()[0])
    assert 'document' not in current and current['lifecycle'] == 'cancelled'
    assert json.loads(c.execute('SELECT payload FROM company_evidence_versions WHERE revision=1').fetchone()[0])['document']['terms']
    c.close()
    h = evidence.history(db,'TECH','techstep')
    assert h['entries'][0]['revision'] == 2
    assert 'title' in h['entries'][0]['changed_fields']
    assert evidence.history(db,'TECH','different issuer')['entries'] == []
    old=evidence.version(db,'TECH','techstep','TECH|'+first['url'],1)
    assert old['payload']['document']['terms']['subscription_price']['value']=='NOK 2'
    assert evidence.version(db,'TECH','different issuer','TECH|'+first['url'],1) is None
    assert evidence.version(db,'OTHER','techstep','TECH|'+first['url'],1) is None
    assert evidence.version(db,'TECH','techstep','TECH|'+first['url'],1000) is None


def test_legacy_baseline_not_backdated_and_transaction_rollback(db):
    c = db()
    first = cc.event_for(event(), {'techstep':['TECH']}, AT)
    c.execute('INSERT INTO company_context_events VALUES(?,?,?,?,?)', ('TECH|'+first['url'],'TECH','techstep',json.dumps(first),'2025-01-01'))
    c.commit()
    cc.save_event(c,first,AT)
    c.rollback()
    assert c.execute('SELECT COUNT(*) FROM company_evidence_versions').fetchone()[0] == 0
    cc.save_event(c, first, AT)
    c.commit();c.close()
    h = evidence.history(db,'TECH','techstep')
    assert h['entries'][0]['recorded_at'] == AT.isoformat()
    assert h['entries'][0]['published_at'] != AT.isoformat()


def test_profile_and_history_are_snapshot_reads(db, monkeypatch):
    cc.scan_once(Provider(),lambda:[event()])
    monkeypatch.setattr(cc,'collect_profile',lambda *a:pytest.fail('GET fetched provider'))
    h = cc.context('TECH',identity='Techstep ASA')['evidence_history']
    assert {e['kind'] for e in h['entries']} == {'profile','financing_document'}
    assert cc.context('TECH',identity='Different issuer')['evidence_history']['entries'] == []


def test_history_is_bounded_and_explicit(db):
    c = db()
    for n in range(32):
        evidence.record(c,'doc','TECH','techstep','financing_document',{'title':str(n)},AT+timedelta(seconds=n))
    c.commit();c.close()
    h = evidence.history(db,'TECH','techstep')
    assert len(h['entries']) == 30 and h['truncated']
    assert h['entries'][0]['revision'] == 32
