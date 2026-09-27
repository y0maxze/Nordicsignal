from datetime import datetime, timezone, timedelta
import json
import sqlite3
import pytest
import company_context as cc
import financing_documents as fd

AT = datetime(2026, 9, 27, 18, tzinfo=timezone.utc)
EVENT = {'ticker':'TECH', 'identity':'techstep', 'company':'Techstep ASA',
         'title':'Key information relating to rights issue',
         'url':'https://live.euronext.com/en/node/123',
         'published_at':'2026-09-17T12:00:00+00:00', 'financing_type':'rights_issue'}


def page(lines, title=EVENT['title'], issuer='Techstep ASA'):
    return '<h1>'+title+'</h1><h3>Issuer</h3><p><span>'+issuer+'</span></p>'+''.join('<p>'+line+'</p>' for line in lines)


TERMS = ['Subscription price: NOK 0.50', 'Number of new shares in the rights issue: 1,000,000',
         'Number of existing shares before the rights issue: 4,000,000',
         'Class of existing and new shares: Ordinary shares', 'Record Date: 4 June 2026',
         'Subscription period: Expected 5–19 June 2026, subject to approval']


def test_terms_preserve_qualifications_evidence_currency_and_dates():
    d=fd.collect(EVENT,AT,fetch=lambda _:page(TERMS))
    assert d['status']=='partial'
    assert d['terms']['subscription_price']['value']=='NOK 0.50'
    assert d['terms']['record_date']['value']=='4 June 2026'
    assert d['terms']['subscription_period']['value'].startswith('Expected')
    assert d['terms']['subscription_period']['evidence'].endswith('subject to approval')
    assert 'net_proceeds' not in d['terms']
    assert d['published_at']==EVENT['published_at'] and d['captured_at']==AT.isoformat()
    assert len(d['content_sha256'])==64
    assert d['dilution']['percentage']=='20.0000'
    assert d['dilution']['new_shares']==1000000
    assert 'Dokumentscenario' in d['dilution']['limitation']


@pytest.mark.parametrize('replacement', ['up to 1,000,000','1.000.000','1,000,000–2,000,000','approximately 1,000,000','1000000.0','0','-1','1000000000000000000000'])
def test_dilution_never_uses_nonexact_counts(replacement):
    d=fd.collect(EVENT,AT,fetch=lambda _:page([x.replace('1,000,000',replacement) for x in TERMS]))
    assert d['dilution']['status']=='unknown'


@pytest.mark.parametrize('removed', ['Number of new shares in the rights issue:', 'Number of existing shares before the rights issue:', 'Class of existing and new shares:'])
def test_dilution_requires_all_compatible_inputs(removed):
    d=fd.collect(EVENT,AT,fetch=lambda _:page([x for x in TERMS if not x.startswith(removed)]))
    assert d['dilution']['status']=='unknown'


def test_maximum_secondary_or_generic_counts_are_not_denominators():
    lines=['Maximum number of new shares: 1000000', 'Existing shares offered: 4000000', 'Class of existing and new shares: Ordinary shares']
    d=fd.collect(EVENT,AT,fetch=lambda _:page(lines))
    assert d['dilution']['status']=='unknown'
    d=fd.collect(EVENT,AT,fetch=lambda _:page([x.replace('Number of new shares in the rights issue:', 'Number of new shares:') for x in TERMS]))
    assert d['dilution']['status']=='unknown'


def test_duplicate_labels_fail_closed_even_if_values_agree():
    for extra in ['Subscription price: NOK 0.75','Subscription price: NOK 0.50']:
        d=fd.collect(EVENT,AT,fetch=lambda _:page(TERMS+[extra]))
        assert d['terms']['subscription_price']['status']=='ambiguous'
        assert d['terms']['subscription_price']['value'] is None


