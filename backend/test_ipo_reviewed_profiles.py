from datetime import datetime, timezone
import copy
from ipo_reviewed_profiles import enrich, _profiles

NOW = datetime(2026, 9, 25, 16, tzinfo=timezone.utc)
ROW = {'ticker':'PLCAN','isin':'CY0201461213','listing_date':'2026-07-02','market':'Euronext Growth'}


def test_exact_identity_enriches_without_score_or_current_financial_claims():
    item = enrich({'score_effect':0,'analysis_available':False}, ROW, NOW)
    assert item['score_effect'] == 0 and item['analysis_available'] is False
    profile = item['documented_profile']
    assert profile['status'] == 'reviewed_snapshot'
    assert all(x['source_id'] in profile['sources'] for x in profile['sections'])
    assert '2027-05-28' in item['next_event']
    financial = profile['sections'][1]
    assert financial['as_of'] == '2026-06-10'
    assert 'USD' in financial['text'] and 'ikke dagens likviditet' in financial['text']
    assert 'Eksakt lock-up' in ' '.join(item['unknowns'])


def test_no_ticker_only_join_and_no_lookahead_or_expired_calendar():
    for key in ROW:
        row = {**ROW,key:'wrong'}
        assert 'documented_profile' not in enrich({}, row, NOW)
    assert enrich({},ROW,datetime(2026,7,2,tzinfo=timezone.utc)) == {}
    later=enrich({},ROW,datetime(2027,5,29,tzinfo=timezone.utc))
    assert 'passert' in later['next_event']
    assert 'next_event_source' not in later


def test_returned_profile_cannot_mutate_reviewed_source():
    original=copy.deepcopy(_profiles())
    item=enrich({},ROW,NOW)
    item['documented_profile']['sections'][0]['text']='changed'
    assert _profiles() == original


def test_discovery_integrates_profile_only_for_matching_admission():
    import ipo_discovery
    row={**ROW,'company':'Pelican Aqua Holding','source_url':'https://live.euronext.com/en/markets/oslo/ipos'}
    item=ipo_discovery.project([row],[],now=NOW)['items'][0]
    assert item['documented_profile']['status']=='reviewed_snapshot'
    assert item['monitoring']=={'5':None,'20':None,'60':None}
    assert item['score_effect']==0
