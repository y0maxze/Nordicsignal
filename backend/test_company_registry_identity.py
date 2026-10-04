"""Issuer metadata may authorize an exact registry lookup, never financials."""
import json
from datetime import timedelta

import pytest
import company_context as cc
import company_registry as cr
import company_newsweb as nw
from test_company_context import AT
from test_company_evidence import db
from test_company_newsweb import raw
from test_company_registry import Provider, payload

ROW={'ticker':'TECH','company':'TECHSTEP','identity':'techstep'}


def document(**changes):
    event=nw.adapt(raw(),{'TECH':ROW},AT)
    return {**event,**changes}


class Down(Provider):
    def _get(self,*a,**kw):
        raise RuntimeError('provider unavailable')
    def fundamentals(self,*a):
        raise AssertionError('unverified financials must not be requested')


def registry(name,at):
    return cr.collect_registry(name,at,lambda _:payload())


def test_official_name_has_document_date_source_and_capture_evidence():
    found=cr.documented_issuer_name(ROW,[document()],AT)
    assert found['legal_name']=='Techstep ASA'
    assert found['published_at']==AT.isoformat()
    assert found['captured_at']==AT.isoformat()
    assert found['source_url']=='https://newsweb.oslobors.no/message/123'
    assert found['source_issuer_id']==7150
    assert found['scope']=='legal_name_for_exact_registry_lookup'


@pytest.mark.parametrize('change',[
    {'source_type':'other'}, {'kind':'other'}, {'ticker':'OTHER'}, {'identity':'other'},
    {'source_message_id':True}, {'source_issuer_id':0},
    {'url':'https://newsweb.oslobors.no.evil.test/message/123'},
    {'company':'Techstep'}, {'company':'Techstep subsidiary ASA'},
    {'title':'Other - Key information relating to rights issue'},
    {'title':'Techstep AS - Key information relating to rights issue'},
    {'title':None}, {'corrected_by_message_id':456}, {'corrected_by_message_id':False},
    {'correction_for_message_id':-1},
    {'published_at':None}, {'published_at':(AT+timedelta(seconds=1)).isoformat()},
    {'published_at':(AT-timedelta(days=180,seconds=1)).isoformat()},
    {'observed_at':None}, {'observed_at':(AT+timedelta(seconds=1)).isoformat()},
    {'observed_at':(AT-timedelta(seconds=1)).isoformat()},
])
def test_unverified_stale_corrected_or_conflicting_document_cannot_supply_name(change):
    assert cr.documented_issuer_name(ROW,[document(**change)],AT)=={'status':'unknown'}


@pytest.mark.parametrize('change',[{'company':'Techstep AS'}, {'source_issuer_id':999}])
def test_conflicting_legal_names_or_issuer_ids_are_ambiguous(change):
    assert cr.documented_issuer_name(ROW,[document(),document(**change)],AT)=={'status':'ambiguous'}


def test_multiple_documents_for_same_issuer_choose_latest_publication_not_scan_time():
    old=document(published_at=(AT-timedelta(days=1)).isoformat(),source_message_id=124,
                 url='https://newsweb.oslobors.no/message/124')
    assert cr.documented_issuer_name(ROW,[document(),old],AT)['source_url'].endswith('/123')


def test_document_limit_cannot_silently_truncate_identity_conflicts():
    assert cr.documented_issuer_name(ROW,[document()]*501,AT)=={'status':'unavailable','reason':'document_limit'}


def test_official_issuer_name_restores_registry_when_yahoo_is_unavailable(monkeypatch):
    monkeypatch.setattr(cc,'now',lambda:AT)
    result=cc.collect_profile(ROW,Down(),registry,[document()])
    assert result['description']=='Registered technology activity.'
    assert result['registry']['identity_evidence']['source_url'].endswith('/123')
    assert result['field_sources']['description']['source']==cr.SOURCE
    assert result['yahoo_identity_verified'] is False and result['financials']==[]


def test_ambiguous_identity_never_uses_provider_fallback_or_retains_old_registry(monkeypatch):
    monkeypatch.setattr(cc,'now',lambda:AT)
    previous=cc.collect_profile(ROW,Down(),registry,[document()])
    def forbidden(*args):
        raise AssertionError('must not query a registry identity that is ambiguous')
    fresh=cc.collect_profile(ROW,Down(),forbidden,[document(),document(company='Techstep AS')])
    assert fresh['source_status']['registry']=='identity_ambiguous'
    retained=cc.retain_profile_fields(fresh,{'payload':json.dumps(previous)},AT)
    assert not retained.get('registry') and retained['description'] is None


def test_collector_uses_saved_evidence_but_get_never_fetches_sources(db,monkeypatch):
    c=db()
    c.execute("UPDATE stocks SET name='TECHSTEP' WHERE ticker='TECH'")
    cc.save_event(c,document(),AT)
    c.commit();c.close()
    calls=[]
    def lookup(name,at):
        calls.append(name)
        return registry(name,at)
    assert cc.scan_once(Down(),lambda:[],registry=lookup)['refreshed']==1
    assert calls==['Techstep ASA']
    result=cc.context('TECH')
    assert result['registry']['official_name']=='TECHSTEP ASA'
    assert result['registry']['identity_evidence']['source_issuer_id']==7150
    assert result['score_effect']==0 and result['financials']==[]
    assert calls==['Techstep ASA']


def test_identity_upgrade_revisits_recent_legacy_snapshot_once_within_batch_limit(db):
    c=db()
    c.execute("UPDATE stocks SET name='TECHSTEP' WHERE ticker='TECH'")
    cc.save_event(c,document(),AT)
    old={'company':'TECHSTEP','ticker':'TECH','description':None,'financials':[]}
    c.execute('INSERT INTO company_context_profiles VALUES(?,?,?,?,?,?)',
              ('TECH','techstep',json.dumps(old),AT.isoformat(),None,'unavailable'))
    c.commit();c.close()
    assert cc.scan_once(Down(),lambda:[],registry=registry,batch_size=0)['refreshed']==0
    assert cc.scan_once(Down(),lambda:[],registry=registry,batch_size=1)['refreshed']==1
    assert cc.context('TECH')['registry_identity_version']==cc.REGISTRY_IDENTITY_VERSION
    assert cc.scan_once(Down(),lambda:[],registry=registry,batch_size=1)['refreshed']==0
