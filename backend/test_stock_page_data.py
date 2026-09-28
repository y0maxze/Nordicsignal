import sqlite3
from unittest.mock import Mock

import pytest
from database import SCHEMA_SQLITE
from stock_page_data import quote_result, stock_summary


@pytest.fixture
def db(tmp_path):
    path = tmp_path / 'stock.sqlite'
    def connect():
        c = sqlite3.connect(path)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        return c
    c = connect()
    c.executescript(SCHEMA_SQLITE)
    c.execute("INSERT INTO stocks(ticker,name) VALUES('AKSO','Aker Solutions')")
    c.commit()
    c.close()
    return connect


def test_unranked_quote_survives_foreign_key_boundary_without_enrolment(db):
    evidence = {'ticker': 'TECH', 'price': 5.5, 'currency': 'NOK', 'source': 'Yahoo Finance',
                'market_time': '2026-09-28T14:28:58Z', 'captured_at': '2026-09-28T17:00:00Z'}
    provider = Mock()
    provider.quote.return_value = evidence
    result = quote_result('tech.ol', provider, db)
    assert all(result[k] == v for k, v in evidence.items())
    assert result['persistence_status'] == 'outside_scoring_universe'
    provider.quote.assert_called_once_with('TECH')
    c = db()
    assert c.execute('SELECT COUNT(*) FROM quotes').fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM stocks WHERE ticker='TECH'").fetchone()[0] == 0
    c.close()


def test_ranked_quote_is_still_persisted(db):
    provider = Mock()
    provider.quote.return_value = {'ticker': 'AKSO', 'price': 42.4, 'source': 'Yahoo Finance'}
    assert quote_result('AKSO', provider, db)['persistence_status'] == 'stored'
    c = db()
    assert c.execute('SELECT price FROM quotes').fetchone()[0] == 42.4
    c.close()


def test_cache_failure_preserves_quote_and_releases_connection():
    provider, conn = Mock(), Mock()
    provider.quote.return_value = {'price': 12, 'source': 'Yahoo Finance', 'market_time': None}
    conn.execute.side_effect = RuntimeError('database unavailable')
    result = quote_result('TECH', provider, lambda: conn)
    assert result['price'] == 12 and result['source'] == 'Yahoo Finance'
    assert result['market_time'] is None and result['persistence_status'] == 'unavailable'
    conn.close.assert_called_once()


def test_provider_failure_does_not_invent_quote_or_open_database():
    provider, connect = Mock(), Mock()
    provider.quote.side_effect = RuntimeError('no quote')
    assert quote_result('TECH', provider, connect)['source'] == 'unavailable'
    connect.assert_not_called()


def test_registry_stock_without_score_keeps_identity_and_null_score(db):
    result = stock_summary('AKSO', db, Mock(side_effect=AssertionError('unneeded fallback')))
    assert result['name'] == 'Aker Solutions'
    assert result['score'] is None and result['signal'] is None
    assert result['score_source'] == 'unavailable'


def test_exact_reconciled_issuer_identity_is_displayed_without_score_or_enrolment(db):
    result = stock_summary('TECH.OL', db, lambda: {'TECH': {'company': 'Techstep ASA'}})
    assert result['name'] == 'Techstep ASA' and result['ticker'] == 'TECH'
    assert result['score'] is None and result['fundamentals'] is None
    assert result['live_verified'] is False
    assert stock_summary('TECH', db, lambda: {}) == {'error': 'Ticker not found'}


def test_latest_existing_score_and_partial_insider_rules_are_preserved(db):
    c = db()
    for total, source in [(60, 'live'), (72, 'partial_live')]:
        c.execute('INSERT INTO scores(ticker,fundamentals,insider,valuation,sentiment,total,created_at,source) VALUES(?,?,?,?,?,?,?,?)', ('AKSO',30,12,20,10,total,'2026-09-28T16:17:00Z',source))
    c.commit(); c.close()
    result = stock_summary('AKSO', db, lambda: {})
    assert result['score'] == 72 and result['insider'] is None
    assert result['partial_live'] is True and result['live_verified'] is False