@pytest.mark.parametrize('html', [page(TERMS,issuer='Other issuer ASA'),page(TERMS,title='Another rights issue'),'<h1>JavaScript is disabled</h1>',page(TERMS)+'<h1>Second title</h1>'])
def test_document_identity_or_challenge_failure_is_unavailable(html):
    assert fd.collect(EVENT,AT,fetch=lambda _:html)['status']=='unavailable'


def test_scripts_never_supply_facts_and_source_line_wrapping_is_preserved():
    html=page(['Subscription period: Expected\n5–19 June,\nsubject to approval'])+'<script>Net proceeds: NOK 100</script>'
    d=fd.collect(EVENT,AT,fetch=lambda _:html)
    assert d['terms']['subscription_period']['value']=='Expected 5–19 June, subject to approval'
    assert 'net_proceeds' not in d['terms']


@pytest.mark.parametrize('url', ['https://evil.test/en/node/123','https://live.euronext.com.evil.test/en/node/123','http://live.euronext.com/en/node/123','https://user:pass@live.euronext.com/en/node/123','https://live.euronext.com:444/en/node/123','https://live.euronext.com/en/node/123?redirect=evil','https://live.euronext.com/en/node/123#x','https://live.euronext.com/other'])
def test_source_rejection_happens_before_network(url):
    calls=[]
    assert fd.collect({**EVENT,'url':url},AT,fetch=lambda u:calls.append(u))['status']=='unavailable'
    assert not calls


def test_failure_retention_and_no_cross_document_reuse():
    old=fd.collect(EVENT,AT,fetch=lambda _:page(TERMS))
    def down(_): raise RuntimeError('down')
    retained=fd.collect(EVENT,AT+timedelta(days=1),old,down)
    assert retained['status']=='stale' and retained['captured_at']==old['captured_at']
    assert retained['attempted_at']!=old['attempted_at']
    assert retained['terms']==old['terms']
    other=fd.collect({**EVENT,'url':'https://live.euronext.com/en/node/124'},AT,old,down)
    assert other['status']=='unavailable' and not other['terms']


def test_background_bound_idempotence_and_get_retains_history(tmp_path,monkeypatch):
    def connect():
        c=sqlite3.connect(tmp_path/'docs.db');c.row_factory=sqlite3.Row;return c
    monkeypatch.setattr(cc,'connect',connect);monkeypatch.setattr(cc,'now',lambda:AT)
    cc.ensure_schema()
    c=connect()
    for i in range(3):
        event={**EVENT,'url':f'https://live.euronext.com/en/node/{i}','observed_at':AT.isoformat()}
        c.execute('INSERT INTO company_context_events VALUES(?,?,?,?,?)',(str(i),'TECH','techstep',json.dumps(event),AT.isoformat()))
    # Older evidence must remain accessible; no fabricated active status.
    event={**EVENT,'published_at':'2025-01-01T12:00:00+00:00','observed_at':AT.isoformat()}
    c.execute('INSERT INTO company_context_events VALUES(?,?,?,?,?)',('old','TECH','techstep',json.dumps(event),AT.isoformat()))
    c.commit();c.close()
    calls=[]
    def fetch(url):calls.append(url);return page(TERMS)
    fd.enrich_saved(connect,AT,limit=2,fetch=fetch)
    assert len(calls)==2
    fd.enrich_saved(connect,AT,limit=2,fetch=fetch)
    assert len(calls)==4
    fd.enrich_saved(connect,AT,limit=2,fetch=fetch)
    assert len(calls)==4
    p=cc.context('TECH',identity='Techstep ASA')
    assert len(calls)==4 and p['financing_document_count']==4
    assert p['financing_documents'][-1]['published_at'].startswith('2025')
    assert all(e['current_status']=='unknown' for e in p['financing_documents'])
    assert not p['financing_documents_truncated']


def test_context_reports_display_limit():
    events=[{**EVENT,'identity':'techstep'} for _ in range(21)]
    p=cc.context('TECH',({}, {'TECH':events}, {}),identity='Techstep ASA')
    assert len(p['financing_documents'])==20
    assert p['financing_document_count']==21 and p['financing_documents_truncated']
