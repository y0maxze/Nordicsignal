"""Database leases for bounded research jobs, independent of alert scheduling."""
from datetime import timedelta
import uuid


def ensure_schema(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS financing_document_jobs (
      event_key TEXT PRIMARY KEY, state TEXT NOT NULL, token TEXT,
      lease_until TEXT, attempts INTEGER NOT NULL, attempted_at TEXT,
      finished_at TEXT, next_attempt_at TEXT NOT NULL);
    ''')


def claim(connect, key, at, expected_payload=None):
    token = uuid.uuid4().hex
    c = connect()
    try:
        c.execute('INSERT INTO financing_document_jobs(event_key,state,attempts,next_attempt_at) VALUES(?,?,0,?) ON CONFLICT(event_key) DO NOTHING',
                  (key, 'queued', at.isoformat()))
        cursor = c.execute('UPDATE financing_document_jobs SET state=?,token=?,lease_until=?,attempted_at=?,attempts=attempts+1 WHERE event_key=? AND (lease_until IS NULL OR lease_until<=?)',
                           ('running', token, (at+timedelta(minutes=3)).isoformat(), at.isoformat(), key, at.isoformat()))
        if cursor.rowcount and expected_payload is not None:
            current = c.execute('SELECT payload FROM company_context_events WHERE event_key=?', (key,)).fetchone()
            if not current or current['payload'] != expected_payload:
                c.rollback()
                return None
        c.commit()
        return token if cursor.rowcount else None
    finally:
        c.close()


def finish(c, key, token, status, at):
    """Acquire the lease row lock before committing snapshot and evidence together.

    A worker whose lease expired or was replaced cannot publish late results.
    Eligibility is derived from the durable document snapshot, including parser
    version; next_attempt_at is an operational projection, not a second scheduler.
    """
    days = 7 if status == 'partial' else 1
    cursor = c.execute('UPDATE financing_document_jobs SET state=?,token=NULL,lease_until=NULL,finished_at=?,next_attempt_at=? WHERE event_key=? AND token=? AND lease_until>?',
                       (status, at.isoformat(), (at+timedelta(days=days)).isoformat(), key, token, at.isoformat()))
    return bool(cursor.rowcount)


def summary(connect):
    c = connect()
    try:
        rows = c.execute('SELECT state,COUNT(*) AS count FROM financing_document_jobs GROUP BY state').fetchall()
        return {r['state']: r['count'] for r in rows}
    finally:
        c.close()
