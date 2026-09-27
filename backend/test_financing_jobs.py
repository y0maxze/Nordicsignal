import json
from datetime import timedelta

import financing_jobs as jobs
import financing_documents as fd
import company_context as cc
from test_company_evidence import db
from test_company_context import AT, event
from test_financing_documents import page, TERMS


def test_lease_exclusion_restart_recovery_and_late_result(db):
    token = jobs.claim(db,'doc',AT)
    assert token and jobs.claim(db,'doc',AT) is None
    later = AT+timedelta(minutes=4)
    replacement = jobs.claim(db,'doc',later)
    assert replacement and replacement != token
    c = db()
    assert not jobs.finish(c,'doc',token,'partial',later)
    assert jobs.finish(c,'doc',replacement,'unavailable',later)
    c.commit();c.close()
    assert jobs.summary(db) == {'unavailable':1}


def seed(db):
    e = cc.event_for(event(),{'techstep':['TECH']},AT)
    c=db();cc.save_event(c,e,AT);c.commit();c.close()
    return e


def test_correction_during_fetch_cannot_restore_old_terms(db):
    seed(db)
    def fetch(url):
        c=db()
        cc.save_event(c, cc.event_for(event(title='Cancellation of rights issue'),{'techstep':['TECH']},AT), AT)
        c.commit();c.close()
        return page(TERMS)
    fd.enrich_saved(db,AT,fetch=fetch)
    p=cc.context('TECH',identity='Techstep ASA')
    assert p['financing_documents'][0]['lifecycle']=='cancelled'
    assert 'document' not in p['financing_documents'][0]
    assert jobs.summary(db)=={'superseded':1}


def test_failed_source_retains_terms_and_retries_next_day(db):
    seed(db)
    fd.enrich_saved(db,AT,fetch=lambda url:page(TERMS))
    later=AT+timedelta(days=8)
    def down(url): raise RuntimeError('unavailable')
    fd.enrich_saved(db,later,fetch=down,clock=lambda:later)
    c=db();doc=json.loads(c.execute('SELECT payload FROM company_context_events').fetchone()[0])['document'];c.close()
    assert doc['status']=='stale' and doc['terms']
    assert fd.enrich_saved(db,later+timedelta(hours=1),fetch=down,clock=lambda:later)['processed']==0
    tomorrow=later+timedelta(days=1)
    assert fd.enrich_saved(db,tomorrow,fetch=down,clock=lambda:tomorrow)['processed']==1


def test_expired_job_does_not_publish_and_changed_snapshot_not_claimed(db):
    e=seed(db)
    key='TECH|'+e['url']
    assert jobs.claim(db,key,AT,'wrong snapshot') is None
    times=iter([AT,AT+timedelta(minutes=4)])
    fd.enrich_saved(db,AT,fetch=lambda url:page(TERMS),clock=lambda:next(times))
    c=db();payload=json.loads(c.execute('SELECT payload FROM company_context_events').fetchone()[0]);c.close()
    assert 'document' not in payload
    assert jobs.claim(db,key,AT+timedelta(minutes=4))


def test_health_reports_job_counts_without_payloads(db, monkeypatch):
    import system_health_runtime as health
    monkeypatch.setattr(health,'connect',db)
    jobs.claim(db,'private-document-url',AT)
    result=health.system_health()['financing_jobs']
    assert result=={'status':'available','states':{'running':1}}
    assert 'private-document-url' not in json.dumps(result)
