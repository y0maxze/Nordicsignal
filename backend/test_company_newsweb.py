import json
from datetime import timedelta

import pytest
import company_newsweb as nw
import company_context as cc
import financing_documents as fd
from test_company_evidence import db
from test_company_context import AT

UNIVERSE={'TECH':{'company':'Techstep ASA','identity':'techstep','ticker':'TECH'}}


def raw(**changes):
    return {**{'id':123,'messageId':123,'issuerId':7150,'issuerSign':'TECH',
               'issuerName':'Techstep ASA','title':'Techstep - Key information relating to rights issue',
               'publishedTime':AT.isoformat(),'test':False,'markets':['XOSL'],
               'correctionForMessageId':0,'correctedByMessageId':0,
               'body':'Subscription price: NOK 1\nMaximum number of new shares: 1000000'},**changes}


@pytest.mark.parametrize('changes',[
    {'title':'BerGenBio ASA - Key information relating to rights issue'},
    {'issuerName':'Techstep AS'}, {'title':'Techstep AS - Key information relating to rights issue'},
    {'issuerSign':'OTHER'}, {'test':True}, {'markets':['XNYS']},
    {'issuerId':None}, {'messageId':True}, {'publishedTime':None},
    {'publishedTime':(AT+timedelta(days=1)).isoformat()}, {'correctedByMessageId':None},
])
def test_strict_issuer_title_and_ticker_binding(changes):
    assert nw.adapt(raw(**changes),UNIVERSE,AT) is None


def test_historical_announcement_and_correction_are_explicit_not_reconstructed():
    old=AT-timedelta(days=500)
    event=nw.adapt(raw(publishedTime=old.isoformat(),correctedByMessageId=456),UNIVERSE,AT)
    assert event['published_at']==old.isoformat() and event['corrected_by_message_id']==456
    assert event['current_status']=='unknown' and event['lifecycle']=='unknown'


def test_verified_document_body_and_missing_denominator():
    event=nw.adapt(raw(),UNIVERSE,AT)
    result=fd.collect(event,AT,fetch=lambda kind,params:{'message':raw()})
    assert result['terms']['subscription_price']['value']=='NOK 1'
    assert result['dilution']['status']=='unknown'
    assert result['source_url']=='https://newsweb.oslobors.no/message/123'
    assert len(result['content_sha256'])==64


@pytest.mark.parametrize('changes',[{'id':456},{'issuerId':1},{'issuerSign':'OTHER'},
    {'issuerName':'Different ASA'},{'publishedTime':'2020-01-01T12:00:00Z'},
    {'correctedByMessageId':456},{'title':'Changed rights issue'},{'test':True},{'body':None}])
def test_document_mismatch_never_contributes_terms(changes):
    result=fd.collect(nw.adapt(raw(),UNIVERSE,AT),AT,fetch=lambda *a:{'message':raw(**changes)})
    assert result['status']=='unavailable' and not result['terms']


def test_bounded_scan_retains_failure_and_discloses_overflow(db):
    calls=[]
    def fetch(kind,params):
        calls.append(params)
        return {'messages':[raw()],'overflow':True}
    result=nw.scan(db,UNIVERSE,AT,fetch,clock=lambda:AT)
    assert result['status']=='truncated' and result['matched']==1 and len(calls)==1
    p=cc.context('TECH',identity='Techstep ASA')
    assert p['financing_documents'][0]['source_message_id']==123
    assert p['financing_coverage']['truncated_days']==1
    def down(*a):raise RuntimeError()
    nw.scan(db,UNIVERSE,AT,down,clock=lambda:AT)
    coverage=nw.coverage(db)
    assert coverage['queried_days']==2 and coverage['failed_days']==1
    assert cc.context('TECH',identity='Techstep ASA')['financing_document_count']==1


def test_interrupted_window_recovers_after_lease_expiry(db):
    day=AT.date().isoformat();c=db()
    c.execute('INSERT INTO company_newsweb_windows VALUES(?,?,?,?,?)',(day,AT.isoformat(),'old',(AT+timedelta(minutes=3)).isoformat(),None));c.commit();c.close()
    later=AT+timedelta(minutes=4)
    result=nw.scan(db,UNIVERSE,later,lambda *a:{'messages':[],'overflow':False},clock=lambda:later)
    assert result['day']==day and result['status']=='partial'
    assert nw.coverage(db)['queried_days']==1


def test_expired_window_cannot_commit_source_events(db):
    result=nw.scan(db,UNIVERSE,AT,lambda *a:{'messages':[raw()],'overflow':False},clock=lambda:AT+timedelta(minutes=4))
    assert result['status']=='lease_lost' and result['matched']==0
    assert cc.context('TECH',identity='Techstep ASA')['financing_document_count']==0


def test_foreign_date_and_renamed_issuer_are_not_silently_imported(db):
    result=nw.scan(db,UNIVERSE,AT,lambda *a:{'messages':[raw(publishedTime=(AT-timedelta(days=1)).isoformat()),raw(title='Different ASA - Key information relating to rights issue')],'overflow':False},clock=lambda:AT)
    assert result['matched']==0 and result['rejected_dates']==1


def test_multiple_share_tickers_for_same_issuer_do_not_choose_one():
    assert nw.adapt(raw(),{**UNIVERSE,'TECHB':UNIVERSE['TECH']},AT) is None
