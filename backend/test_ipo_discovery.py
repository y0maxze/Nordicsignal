from datetime import datetime, timezone
import json
import sqlite3
import ipo_discovery as discovery

NOW = datetime(2026, 9, 25, tzinfo=timezone.utc)


def listed(**kw):
    return dict({'listing_id':'one','company':'Example ASA','ticker':'EX','market':'Euronext Growth',
                 'listing_date':'2026-09-24','source_url':'https://live.euronext.com/en/markets/oslo/ipos'}, **kw)


def candidate(**kw):
    return dict({'candidate_id':'next','company':'New ASA','ticker':'NEW','market':'Euronext Growth Oslo',
                 'title':'Intention to float on Euronext Growth Oslo','published_at':'2026-09-21T08:00:00Z',
                 'expected_listing_date_text':'5 October 2026','source_url':'https://live.euronext.com/en/node/42',
                 'raw_payload':json.dumps({'official':True})}, **kw)


def test_groups_are_oslo_calendar_days_and_not_universe_limited():
    result=discovery.project([listed(),listed(listing_id='old',ticker='OLD',listing_date='2026-01-02'),
                              listed(listing_id='future',ticker='FUT',listing_date='2026-09-26')],[],now=NOW)
    assert result['counts']=={'upcoming':0,'recent':1,'year':2}
    assert result['items'][0]['analysis_available'] is False
    assert all(x['score_effect']==0 for x in result['items'])
    assert result['items'][0]['listing_type']=='unknown'
    # In Oslo it is Jan 1: a Dec 31 admission is recent, not this year's admission.
    result=discovery.project([listed(listing_date='2026-12-31')],[],now=datetime(2026,12,31,23,30,tzinfo=timezone.utc))
    assert result['year']==2027 and result['counts']['recent']==1 and result['counts']['year']==0


def test_stale_cancelled_bonds_transfers_completed_and_unofficial_plans_excluded():
    bad=[candidate(expected_listing_date_text='24 September 2026'),
         candidate(published_at='2026-01-01T08:00:00Z'),candidate(title='IPO postponed'),
         candidate(title='Expected listing of bonds on Euronext Growth Oslo'),
         candidate(title='Intention to list transfer to Oslo Børs'),
         candidate(raw_payload='{"official":false}'),candidate(source_url='https://live.euronext.com.evil.test/x'),
         candidate(ticker='EX')]
    result=discovery.project([listed()],bad,now=NOW)
    assert result['counts']['upcoming']==0
    assert result['excluded_candidates']==len(bad)


def test_upcoming_dedup_unknown_and_date_not_completion():
    row=candidate(expected_listing_date_text=None)
    result=discovery.project([], [row,row],now=NOW)
    assert result['count']==1
    item=result['items'][0]
    assert item['expected_listing_date'] is None and item['listing_date'] is None
    assert item['display_status']=='PRE-IPO'
    assert item['monitoring']=={'5':None,'20':None,'60':None}
    assert 'gjennomføring ikke bekreftet' in item['confirmation']


def test_read_endpoint_survives_missing_optional_tables_and_closes_connections(tmp_path, monkeypatch):
    path=tmp_path/'read.db'
    conn=sqlite3.connect(path)
    conn.execute('CREATE TABLE ipo_listings(listing_id TEXT, company TEXT, ticker TEXT, market TEXT, listing_date TEXT, source_url TEXT)')
    row=listed();conn.execute('INSERT INTO ipo_listings VALUES(?,?,?,?,?,?)',tuple(row.values()))
    conn.commit();conn.close()
    connections=[]
    def connect():
        c=sqlite3.connect(path);c.row_factory=sqlite3.Row;connections.append(c);return c
    monkeypatch.setattr(discovery,'connect',connect)
    result=discovery.build_discovery()
    assert result['status']=='partial'
    assert result['source_status']['candidates']=='unavailable'
    assert len(connections)==3
    for c in connections:
        try:c.execute('SELECT 1')
        except sqlite3.ProgrammingError:pass
        else:raise AssertionError('Connection leaked')


def test_registry_html_without_rows_is_not_a_successful_sync(monkeypatch):
    import ipo_listing_registry_runtime as registry
    monkeypatch.setattr(registry, 'record_listings', lambda rows: (_ for _ in ()).throw(AssertionError('Must not write')))
    assert registry.sync_listings(fetch_text=lambda url: '<html>Source unavailable</html>')['status']=='unavailable'
