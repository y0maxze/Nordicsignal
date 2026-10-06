from datetime import datetime, timezone
import sqlite3
import pytest
import company_context as cc
AT=datetime(2026,9,25,15,tzinfo=timezone.utc)
class Provider:
    BASE='https://example.test'
    def _get(self,*a,**k):return {'quoteSummary':{'result':[{'price':{'symbol':'TECH.OL','longName':'Techstep ASA'},'assetProfile':{'longBusinessSummary':'Mobile technology'}}]}}
    def fundamentals(self,ticker):return {'symbol':ticker+'.OL','series':[{'annualTotalDebt':[{'asOfDate':'2025-12-31','reportedValue':100,'currencyCode':'USD'}]}]}
def event(**kw):return dict({'company':'Techstep ASA','title':'Key information relating to rights issue','url':'https://live.euronext.com/en/node/123','official':True,'published_at':'2026-09-17T12:00:00Z'},**kw)
def test_automatic_enrolment_failure_retention_and_no_model_mutation(tmp_path,monkeypatch):
    def connect():
        c=sqlite3.connect(tmp_path/'c.db');c.row_factory=sqlite3.Row;return c
    monkeypatch.setattr(cc,'connect',connect);monkeypatch.setattr(cc,'now',lambda:AT);cc.ensure_schema()
    c=connect();c.executescript("CREATE TABLE stocks(ticker TEXT,name TEXT,sector TEXT,active INTEGER); CREATE TABLE ipo_listings(ticker TEXT,company TEXT,isin TEXT,listing_date TEXT,location TEXT); INSERT INTO stocks VALUES('TECH','Techstep ASA','Technology',1);");c.commit();c.close()
    assert cc.scan_once(Provider(),lambda:[event()])['refreshed']==1
    p=cc.context('TECH',identity='Techstep ASA');assert p['description']=='Mobile technology' and p['financials'][0]['currency']=='USD' and len(p['financing_documents'])==1 and p['score_effect']==0
    c=connect();c.execute("INSERT INTO ipo_listings VALUES('NEW','New company','NO123','2026-09-25','Oslo')");c.commit();c.close()
    assert cc.scan_once(Provider(),lambda:[])['refreshed']==1
    assert cc.context('NEW')['description'] is None
    monkeypatch.setattr(cc,'now',lambda:datetime(2026,9,28,15,tzinfo=timezone.utc))
    class Down(Provider):
        def _get(self,*a,**k):raise RuntimeError()
        def fundamentals(self,*a):raise RuntimeError()
    cc.scan_once(Down(),lambda:[])
    p=cc.context('TECH');assert p['status']=='stale' and p['captured_at']==AT.isoformat() and p['description']=='Mobile technology'
    assert cc.context('TECH',identity='Other issuer')['status']=='collecting'
    c=connect();assert c.execute('SELECT COUNT(*) FROM stocks').fetchone()[0]==1
    c.execute("INSERT INTO ipo_listings VALUES('TECH','Other issuer','NO999','2026-09-01','Oslo')");c.commit();c.close()
    assert 'TECH' not in cc.universe()
def test_strict_event_matching():
    ids={'techstep':['TECH']}
    assert cc.event_for(event(),ids,AT)['kind']=='financing_document'
    for e in [event(company='Techstep subsidiary'),event(url='https://live.euronext.com.evil.test/x'),event(official=False),event(published_at='2026-09-26T00:00:00Z'),event(published_at=None),event(title='New customer contract')]:assert cc.event_for(e,ids,AT) is None
    assert cc.event_for(event(),{'techstep':['TECH','OTHER']},AT) is None
    assert cc.event_for(event(title='Cancellation of rights issue'),ids,AT)
def test_financial_dates_currency_and_invalid_values():
    rows=[{'annualTotalDebt':[{'asOfDate':'2025-12-31','currencyCode':'USD','reportedValue':4},{'asOfDate':'2027-01-01','reportedValue':9}]},{'annualTotalRevenue':[{'asOfDate':'2025-12-31','reportedValue':float('nan')}]},{'annualNetIncome':[{'asOfDate':'2025-12-31','reportedValue':-3}]}]
    facts=cc.project_financials(rows,AT);assert len(facts)==2
    assert next(f for f in facts if f['label']=='Gjeld')['value']==4
    assert next(f for f in facts if f['label']=='Nettoresultat')['currency'] is None

def test_ebitda_is_projected_with_its_own_period_and_currency():
    facts=cc.project_financials([{'annualEBITDA':[{'asOfDate':'2025-12-31','reportedValue':{'raw':-300},'currencyCode':'USD','periodType':'12M'}]}],AT)
    assert facts==[{'label':'EBITDA','value':-300,'currency':'USD','period':'2025-12-31','period_type':'12M'}]

