"""Persist already-fetched public news metadata; never infer alerts or coverage.

No provider calls, retroactive first-seen dates, issuer inference or score changes.
The bounded latest-page collector is not a complete exchange announcement archive.
"""
from datetime import datetime, timezone
import json
import time

from database import connect


def record(feed):
    if not isinstance(feed, dict) or not isinstance(feed.get('items'), list):
        raise ValueError('invalid_news_feed')
    checked = datetime.now(timezone.utc).isoformat()
    epoch = time.time()
    sources = feed.get('sources') or {}
    failed = any(isinstance(s, dict) and s.get('status') == 'unavailable'
                 for s in sources.values()) if isinstance(sources, dict) else True
    usable = bool(feed['items']) or (feed.get('status') != 'unavailable' and not failed)
    conn = connect()
    try:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS market_news_observations (
          source_url TEXT PRIMARY KEY, title TEXT NOT NULL, published_at TEXT,
          first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
          source_type TEXT, ticker TEXT
        );
        CREATE TABLE IF NOT EXISTS market_news_capture_state (
          id INTEGER PRIMARY KEY, checked_at TEXT NOT NULL, status TEXT NOT NULL,
          sources_json TEXT NOT NULL, items_seen INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runtime_feed_cache (
          cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at DOUBLE PRECISION NOT NULL
        );
        ''')
        count = 0
        for item in feed['items'][:50]:
            if not isinstance(item, dict):
                continue
            url = str(item.get('url') or '').strip()
            title = str(item.get('title') or '').strip()
            if not url.startswith(('https://', 'http://')) or not title:
                continue
            conn.execute('INSERT INTO market_news_observations VALUES(?,?,?,?,?,?,?) '
                         'ON CONFLICT(source_url) DO UPDATE SET title=excluded.title,'
                         'published_at=excluded.published_at,last_seen_at=excluded.last_seen_at,'
                         'source_type=excluded.source_type,ticker=excluded.ticker',
                         (url, title, item.get('published_at'), checked, checked,
                          item.get('source_type'), item.get('ticker')))
            count += 1
        conn.execute('INSERT INTO market_news_capture_state VALUES(1,?,?,?,?) '
                     'ON CONFLICT(id) DO UPDATE SET checked_at=excluded.checked_at,'
                     'status=excluded.status,sources_json=excluded.sources_json,items_seen=excluded.items_seen',
                     (checked, str(feed.get('status') or 'unknown'), json.dumps(sources), count))
        if usable:
            conn.execute('INSERT INTO runtime_feed_cache VALUES(?,?,?) '
                         'ON CONFLICT(cache_key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at '
                         'WHERE runtime_feed_cache.updated_at<=excluded.updated_at',
                         ('market_news:v1', json.dumps(feed, ensure_ascii=False), epoch))
        conn.commit()
        return count
    finally:
        conn.close()
