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


def test_wrapped_qualifiers_cannot_be_lost_before_a_calculation():
    lines=[x.replace('1,000,000','1,000,000<br>subject to final allocation') for x in TERMS]
    d=fd.collect(EVENT,AT,fetch=lambda _:page(lines))
    assert d['terms']['new_shares']['value'].endswith('subject to final allocation')
    assert d['dilution']['status']=='unknown'


@pytest.mark.parametrize('qualification', ['Condition: subject to final allocation', 'Note: maximum number, subject to approval', 'https://example.test/conditions: additional restrictions'])
def test_colon_in_unknown_continuation_never_discards_qualifications(qualification):
    lines=[x.replace('1,000,000','1,000,000</p><p>'+qualification) for x in TERMS]
    d=fd.collect(EVENT,AT,fetch=lambda _:page(lines))
    assert qualification in d['terms']['new_shares']['value']
    assert d['dilution']['status']=='unknown'


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

def test_old_parser_evidence_is_withheld_and_not_retained_after_failure():
    old=fd.collect(EVENT,AT,fetch=lambda _:page(TERMS))
    old['version']=1
    public=fd.public_document(old)
    assert public['status']=='revalidation_required' and public['terms']=={}
    assert public['dilution']['status']=='unknown'
    assert old['terms'] and old['dilution']['status']=='calculated'
    def down(url): raise RuntimeError('unavailable')
    result=fd.collect(EVENT,AT,old,down)
    assert result['version']==fd.VERSION and result['terms']=={} and not result['captured_at']


NORWEGIAN_TITLE = 'Nøkkelinformasjon ved fortrinnsrettsemisjon – oppdatert'


def test_norwegian_official_template_preserves_distinct_terms_without_calculation():
    # Synthetic values; field labels follow Euronext notice 4.3.5.2A.
    lines = [
        'Dato for når vilkårene for fortrinnsrettsemisjonen ble annonsert: 2 desember 2023',
        'Siste dag inklusive: 23 desember 2023',
        'Ex-dato: 27 desember 2024',
        'Record date (eierregisterdato): 30 desember 2024',
        'Vedtaksdato: 23 desember 2024',
        'Maksimalt antall nye aksjer: 2 000 000',
        'Tegningskurs: NOK 0,015',
        'Tildelingsforhold: 2,5 fortrinnsretter per gammel aksje',
        'avrundet ned til nærmeste hele tegningsrett',
        'Tegningsforhold: 1:1 (antall nye aksjer per tegningsrett)',
        'Tilrettelegger: Eksempel ASA',
        'Oppgjørsagent: Annet Eksempel ASA',
        'Skal rettene noteres ja/nei: Selskapet vil søke om notering',
        'ISIN på fortrinnsrettene: Vil annonseres',
        'Tegningsperiode: Forventet 5.–19. januar 2025',
        'Tegningsfrist: 19. januar 2025 kl. 16:30',
        'Øvrig informasjon (valgfritt): Betinget av generalforsamlingens godkjennelse',
    ]
    event = {**EVENT, 'title': NORWEGIAN_TITLE}
    html = page(lines, title=NORWEGIAN_TITLE).replace('<h3>Issuer</h3>', '<h3>Utsteder</h3>')
    d = fd.collect(event, AT, fetch=lambda _: html)
    terms = d['terms']
    assert d['status'] == 'partial'
    assert terms['subscription_price']['value'] == 'NOK 0,015'
    assert terms['maximum_new_shares']['value'] == '2 000 000'
    assert 'new_shares' not in terms and d['dilution']['status'] == 'unknown'
    assert terms['allocation_ratio']['value'].endswith('avrundet ned til nærmeste hele tegningsrett')
    assert terms['subscription_ratio']['value'] == '1:1 (antall nye aksjer per tegningsrett)'
    assert 'subscription_rights' not in terms
    assert terms['arranger']['value'] == 'Eksempel ASA'
    assert terms['settlement_agent']['value'] == 'Annet Eksempel ASA'
    assert terms['rights_isin']['value'] == 'Vil annonseres'
    assert terms['rights_listing']['value'] == 'Selskapet vil søke om notering'
    assert terms['announcement_date']['value'].endswith('2023')  # Do not repair source dates.
    assert terms['ex_date']['value'].endswith('2024')
    assert terms['subscription_deadline']['value'].endswith('16:30')
    assert 'Betinget' in terms['additional_information']['evidence']
    assert 'lifecycle' not in d


@pytest.mark.parametrize('title', [
    'Nøkkelinformasjon ved fortrinnsrettsemisjon og rettet emisjon',
    'Fortrinnsrettsemisjon',
    'Nøkkelinformasjon ved utbytte',
])
def test_norwegian_title_gate_rejects_compound_and_unsupported_notices(title):
    assert not fd.supported_title(title)
    calls = []
    assert fd.collect({**EVENT, 'title': title}, AT, fetch=lambda u: calls.append(u))['status'] == 'unsupported_document'
    assert not calls


