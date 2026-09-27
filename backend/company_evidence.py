"""Append-only research snapshots. Recorded time is never a backdated known time.

Call record inside the transaction which owns the snapshot write lock. Repeated
captures do not create revisions; A -> B -> A does. No signal engine consumers.
"""
import json


def ensure_schema(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS company_evidence_versions (
      entity_key TEXT NOT NULL, revision INTEGER NOT NULL, ticker TEXT NOT NULL,
      identity TEXT NOT NULL, kind TEXT NOT NULL, recorded_at TEXT NOT NULL,
      payload TEXT NOT NULL, signature TEXT NOT NULL, changed_fields TEXT NOT NULL,
      PRIMARY KEY(entity_key,revision));
    CREATE INDEX IF NOT EXISTS company_evidence_lookup
      ON company_evidence_versions(ticker,identity,recorded_at);
    ''')


def facts(value):
    """Exclude collection clocks, retaining sources, dates, uncertainty and values."""
    if isinstance(value, dict):
        return {k: facts(v) for k, v in value.items()
                if k not in {'attempted_at', 'captured_at', 'observed_at'}}
    if isinstance(value, list):
        return [facts(v) for v in value]
    return value


def record(c, key, ticker, identity, kind, payload, at):
    canonical = facts(payload)
    signature = json.dumps(canonical, sort_keys=True, ensure_ascii=False)
    old = c.execute('SELECT * FROM company_evidence_versions WHERE entity_key=? ORDER BY revision DESC LIMIT 1', (key,)).fetchone()
    if old and old['signature'] == signature and old['identity'] == identity:
        return
    before = json.loads(old['signature']) if old and old['identity'] == identity else {}
    changed = sorted(k for k in set(before) | set(canonical) if before.get(k) != canonical.get(k))
    c.execute('INSERT INTO company_evidence_versions(entity_key,revision,ticker,identity,kind,recorded_at,payload,signature,changed_fields) VALUES(?,?,?,?,?,?,?,?,?)',
              (key, old['revision'] + 1 if old else 1, ticker, identity, kind,
               at.isoformat(), json.dumps(payload), signature, json.dumps(changed)))


def history(connect, ticker, identity, limit=30):
    """Bounded snapshot-only read. Legacy captures are not invented as history."""
    c = connect()
    try:
        rows = c.execute('SELECT * FROM company_evidence_versions WHERE ticker=? AND identity=? ORDER BY recorded_at DESC,entity_key,revision DESC LIMIT ?',
                         (ticker, identity, limit + 1)).fetchall()
        entries = []
        for row in rows[:limit]:
            payload = json.loads(row['payload'])
            entries.append({'entity_key': row['entity_key'], 'kind': row['kind'], 'revision': row['revision'],
                            'recorded_at': row['recorded_at'],
                            'title': payload.get('title'), 'source_url': payload.get('url') or payload.get('source_url'),
                            'published_at': payload.get('published_at'),
                            'changed_fields': json.loads(row['changed_fields'])})
        return {'status': 'available', 'entries': entries, 'truncated': len(rows) > limit,
                'coverage': 'Historikk fra aktivering av versjonslagring. Registreringstid er når denne versjonen ble lagret, ikke når markedet først kjente opplysningen. Endringer kan skyldes kildeinnhold, tolkning eller datastatus.'}
    finally:
        c.close()


def version(connect, ticker, identity, entity_key, revision):
    c = connect()
    try:
        row = c.execute('SELECT kind,recorded_at,payload FROM company_evidence_versions WHERE ticker=? AND identity=? AND entity_key=? AND revision=?',
                        (ticker, identity, entity_key, revision)).fetchone()
        if not row:
            return None
        payload=json.loads(row['payload'])
        if row['kind']=='financing_document' and payload.get('document'):
            from financing_documents import public_document
            payload['document']=public_document(payload['document'])
        return {'kind':row['kind'], 'recorded_at':row['recorded_at'],
                'revision':revision, 'payload':payload}
    finally:
        c.close()
