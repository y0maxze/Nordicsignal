from datetime import datetime,timezone
import json
import pytest
import company_registry as cr
import company_context as cc

AT=datetime(2026,9,27,18,tzinfo=timezone.utc)
ROW={'ticker':'TECH','company':'Techstep ASA','identity':'techstep'}
ENTITY={'navn':'TECHSTEP ASA','organisasjonsnummer':'977037093','organisasjonsform':{'kode':'ASA'},'aktivitet':['Registered technology','activity.'],'naeringskode1':{'kode':'62.200','beskrivelse':'Technology consulting'}}

def payload(rows=None,**page):
    rows=[ENTITY] if rows is None else rows
    return {'_embedded':{'enheter':rows},'page':{'number':0,'totalElements':len(rows),'totalPages':1,**page}}


def test_exact_legal_identity_source_and_activity_only():
    result=cr.collect_registry('Techstep ASA',AT,lambda _:payload())
    assert result['official_name']=='TECHSTEP ASA'
    assert result['registered_activity']=='Registered technology activity.'
    assert result['source_url'].endswith('/977037093') and result['license']=='NLOD 2.0'
    assert result['captured_at']==AT.isoformat()
    assert result['scope']=='registered_activity_not_a_consolidated_group_description'
    assert 'financials' not in result


@pytest.mark.parametrize('name', ['Techstep','BW LPG Limited','Techstep subsidiary ASA','Techstep AS'])
def test_no_suffix_guessing_parent_subsidiary_or_legal_form_substitution(name):
    assert cr.collect_registry(name,AT,lambda _:payload()) is None


@pytest.mark.parametrize('data', [payload([ENTITY,ENTITY]),payload(totalPages=2),payload(number=1),payload(totalElements=2),payload([{**ENTITY,'slettedato':'2026-01-01'}]),payload([{**ENTITY,'organisasjonsnummer':'123'}])])
def test_ambiguous_incomplete_deleted_or_invalid_registry_is_rejected(data):
    assert cr.collect_registry('Techstep ASA',AT,lambda _:data) is None


class Provider:
    BASE='https://example.test'
    def _get(self,*a,**kw):
        return {'quoteSummary':{'result':[{'price':{'symbol':'TECH.OL','longName':'Techstep ASA'},'assetProfile':{'longBusinessSummary':'Yahoo description'}}]}}
    def fundamentals(self,ticker):
        return {'symbol':'TECH.OL','series':[{'annualTotalDebt':[{'asOfDate':'2025-12-31','reportedValue':100,'currencyCode':'NOK'}]}]}


def test_official_activity_has_own_source_financials_retain_yahoo_source(monkeypatch):
    monkeypatch.setattr(cc,'now',lambda:AT)
    result=cc.collect_profile(ROW,Provider(),lambda name,at:cr.collect_registry(name,at,lambda _:payload()))
    assert result['description']=='Registered technology activity.'
    assert result['description_kind']=='registered_activity'
    assert result['field_sources']['description']['source']==cr.SOURCE
    assert result['field_sources']['financials']['source']=='Yahoo Finance'
    assert result['financials'][0]['currency']=='NOK'
    assert result['yahoo_identity_verified'] is True


def test_wrong_issuer_cannot_supply_fundamentals_even_with_matching_ticker():
    class Wrong(Provider):
        def _get(self,*a,**kw):return {'quoteSummary':{'result':[{'price':{'symbol':'TECH.OL','longName':'Other issuer ASA'}}]}}
        def fundamentals(self,ticker):raise AssertionError('Must not call unverified financials')
    result=cc.collect_profile(ROW,Wrong())
    assert result['financials']==[] and not result['description']
    assert result['yahoo_identity_verified'] is False


def test_official_source_can_supply_missing_description_without_authorizing_yahoo_financials():
    class Down(Provider):
        def _get(self,*a,**kw):raise RuntimeError('unavailable')
        def fundamentals(self,*a):raise AssertionError('must not call')
    result=cc.collect_profile(ROW,Down(),lambda name,at:cr.collect_registry(name,at,lambda _:payload()))
    assert result['description']=='Registered technology activity.' and not result['financials']


def test_partial_failure_retains_independent_fields_and_capture_times(monkeypatch):
    monkeypatch.setattr(cc,'now',lambda:AT)
    previous=cc.collect_profile(ROW,Provider())
    previous['field_sources']['description']['captured_at']='2026-09-01T00:00:00+00:00'
    old={'payload':json.dumps(previous),'captured_at':'2026-09-01T00:00:00+00:00'}
    fresh={**previous,'description':None,'source_status':{'description':'unavailable','financials':'stored'},'field_sources':dict(previous['field_sources'])}
    result=cc.retain_profile_fields(fresh,old,AT)
    assert result['description']=='Yahoo description'
    assert result['field_sources']['description']['status']=='stale'
    assert result['field_sources']['description']['captured_at']=='2026-09-01T00:00:00+00:00'
    assert result['field_sources']['financials']['status']=='stored'


def test_legacy_unverified_financials_are_not_retained(monkeypatch):
    monkeypatch.setattr(cc,'now',lambda:AT)
    previous=cc.collect_profile(ROW,Provider());previous.pop('yahoo_identity_verified')
    old={'payload':json.dumps(previous),'captured_at':AT.isoformat()}
    fresh={**previous,'financials':[],'source_status':{},'field_sources':{}}
    assert cc.retain_profile_fields(fresh,old,AT)['financials']==[]


def test_legal_name_and_isin_conflicts_never_resolve_silently(tmp_path,monkeypatch):
    import sqlite3
    def connect():
        c=sqlite3.connect(tmp_path/'u.db');c.row_factory=sqlite3.Row;return c
    monkeypatch.setattr(cc,'connect',connect);cc.ensure_schema()
    c=connect();c.executescript("CREATE TABLE stocks(ticker TEXT,name TEXT,sector TEXT,active INTEGER); CREATE TABLE ipo_listings(ticker TEXT,company TEXT,isin TEXT,listing_date TEXT,location TEXT); INSERT INTO stocks VALUES('TECH','Techstep ASA','Technology',1);")
    c.execute('INSERT INTO ipo_listings VALUES(?,?,?,?,?)',('TECH','Techstep ASA','NO0010096985','2025-01-01','Oslo'));c.commit();c.close()
    assert cc.universe()['TECH']['isin']=='NO0010096985'
    c=connect();c.execute('INSERT INTO ipo_listings VALUES(?,?,?,?,?)',('TECH','Techstep ASA','NO0010096993','2025-01-01','Oslo'));c.commit();c.close()
    assert cc.universe()['TECH']['isin'] is None and cc.universe()['TECH']['isin_status']=='ambiguous'
    c=connect();c.execute("UPDATE ipo_listings SET company='Techstep AS'");c.commit();c.close()
    assert 'TECH' not in cc.universe()