def test_norwegian_alias_duplicates_are_ambiguous_and_conflicting_issuers_fail():
    event = {**EVENT, 'title': NORWEGIAN_TITLE}
    html = page(['Tegningskurs: NOK 1', 'Subscription price: NOK 1'], title=NORWEGIAN_TITLE)
    assert fd.collect(event, AT, fetch=lambda _: html)['terms']['subscription_price']['status'] == 'ambiguous'
    html += '<h3>Utsteder</h3><p>Other ASA</p>'
    assert fd.collect(event, AT, fetch=lambda _: html)['status'] == 'unavailable'


def test_parser_v2_is_withheld_until_revalidated_and_failure_does_not_resurrect_it():
    old = {'version': 2, 'captured_at': AT.isoformat(), 'source_url': EVENT['url'],
           'published_at': EVENT['published_at'], 'terms': {'subscription_price': {'value': 'NOK 1'}}}
    assert fd.public_document(old)['status'] == 'revalidation_required'
    assert fd.public_document(old)['terms'] == {}
    def fail(_):
        raise ValueError('unavailable')
    result = fd.collect(EVENT, AT, previous=old, fetch=fail)
    assert result['status'] == 'unavailable' and result['terms'] == {}


@pytest.mark.parametrize('bullet', ['- ', '* ', '• '])
def test_bulleted_wrapped_official_labels_keep_values_conditions_and_evidence(bullet):
    lines = [
        bullet + 'Date on which the terms and conditions of the Subsequent Offering were',
        'announced: 2 June 2026',
        bullet + 'Last day including rights: 1 June 2026',
        bullet + 'Ex-date: 2 June 2026',
        bullet + 'Record date: 3 June 2026',
        bullet + 'Expected date of approval: Subject to a final board resolution',
        'and publication of a prospectus',
        bullet + 'Maximum number of new shares: 500,000',
        bullet + 'Subscription price: NOK 1',
        'Any offer remains conditional; the board may decide not to proceed.',
    ]
    terms, status = fd.parse_lines(lines)
    assert status == 'partial'
    assert terms['announcement_date']['value'] == '2 June 2026'
    assert terms['announcement_date']['evidence'].startswith(bullet)
    assert terms['record_date']['value'] == '3 June 2026'
    assert terms['expected_decision_date']['value'].endswith('publication of a prospectus')
    assert terms['subscription_price']['value'].endswith('may decide not to proceed.')
    assert terms['maximum_new_shares']['value'] == '500,000'
    assert fd.dilution(terms, EVENT)['status'] == 'unknown'


def test_live_english_rights_ratios_and_decision_dates_remain_distinct():
    terms, _ = fd.parse_lines([
        'Record Date: 3 June 2026', 'Date of approval: 1 June 2026',
        'Ratio preferential rights: Approximately 2.5 per existing share',
        'rounded down to whole rights', 'Subscription ratio: 1:1',
        'Manager: Example Bank', 'Will the rights be listed: Application planned',
        'ISIN for the preferential rights: To be announced',
        'Other information: Subject to shareholder approval',
    ])
    assert terms['record_date']['value'] == '3 June 2026'
    assert terms['decision_date']['value'] == '1 June 2026'
    assert terms['allocation_ratio']['value'].endswith('rounded down to whole rights')
    assert terms['subscription_ratio']['value'] == '1:1'
    assert terms['additional_information']['value'] == 'Subject to shareholder approval'
    assert all(t['status'] == 'documented' for t in terms.values())


def test_bullets_do_not_strip_unknown_qualifications_or_hide_duplicate_labels():
    lines = ['Number of new shares in the rights issue: 1000',
             '- Condition: subject to allocation',
             'Number of existing shares before the rights issue: 4000',
             'Class of existing and new shares: Ordinary shares']
    terms, _ = fd.parse_lines(lines)
    assert '- Condition: subject to allocation' in terms['new_shares']['value']
    assert fd.dilution(terms, EVENT)['status'] == 'unknown'
    terms, _ = fd.parse_lines(['* Subscription price: NOK 1', '- Subscription price: NOK 1'])
    assert terms['subscription_price']['status'] == 'ambiguous'
    terms, _ = fd.parse_lines(['Not Subscription price: NOK 1', '** Subscription price: NOK 1'])
    assert terms == {}


def test_v3_extraction_waits_for_new_parser_without_mutating_stored_evidence():
    old = {'version': 3, 'terms': {'record_date': {'value': 'date mixed with approval date'}}}
    public = fd.public_document(old)
    assert public['status'] == 'revalidation_required' and public['terms'] == {}
    assert old['terms']


def test_singular_right_and_shall_listing_aliases_do_not_pollute_nearby_values():
    terms, _ = fd.parse_lines(['Date on which the terms and conditions of the Subsequent Offering were',
                              'announced: 1 June 2026', 'Last day including right: 2 June 2026',
                              'Subscription price: NOK 2 per share', 'Shall the rights be listed: No',
                              'Other information: Subject to a prospectus'])
    assert terms['announcement_date']['value'] == '1 June 2026'
    assert terms['subscription_price']['value'] == 'NOK 2 per share'
    assert terms['rights_listing']['value'] == 'No'


