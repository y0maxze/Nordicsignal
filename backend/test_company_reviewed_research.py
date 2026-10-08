from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import pytest
import company_reviewed_research as research
import company_context as cc

AT = datetime(2026, 10, 9, tzinfo=timezone.utc)


def project(ticker='HDLY', identity='huddly', profile=None, events=None, at=AT):
    if events is None:
        events = [{'source_type': 'newsweb_oam', 'source_issuer_id': 12850}]
    return research.project(ticker, identity, profile or {}, events, at)


def test_reviewed_sources_and_comparative_units_are_valid():
    for p in research.profiles():
        research.validate(p)
        result = research.project(p['ticker'], p['identity'], {'isin': p['isin']},
                                  [{'source_type': 'newsweb_oam', 'source_issuer_id': p['newsweb_issuer_id']}], AT)
        assert result['status'] == 'reviewed_snapshot' and not result['needs_review']
        assert [g['kind'] for g in result['financial_groups']] == ['quarter', 'half_year', 'balance', 'annual']
    inify = project('INIFY', 'inify laboratories', {'isin': 'SE0017486103'}, [])
    assert {g['currency'] for g in inify['financial_groups']} == {'SEK'}
    assert inify['financial_groups'][0]['metrics'][0]['value'] == 6323
    assert inify['financial_groups'][3]['metrics'][0]['previous'] == 13131


@pytest.mark.parametrize('ticker,identity,profile,events', [
    ('HDLY', 'different issuer', {}, [{'source_type': 'newsweb_oam', 'source_issuer_id': 12850}]),
    ('OTHER', 'huddly', {}, [{'source_type': 'newsweb_oam', 'source_issuer_id': 12850}]),
    ('HDLY', 'huddly', {}, []),
    ('HDLY', 'huddly', {}, [{'source_type': 'newsweb_oam', 'source_issuer_id': 999}]),
    ('HDLY', 'huddly', {}, [{'source_type': 'newsweb_oam', 'source_issuer_id': x} for x in [12850, 999]]),
    ('HYPRO', 'hydrogenpro', {'isin': 'WRONG'}, [{'source_type': 'newsweb_oam', 'source_issuer_id': 12809}]),
    ('HYPRO', 'hydrogenpro', {'isin': None, 'isin_status': 'ambiguous'}, [{'source_type': 'newsweb_oam', 'source_issuer_id': 12809}]),
])
def test_identity_requires_corroboration_and_rejects_conflicts(ticker, identity, profile, events):
    assert project(ticker, identity, profile, events) is None


def test_future_review_cannot_leak_and_projection_never_mutates_cached_sources():
    reviewed = research.timestamp(research.profiles()[1]['reviewed_at'])
    assert project(at=reviewed-timedelta(seconds=1)) is None
    result = project(); result['financial_groups'][0]['metrics'][0]['value'] = 999
    assert project()['financial_groups'][0]['metrics'][0]['value'] == 50373
    assert 'status' not in research.profiles()[1]


def test_newer_evidence_correction_and_age_require_review_without_claiming_new_status():
    newer = {'source_type': 'newsweb_oam', 'source_issuer_id': 12850, 'url': 'https://example.test/new', 'published_at': '2026-10-09T00:00:00Z'}
    p = project(events=[newer, deepcopy(newer)])
    assert p['needs_review'] and p['newer_financing_count'] == 1
    assert 'kansellert' in p['transactions'][1]['steps'][-1]['text']
    old = {'source_type':'newsweb_oam', 'source_issuer_id':12850, 'source_message_id':683086, 'corrected_by_message_id':999}
    assert project(events=[old])['source_correction_observed']
    assert project(at=AT+timedelta(days=40))['needs_review']
    assert project(at=AT+timedelta(days=40))['next_event']['passed']
    assert not project(at=datetime(2026,11,5,22,tzinfo=timezone.utc))['next_event']['passed']
    assert project(at=datetime(2026,11,5,23,tzinfo=timezone.utc))['next_event']['passed']


@pytest.mark.parametrize('mutation', [
    lambda p:p['sources']['q2'].update(url='javascript:alert(1)'),
    lambda p:p['sources']['q2'].update(url='https://user:pass@example.test'),
    lambda p:p['sources']['q2'].update(published_on='2099-01-01'),
    lambda p:p['business'].update(source_id='missing'),
    lambda p:p['financial_groups'][0].update(currency='USD'),
    lambda p:p['financial_groups'][0].update(previous_start='2025-01-01'),
    lambda p:p['financial_groups'][0].update(end='2026-06-15'),
    lambda p:p['financial_groups'][0]['metrics'][0].update(value=float('nan')),
    lambda p:p['financial_groups'][0]['metrics'][0].update(value=True),
])
def test_invalid_snapshot_cannot_be_published(mutation):
    p = deepcopy(research.profiles()[0]); mutation(p)
    with pytest.raises(ValueError): research.validate(p)


def test_registry_fallback_preserves_previous_verified_business_description():
    previous = {'description':'Verified business', 'yahoo_identity_verified':True,
                'field_sources':{'description':{'source':'Yahoo Finance','captured_at':'2026-10-01T00:00:00Z'}}}
    fresh = {'description':'Register activity', 'description_kind':'registered_activity',
             'source_status':{'description':'stored'}, 'field_sources':{}}
    result = cc.retain_profile_fields(fresh, {'payload':json.dumps(previous)}, AT)
    assert result['description'] == 'Verified business'
    assert result['field_sources']['description']['status'] == 'stale'
    assert result['field_sources']['description']['captured_at'] == '2026-10-01T00:00:00Z'
    assert result.get('description_kind') != 'registered_activity'


def test_context_adds_read_only_research_without_authorizing_yahoo_or_changing_score(monkeypatch):
    monkeypatch.setattr(cc,'now',lambda:AT)
    monkeypatch.setattr(cc.evidence,'history',lambda *args:{'status':'available','entries':[]})
    import company_newsweb
    monkeypatch.setattr(company_newsweb,'coverage',lambda *args:{})
    p={'identity':'hydrogenpro','isin':'NO0010892359','yahoo_identity_verified':False,'financials':[]}
    result=cc.context('HYPRO',({'HYPRO':p},{},{}),identity='HydrogenPro ASA')
    assert result['reviewed_research']['ticker']=='HYPRO'
    assert result['score_effect']==0 and result['financials']==[] and result['yahoo_identity_verified'] is False
