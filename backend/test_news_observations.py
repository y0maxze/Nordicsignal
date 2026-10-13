import json
import sqlite3

import pytest

import news_observations as observations


@pytest.fixture
def db(tmp_path, monkeypatch):
    def connect():
        conn = sqlite3.connect(tmp_path / 'news.db')
        conn.row_factory = sqlite3.Row
        return conn
    monkeypatch.setattr(observations, 'connect', connect)
    return connect


def feed(title='Announcement'):
    return {'status': 'live_general_news', 'sources': {'euronext': {'status': 'live'}},
            'items': [{'url': 'https://example.test/1', 'title': title,
                       'published_at': '2026-10-09T12:00:00Z', 'source_type': 'exchange'}]}


def test_first_seen_is_real_observation_not_publication_and_survives_update(db):
    observations.record(feed())
    with db() as c:
        first = dict(c.execute('SELECT * FROM market_news_observations').fetchone())
    observations.record(feed('Corrected announcement'))
    with db() as c:
        rows = c.execute('SELECT * FROM market_news_observations').fetchall()
    assert len(rows) == 1
    assert rows[0]['first_seen_at'] == first['first_seen_at']
    assert rows[0]['first_seen_at'] != rows[0]['published_at']
    assert rows[0]['title'] == 'Corrected announcement'
    assert rows[0]['ticker'] is None


def test_background_observation_updates_public_cache(db):
    payload = feed()
    observations.record(payload)
    with db() as c:
        row = c.execute('SELECT * FROM runtime_feed_cache').fetchone()
    assert row['cache_key'] == 'market_news:v1'
    assert json.loads(row['payload']) == payload


def test_failure_recorded_without_erasing_success(db):
    observations.record(feed())
    observations.record({'status': 'unavailable', 'items': [],
                         'sources': {'euronext': {'status': 'unavailable'}}})
    with db() as c:
        assert json.loads(c.execute('SELECT payload FROM runtime_feed_cache').fetchone()[0]) == feed()
        state = c.execute('SELECT * FROM market_news_capture_state').fetchone()
        assert state['status'] == 'unavailable' and state['items_seen'] == 0
        assert c.execute('SELECT count(*) FROM market_news_observations').fetchone()[0] == 1


def test_bounded_metadata_and_no_invalid_links(db):
    payload = feed()
    payload['items'] = [{'url': f'https://example.test/{i}', 'title': 'Announcement'} for i in range(70)]
    payload['items'][0]['url'] = 'javascript:alert(1)'
    payload['items'][1] = None
    assert observations.record(payload) == 48
    with db() as c:
        assert c.execute('SELECT count(*) FROM market_news_observations').fetchone()[0] == 48


def test_invalid_feed_rejected_before_connection(db):
    with pytest.raises(ValueError):
        observations.record({'items': None})


def test_successful_empty_observation_replaces_old_snapshot(db):
    observations.record(feed())
    observations.record({'status': 'no_market_news', 'items': [],
                         'sources': {'euronext': {'status': 'no_matches'}}})
    with db() as c:
        assert json.loads(c.execute('SELECT payload FROM runtime_feed_cache').fetchone()[0])['items'] == []
        assert c.execute('SELECT count(*) FROM market_news_observations').fetchone()[0] == 1