@pytest.mark.parametrize('bullet', ['-', '*', '•', '·', '- ', '* ', '• ', '· '])
def test_compact_list_markers_preserve_exact_labels_and_qualifications(bullet):
    terms, status = fd.parse_lines([
        bullet + 'Date on which the terms and conditions of the subsequent offering were',
        'announced: 1 June 2026',
        bullet + 'Last day including right: 1 June 2026',
        bullet + 'Ex-date: 2 June 2026',
        bullet + 'Record date: 3 June 2026',
        bullet + 'Maximum number of new shares: up to 500,000',
        bullet + 'Subscription price: NOK 1',
        'The offering remains subject to approval.',
    ])
    assert status == 'partial'
    assert terms['announcement_date']['value'] == '1 June 2026'
    assert terms['announcement_date']['evidence'].startswith(bullet)
    assert terms['record_date']['value'] == '3 June 2026'
    assert terms['maximum_new_shares']['value'] == 'up to 500,000'
    assert terms['subscription_price']['value'].endswith('subject to approval.')
    assert fd.dilution(terms, EVENT)['status'] == 'unknown'


def test_observed_template_aliases_do_not_merge_dates_ratios_and_managers():
    terms, _ = fd.parse_lines([
        'Date on which the terms and conditions of the repair issue were announced: 1 June 2026',
        'Last day of trading including right to receive subscription rights: 2 June 2026',
        'First day of trading exclusive right to receive subscription rights (Ex-date): 3 June 2026',
        'Record Date: 4 June 2026',
        'Subscription ratio: 1:1 (number of new shares per subscription right)',
        'Managers: Example Bank and Other Bank',
        'Will the rights be listed yes/no: Yes, subject to approval',
        'Other information: The board may cancel the offering',
    ])
    assert terms['announcement_date']['value'] == '1 June 2026'
    assert terms['last_day_including']['value'] == '2 June 2026'
    assert terms['ex_date']['value'] == '3 June 2026'
    assert terms['record_date']['value'] == '4 June 2026'
    assert terms['subscription_ratio']['value'] == '1:1 (number of new shares per subscription right)'
    assert terms['arranger']['value'] == 'Example Bank and Other Bank'
    assert terms['rights_listing']['value'] == 'Yes, subject to approval'
    assert terms['additional_information']['value'] == 'The board may cancel the offering'


def test_compact_markers_do_not_hide_duplicates_or_unknown_conditions():
    terms, _ = fd.parse_lines(['Subscription price: NOK 1', '-Subscription price: NOK 1'])
    assert terms['subscription_price']['status'] == 'ambiguous'
    terms, _ = fd.parse_lines(['Number of new shares in the rights issue: 1000',
                             '-Condition: subject to allocation',
                             'Number of existing shares before the rights issue: 4000',
                             'Class of existing and new shares: Ordinary shares'])
    assert '-Condition: subject to allocation' in terms['new_shares']['value']
    assert fd.dilution(terms, EVENT)['status'] == 'unknown'
    terms, _ = fd.parse_lines(['--Subscription price: NOK 1', 'Not Subscription price: NOK 1'])
    assert terms == {}


def test_fetched_document_without_supported_fields_is_not_labelled_partially_parsed():
    result = fd.collect(EVENT, AT, fetch=lambda _: page(['Unstructured information without labelled terms']))
    assert result['status'] == 'no_supported_terms'
    assert result['captured_at'] == AT.isoformat()
    assert result['content_sha256'] and result['terms'] == {}
    assert result['dilution']['status'] == 'unknown'


def test_v4_mixed_fields_are_withheld_until_revalidated():
    old = {'version': 4, 'terms': {'subscription_ratio': {'value': '1:1 Managers: Example'}}}
    public = fd.public_document(old)
    assert public['status'] == 'revalidation_required' and public['terms'] == {}
    assert old['terms']


def test_repair_offering_aliases_keep_conditions_and_listing_distinct():
    terms, _ = fd.parse_lines([
        '• Date on which the terms and conditions of the Subsequent Repair Offering were announced: 1 June 2026',
        '• Last day including right to receive subscription rights in the Subsequent Repair Offering: 2 June 2026',
        '• Subscription price: NOK 1',
        'Will the subscription rights be listed: No',
        'Other information: Subject to approval',
    ])
    assert terms['announcement_date']['value'] == '1 June 2026'
    assert terms['last_day_including']['value'] == '2 June 2026'
    assert terms['subscription_price']['value'] == 'NOK 1'
    assert terms['rights_listing']['value'] == 'No'


def test_long_conditions_are_preserved_without_truncation_or_calculation():
    conditions = 'The offering remains subject to approval. ' * 30
    terms, status = fd.parse_lines([
        'Number of existing shares before the rights issue: 4000',
        'Class of existing and new shares: Ordinary shares',
        'Number of new shares in the rights issue: 1000', conditions,
    ])
    assert status == 'partial'
    assert terms['new_shares']['value'] == '1000 ' + conditions.strip()
    assert fd.dilution(terms, EVENT)['status'] == 'unknown'
    terms, status = fd.parse_lines(['Subscription price: NOK 1', 'x' * fd.MAX_TERM_CHARS])
    assert terms == {} and status == 'no_supported_terms'
