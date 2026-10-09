import inspect
import unittest
from datetime import datetime, timezone, timedelta
import json
import sqlite3

import pytest
from database import SCHEMA_SQLITE

import data_quality_runtime as dq


class DataQualityRuntimeTests(unittest.TestCase):
    def test_age_seconds_handles_current_timestamp(self):
        value=(datetime.now(timezone.utc)-timedelta(seconds=5)).isoformat()
        age=dq._age_seconds(value)
        self.assertIsNotNone(age)
        self.assertGreaterEqual(age, 0)
        self.assertLess(age, 30)

    def test_check_keeps_warning_severity(self):
        row=dq._check('freshness', False, 'stale', severity='warning')
        self.assertFalse(row['ok'])
        self.assertEqual(row['severity'],'warning')

    def test_persisted_quote_age_is_not_reported_as_live_price_age(self):
        source=inspect.getsource(dq.data_quality_snapshot)
        self.assertIn('"mode": "live_on_request"', source)
        self.assertIn('freshness["persisted_price_snapshot"]', source)
        self.assertNotIn('quote_age = freshness["prices"]', source)


if __name__=='__main__':
    unittest.main()


@pytest.fixture
def quality_db(tmp_path, monkeypatch):
    path = tmp_path / 'quality.db'
    def connect():
        c = sqlite3.connect(path)
        c.row_factory = sqlite3.Row
        return c
    monkeypatch.setattr(dq, 'connect', connect)
    with connect() as c:
        c.executescript(SCHEMA_SQLITE)
        c.executescript('''
          CREATE TABLE trend_activity_events(created_at TEXT,volume_ratio REAL,recent_volume_ratio REAL);
          CREATE TABLE signal_events(created_at TEXT);
          CREATE TABLE runtime_feed_cache(cache_key TEXT,updated_at REAL);
          CREATE TABLE holding_purchase_lots(shares REAL,price_nok REAL);
          CREATE TABLE company_context_profiles(ticker TEXT,payload TEXT);
          CREATE TABLE ipo_listings(ticker TEXT,isin TEXT);
          INSERT INTO holding_purchase_lots VALUES(3,100);
          INSERT INTO ipo_listings VALUES('NORSE','NO0012885252');
          INSERT INTO stocks VALUES('AAA','A','sector','Oslo',1);
          INSERT INTO stocks VALUES('BBB','B','sector','Oslo',1);
        ''')
        now = datetime.now(timezone.utc).isoformat()
        for ticker in ('AAA','BBB'):
            c.execute('INSERT INTO scores(ticker,fundamentals,insider,valuation,sentiment,total,created_at,source) VALUES(?,20,12,10,8,50,?,?)', (ticker, now, 'live'))
        c.execute('INSERT INTO quotes(ticker,price,captured_at,market_time) VALUES(?,?,?,?)', ('AAA',100,now,now))
    return connect


def checks(snapshot):
    return {x['name']: x for x in snapshot['checks']}


def test_actual_purchase_lot_schema_is_checked_and_invalid_values_fail(quality_db):
    assert checks(dq.data_quality_snapshot())['holding_lot_sanity']['ok'] is True
    with quality_db() as c:
        c.execute('INSERT INTO holding_purchase_lots VALUES(NULL,100)')
        c.execute('INSERT INTO holding_purchase_lots VALUES(1,0)')
    check = checks(dq.data_quality_snapshot())['holding_lot_sanity']
    assert check['ok'] is False and '2 invalid' in check['detail']


def test_unavailable_check_is_never_reported_as_pass(quality_db):
    with quality_db() as c:
        c.execute('DROP TABLE holding_purchase_lots')
        c.execute('DROP TABLE trend_activity_events')
    result = dq.data_quality_snapshot()
    for name in ('holding_lot_sanity','trend_volume_sanity'):
        assert checks(result)[name]['ok'] is False
        assert checks(result)[name]['severity'] == 'warning'
    assert result['status'] == 'warning'


@pytest.mark.parametrize('value', [None, '', 'invalid', '2026-10-09', '2026-10-09T12:00:00',
    (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()])
def test_future_naive_or_invalid_time_is_unknown(value):
    assert dq._age_seconds(value) is None


def test_recent_one_stock_does_not_hide_missing_quote_for_another(quality_db):
    result = dq.data_quality_snapshot()
    assert checks(result)['persisted_quote_snapshot_recency']['ok'] is True
    assert checks(result)['persisted_quote_coverage']['ok'] is False
    assert result['metrics']['persisted_quotes']['missing'] == 1
    assert result['metrics']['persisted_quotes']['unknown_or_invalid_market_time'] == 1


def test_recent_capture_does_not_certify_missing_or_future_market_time(quality_db):
    with quality_db() as c:
        c.execute('UPDATE quotes SET market_time=?', ((datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),))
        c.execute('UPDATE scores SET created_at=? WHERE ticker=?', ('2026-10-09T12:00:00','BBB'))
    result = dq.data_quality_snapshot()
    assert result['metrics']['persisted_quotes']['unknown_or_invalid_market_time'] == 2
    assert checks(result)['score_freshness']['ok'] is False
    assert result['freshness']['fundamentals']['latest_at'] is None
    assert result['freshness']['fundamentals']['age_seconds'] is None
    assert result['freshness']['fundamentals']['processed_at'] is not None


def test_financial_coverage_excludes_stale_and_unverified_rows(quality_db):
    verified = {'description':'A','financials':[{'value':100}], 'yahoo_identity_verified':True,
                'field_sources':{'financials':{'status':'stale','captured_at':datetime.now(timezone.utc).isoformat()}}}
    legacy = {'description':'B','financials':[{'value':100}]}
    with quality_db() as c:
        for ticker, payload in [('AAA',verified),('BBB',legacy),('BROKEN',[])]:
            c.execute('INSERT INTO company_context_profiles VALUES(?,?)', (ticker,json.dumps(payload)))
    result = dq.data_quality_snapshot()
    assert result['metrics']['company_profiles'] == {'stored':3,'with_description':2,
        'financials_with_verified_identity':1,'financials_recently_collected':0,
        'unverified_financials_hidden':1,'invalid_payloads':1}
    assert checks(result)['company_profile_payloads']['ok'] is False
    assert checks(result)['company_financial_coverage']['ok'] is False
    assert checks(result)['listing_identifier_format']['ok'] is True


def test_optional_query_failure_recovers_transaction_before_next_check(quality_db,monkeypatch):
    class Transaction:
        def __init__(self):
            self.c = quality_db()
            self.failed = False
        def execute(self, sql, params=()):
            if self.failed:
                raise RuntimeError('transaction aborted')
            if 'FROM trend_activity_events' in sql:
                self.failed = True
                raise RuntimeError('optional relation unavailable')
            return self.c.execute(sql,params)
        def rollback(self):
            self.failed = False
            self.c.rollback()
        def close(self):
            self.c.close()
    monkeypatch.setattr(dq,'connect',Transaction)
    result = checks(dq.data_quality_snapshot())
    assert result['trend_volume_sanity']['ok'] is False
    assert result['holding_lot_sanity']['ok'] is True
    assert result['listing_identifier_format']['ok'] is True