def test_news_issuer_resolution_requires_unique_exact_oslo_equity(tmp_path,monkeypatch):
    def connect():
        c=sqlite3.connect(tmp_path/'names.db');c.row_factory=sqlite3.Row;return c
    monkeypatch.setattr(cc,'connect',connect);monkeypatch.setattr(cc,'universe',lambda:{});cc.ensure_schema()
    class Search:
        BASE='https://example.test'
        def _get(self,*a,**k):return {'quotes':[{'symbol':'TECH.OL','quoteType':'EQUITY','longname':'Techstep ASA'}, {'symbol':'TECH.US','quoteType':'EQUITY','longname':'Techstep ASA'}]}
    cc.enrol_news_issuers([event()],Search(),AT)
    c=connect();assert c.execute('SELECT ticker FROM company_context_issuers').fetchone()[0]=='TECH';c.close()


def test_financing_lifecycle_requires_explicit_title_evidence():
    assert cc.classify_financing('Proposed private placement')[0:2] == ('private_placement','proposed')
    assert cc.classify_financing('Successfully completed private placement')[0:2] == ('private_placement','completed')
    assert cc.classify_financing('Cancellation of rights issue')[0:2] == ('rights_issue','cancelled')
    assert cc.classify_financing('Subscription period opens for rights issue')[0:2] == ('rights_issue','open')
    assert cc.classify_financing('Key information relating to rights issue')[0:2] == ('rights_issue','unknown')
    assert cc.classify_financing('Refinancing update')[0:2] == ('debt_or_refinancing','unknown')

def test_event_exposes_evidence_status_without_claiming_more():
    row=cc.event_for(event(title='Successfully completed private placement'),{'techstep':['TECH']},AT)
    assert row['financing_type']=='private_placement'
    assert row['lifecycle']=='completed'
    unknown=cc.event_for(event(title='Key information relating to rights issue'),{'techstep':['TECH']},AT)
    assert unknown['lifecycle']=='unknown'


@pytest.mark.parametrize('title', [
    'Private placement not completed',
    'Private placement expected to be successfully completed',
    'Proposed cancellation of rights issue',
    'No cancellation of rights issue',
    'Completion of private placement expected tomorrow',
    'Completion of private placement',
    'Final results of rights issue',
    'Fully subscribed rights issue',
    'Rights issue: subscription period opens tomorrow',
    'Rights issue approved by board subject to shareholder approval',
    'Prospectus for rights issue approved by regulator',
    'Rights issue: cancellation of extraordinary general meeting',
    'Successfully completed private placement and proposed subsequent offering',
    'Successfully completed private placement and proposed private placement',
    'Update on successfully completed private placement',
    'Private placement completed subject to settlement',
    'Refinancing: acquisition successfully completed',
    'Rights issue cancelled?',
])
def test_qualified_unrelated_or_multiple_events_remain_unknown(title):
    assert cc.classify_financing(title)[1] == 'unknown'


@pytest.mark.parametrize('title,kind,status', [
    ('Rights issue has been cancelled', 'rights_issue', 'cancelled'),
    ('Private placement successfully completed', 'private_placement', 'completed'),
    ('Rights issue approved by the general meeting', 'rights_issue', 'approved'),
    ('The board has approved the rights issue', 'rights_issue', 'approved'),
    ('Rights issue: subscription period commences', 'rights_issue', 'open'),
    ('Gjennomført rettet emisjon', 'private_placement', 'completed'),
    ('Foreslått reparasjonsemisjon', 'repair_offering', 'proposed'),
    ('Proposed subsequent offering', 'subsequent_offering', 'proposed'),
    ('Convertible bond update', 'convertible', 'unknown'),
    ('Bridge financing update', 'debt_or_refinancing', 'unknown'),
])
def test_types_and_affirmative_templates(title, kind, status):
    assert cc.classify_financing(title) == (kind, status)
    row = cc.event_for(event(title=title), {'techstep':['TECH']}, AT)
    assert row is not None
    assert row['current_status'] == 'unknown'
    assert row['lifecycle_evidence'] == (title if status != 'unknown' else None)


def test_only_verified_issuer_prefix_can_be_removed():
    row = cc.event_for(event(title='Techstep ASA: Successfully completed private placement'), {'techstep':['TECH']}, AT)
    assert row['lifecycle'] == 'completed'
    assert row['lifecycle_evidence'] == 'Successfully completed private placement'
    row = cc.event_for(event(title='Expected: Successfully completed private placement'), {'techstep':['TECH']}, AT)
    assert row['lifecycle'] == 'unknown'
