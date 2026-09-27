"""Bounded official-document evidence. No model, push or per-GET network work.

Version 1 deliberately handles English labelled key-information notices only.
It preserves the original field text, including qualifications; unstructured prose,
conflicting labels and multi-offering titles are not reconciled automatically.
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from html.parser import HTMLParser
from urllib.parse import urlsplit
import hashlib
import re

VERSION = 1
MAX_BYTES = 1_000_000
LABELS = {
    'subscription_price': ('subscription price',),
    'new_shares': ('number of new shares', 'number of new shares in the rights issue'),
    'maximum_new_shares': ('maximum number of new shares', 'maximum number of new shares to be issued in the rights issue'),
    'existing_shares': ('number of existing shares before the rights issue',),
    'share_class': ('class of existing and new shares',),
    'gross_proceeds': ('gross proceeds',),
    'net_proceeds': ('net proceeds',),
    'subscription_period': ('subscription period',),
    'subscription_deadline': ('subscription deadline',),
    'ex_date': ('ex-date',),
    'record_date': ('record date',),
    'settlement_date': ('settlement date',),
    'delivery_date': ('delivery date',),
    'subscription_rights': ('ratio subscription rights', 'ratio preferential rights', 'subscription ratio'),
    'eligibility': ('eligible shareholders', 'who may subscribe'),
    'primary_secondary': ('primary and secondary shares',),
    'use_of_proceeds': ('use of proceeds',),
    'lock_up': ('lock-up', 'lock-up period'),
    'underwriting': ('underwriting', 'underwriting guarantee'),
}
LABEL_MAP = {label: key for key, labels in LABELS.items() for label in labels}


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style', 'noscript'}:
            self.skip += 1
        elif not self.skip and tag in {'p', 'br', 'li', 'tr', 'h1', 'h2', 'h3', 'div'}:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in {'script', 'style', 'noscript'}:
            self.skip = max(0, self.skip - 1)
        elif not self.skip and tag in {'p', 'li', 'tr', 'h1', 'h2', 'h3', 'div'}:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(re.sub(r'\s+', ' ', data))

    @property
    def lines(self):
        return [' '.join(line.split()) for line in ''.join(self.parts).splitlines() if line.strip()]


def _text(html):
    parser = PageText()
    parser.feed(html)
    return ' '.join(parser.lines)


def source_allowed(url):
    try:
        u = urlsplit(str(url or ''))
        return (u.scheme == 'https' and u.hostname == 'live.euronext.com'
                and not u.username and not u.password and u.port in (None, 443)
                and not u.query and not u.fragment
                and bool(re.fullmatch(r'/(?:en|nb)/(?:node/\d+|products/equities/company-news/[a-zA-Z0-9_-]+)', u.path)))
    except ValueError:
        return False


def fetch_document(url):
    """Do not follow redirects to unverified hosts or parse challenge/error pages."""
    if not source_allowed(url):
        raise ValueError('unverified document URL')
    import requests
    with requests.get(url, timeout=12, allow_redirects=False, stream=True) as response:
        if response.status_code != 200 or 'text/html' not in response.headers.get('Content-Type', '').lower():
            raise ValueError('document unavailable')
        body = bytearray()
        for chunk in response.iter_content(16384):
            body.extend(chunk)
            if len(body) > MAX_BYTES:
                raise ValueError('document too large')
        return body.decode(response.encoding or 'utf-8', errors='strict')


def parse_terms(html, event):
    from company_context import norm, FINANCING_TYPES
    titles = re.findall(r'<h1\b[^>]*>(.*?)</h1>', html, re.I | re.S)
    if len(titles) != 1 or _text(titles[0]).casefold() != ' '.join(event['title'].split()).casefold():
        raise ValueError('document title mismatch')
    issuers = re.findall(r'<h3\b[^>]*>\s*(?:Issuer|Company Name)\s*</h3>\s*<p\b[^>]*>(.*?)</p>', html, re.I | re.S)
    if not issuers or {norm(_text(v)) for v in issuers} != {event['identity']}:
        raise ValueError('document issuer mismatch')
    # Only labelled key-information documents with one financing type are supported.
    kinds = {kind for kind, pattern in FINANCING_TYPES if pattern.search(event['title'])}
    if len(kinds) != 1 or not re.search(r'\bkey information\b', event['title'], re.I):
        return {}, 'unsupported_document'
    parser = PageText()
    parser.feed(html)
    found = {}
    lines = parser.lines
    for index, line in enumerate(lines):
        label, sep, value = line.partition(':')
        key = LABEL_MAP.get(label.strip().casefold())
        if key and sep:
            # Line/paragraph wrapping must not discard a qualification after a
            # number. Keep continuation text up to the next explicitly labelled
            # field; too much prose will deliberately become unsupported below.
            continuation = []
            for following in lines[index + 1:]:
                if ':' in following:
                    break
                continuation.append(following)
            value = ' '.join([value.strip(), *continuation]).strip()
            evidence = label + ': ' + value
            found.setdefault(key, []).append((evidence, value))
    terms = {}
    for key, candidates in found.items():
        # Even duplicate values can refer to different tranches. Do not pick one.
        if len(candidates) != 1:
            terms[key] = {'status': 'ambiguous', 'value': None, 'evidence': None}
            continue
        evidence, value = candidates[0]
        if not value or len(evidence) > 700:
            continue
        terms[key] = {'status': 'documented', 'value': value, 'evidence': evidence}
    return terms, 'partial'


def _integer(term):
    value = (term or {}).get('value')
    if (term or {}).get('status') != 'documented' or not isinstance(value, str):
        return None
    # English-labelled exact counts only. No ranges, maxima, decimal counts or prose.
    if not re.fullmatch(r'(?:[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)(?: shares)?', value):
        return None
    number = int(value.removesuffix(' shares').replace(',', ''))
    return number if number <= 10**15 else None


def dilution(terms, event):
    """Same document + explicitly shared class + pre-issue denominator required."""
    unknown = {'status': 'unknown', 'percentage': None,
               'reason': 'Krever eksakte nye aksjer, aksjer før samme emisjon og uttrykkelig felles aksjeklasse i samme dokument.'}
    before, new = _integer(terms.get('existing_shares')), _integer(terms.get('new_shares'))
    share_class = terms.get('share_class') or {}
    if (not before or not new or share_class.get('status') != 'documented'
            or not str((terms.get('new_shares') or {}).get('evidence', '')).casefold().startswith('number of new shares in the rights issue:')
            or str(share_class.get('value', '')).casefold() not in {'ordinary shares', 'class a', 'class b'}
            or event.get('financing_type') != 'rights_issue'):
        return unknown
    return {'status': 'calculated', 'percentage': str((Decimal(new) / Decimal(before + new) * 100).quantize(Decimal('0.0001'))),
            'existing_shares': before, 'new_shares': new, 'share_class': share_class['value'],
            'formula': 'new_shares / (existing_shares + new_shares) × 100',
            'source_url': event['url'], 'published_at': event['published_at'],
            'limitation': 'Dokumentscenario for en eier som ikke deltar. Ikke bekreftelse på gjennomføring, kurstap eller fullt utvannet aksjetall.'}


def collect(event, at, previous=None, fetch=None):
    from company_context import FINANCING_TYPES
    previous = previous or {}
    result = {'version': VERSION, 'attempted_at': at.isoformat(), 'captured_at': None,
              'status': 'unavailable', 'terms': {}, 'dilution': dilution({}, event),
              'source_url': event['url'], 'published_at': event['published_at']}
    kinds = {kind for kind, pattern in FINANCING_TYPES if pattern.search(event['title'])}
    if len(kinds) != 1 or not re.search(r'\bkey information\b', event['title'], re.I):
        result['status'] = 'unsupported_document'
        return result
    try:
        if not source_allowed(event['url']):
            raise ValueError('unverified source')
        html = (fetch or fetch_document)(event['url'])
        if not isinstance(html, str) or len(html.encode('utf-8')) > MAX_BYTES:
            raise ValueError('invalid document')
        terms, status = parse_terms(html, event)
        result.update(status=status, terms=terms, captured_at=at.isoformat(),
                      content_sha256=hashlib.sha256(html.encode('utf-8')).hexdigest(),
                      dilution=dilution(terms, event))
    except Exception:
        # Retain evidence only for the exact same immutable document identity.
        if (previous.get('captured_at') and previous.get('source_url') == event['url']
                and previous.get('published_at') == event['published_at']):
            result.update(previous, status='stale', attempted_at=at.isoformat())
    return result


def enrich_saved(connect, at, limit=2, fetch=None, clock=None):
    import json
    from company_context import stamp, now
    from financing_jobs import claim, finish
    clock = clock or now
    c = connect()
    try:
        rows = [dict(r) for r in c.execute('SELECT * FROM company_context_events').fetchall()]
    finally:
        c.close()
    due = []
    for row in rows:
        event = json.loads(row['payload'])
        old = event.get('document') or {}
        if old.get('status') == 'unsupported_document' and old.get('version') == VERSION:
            continue
        attempted = stamp(old.get('attempted_at'))
        if old.get('version') != VERSION or not attempted or at - attempted >= timedelta(days=7 if old.get('status') == 'partial' else 1):
            due.append((row, event, old))
    due.sort(key=lambda entry: ((entry[2].get('attempted_at') or ''), entry[1].get('published_at') or ''))
    processed = 0
    for row, event, old in due:
        if processed >= max(0, min(int(limit), 4)):
            break
        token = claim(connect, row['event_key'], clock(), row['payload'])
        if not token:
            continue
        processed += 1
        event['document'] = collect(event, at, old, fetch)
        c = connect()
        try:
            if not finish(c, row['event_key'], token, event['document']['status'], clock()):
                continue
            cursor = c.execute('UPDATE company_context_events SET payload=? WHERE event_key=? AND payload=?',
                      (json.dumps(event), row['event_key'], row['payload']))
            if cursor.rowcount:
                from company_evidence import record
                record(c, row['event_key'], row['ticker'], row['identity'], 'financing_document', json.loads(row['payload']), at)
                record(c, row['event_key'], row['ticker'], row['identity'], 'financing_document', event, at)
            else:
                c.execute('UPDATE financing_document_jobs SET state=? WHERE event_key=?', ('superseded', row['event_key']))
            c.commit()
        finally:
            c.close()
    return {'processed': processed, 'due_observed': len(due)}
