"""Bounded official-document evidence. No model, push or per-GET network work.

Version 5 handles English and Norwegian labelled key-information notices.
It preserves the original field text, including qualifications; unstructured prose,
conflicting labels and multi-offering titles are not reconciled automatically.
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from html.parser import HTMLParser
from urllib.parse import urlsplit
import hashlib
import re

VERSION = 5
MAX_BYTES = 1_000_000
# Final fields often include several paragraphs of conditions and legal text.
# Preserve those together; never truncate to a bare price or exact share count.
MAX_TERM_CHARS = 10_000
LABELS = {
    'subscription_price': ('subscription price', 'tegningskurs'),
    'new_shares': ('number of new shares', 'number of new shares in the rights issue'),
    'maximum_new_shares': ('maximum number of new shares', 'maximum number of new shares to be issued in the rights issue', 'maksimalt antall nye aksjer', 'maksimum antall nye aksjer'),
    'existing_shares': ('number of existing shares before the rights issue',),
    'share_class': ('class of existing and new shares',),
    'gross_proceeds': ('gross proceeds',),
    'net_proceeds': ('net proceeds',),
    'subscription_period': ('subscription period', 'tegningsperiode'),
    'subscription_deadline': ('subscription deadline', 'tegningsfrist'),
    'ex_date': ('ex-date', 'ex-dato', 'first day of trading exclusive right to receive subscription rights (ex-date)'),
    'record_date': ('record date', 'record date (eierregisterdato)'),
    'settlement_date': ('settlement date',),
    'delivery_date': ('delivery date',),
    'subscription_rights': ('ratio subscription rights',),
    # The official Norwegian template distinguishes rights per old share from
    # new shares per right. Preserve both verbatim; never invert a ratio.
    'allocation_ratio': ('tildelingsforhold', 'ratio preferential rights'),
    'subscription_ratio': ('tegningsforhold', 'subscription ratio'),
    'announcement_date': ('dato for når vilkårene for fortrinnsrettsemisjonen ble annonsert', 'date on which the terms and conditions of the preferential rights issue were announced', 'date on which the terms and conditions of the subsequent offering were announced', 'date on which the terms and conditions of the repair issue were announced', 'date on which the terms and conditions of the subsequent repair offering were announced'),
    'last_day_including': ('siste dag inklusive', 'last day of trading in the shares including subscription rights', 'last day of trading including right to receive subscription rights', 'last day including right to receive subscription rights', 'last day including right to receive subscription rights in the subsequent repair offering', 'last day including rights', 'last day including right'),
    'decision_date': ('vedtaksdato', 'date of approval'),
    'expected_decision_date': ('expected date of approval',),
    'rights_listing': ('skal rettene notere ja/nei', 'skal rettene noteres ja/nei', 'will the rights be listed', 'shall the rights be listed', 'will the rights be listed yes/no', 'will the subscription rights be listed'),
    'rights_isin': ('isin på fortrinnsrettene', 'isin for fortrinnsrettene', 'isin for the preferential rights'),
    'arranger': ('tilrettelegger', 'manager', 'managers'),
    'settlement_agent': ('oppgjørsagent',),
    'additional_information': ('øvrig informasjon (valgfritt)', 'øvrig informasjon', 'other information'),
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
    from company_context import norm
    titles = re.findall(r'<h1\b[^>]*>(.*?)</h1>', html, re.I | re.S)
    if len(titles) != 1 or _text(titles[0]).casefold() != ' '.join(event['title'].split()).casefold():
        raise ValueError('document title mismatch')
    issuers = re.findall(r'<h3\b[^>]*>\s*(?:Issuer|Utsteder|Company Name)\s*</h3>\s*<p\b[^>]*>(.*?)</p>', html, re.I | re.S)
    if not issuers or {norm(_text(v)) for v in issuers} != {event['identity']}:
        raise ValueError('document issuer mismatch')
    # Only labelled key-information documents with one financing type are supported.
    if not supported_title(event['title']):
        return {}, 'unsupported_document'
    parser = PageText()
    parser.feed(html)
    return parse_lines(parser.lines)


def _field_at(lines, index):
    """Exact labels only, with one list marker and at most three wrapped lines.

    Unknown colon-bearing text is never a field boundary: it can qualify the
    preceding number. Keep the source label, including any bullet, as evidence.
    """
    parts = []
    for end in range(index, min(index + 3, len(lines))):
        parts.append(lines[end].strip())
        label, sep, value = ' '.join(parts).partition(':')
        if sep:
            lookup = re.sub(r'^[-*•·]\s*', '', label).strip().casefold()
            key = LABEL_MAP.get(lookup)
            return (key, label, value, end + 1) if key else None
    return None


def parse_lines(lines):
    found = {}
    index = 0
    while index < len(lines):
        field = _field_at(lines, index)
        if not field:
            index += 1
            continue
        key, label, value, following_index = field
        # Do not stop at an arbitrary heading/blank line or discard trailing
        # prose: it may contain the offer's conditions, not just a footer.
        continuation = []
        while following_index < len(lines) and not _field_at(lines, following_index):
            continuation.append(lines[following_index])
            following_index += 1
        value = ' '.join([value.strip(), *continuation]).strip()
        evidence = label + ': ' + value
        found.setdefault(key, []).append((evidence, value))
        index = following_index
    terms = {}
    for key, candidates in found.items():
        # Even duplicate values can refer to different tranches. Do not pick one.
        if len(candidates) != 1:
            terms[key] = {'status': 'ambiguous', 'value': None, 'evidence': None}
            continue
        evidence, value = candidates[0]
        if not value or len(evidence) > MAX_TERM_CHARS:
            continue
        terms[key] = {'status': 'documented', 'value': value, 'evidence': evidence}
    return terms, 'partial' if terms else 'no_supported_terms'


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


def supported_title(title):
    from company_context import FINANCING_TYPES
    kinds = {kind for kind, pattern in FINANCING_TYPES if pattern.search(title)}
    return len(kinds) == 1 and bool(re.search(r'\b(?:key information|nøkkelinformasjon)\b', title, re.I))


def collect(event, at, previous=None, fetch=None):
    previous = previous or {}
    result = {'version': VERSION, 'attempted_at': at.isoformat(), 'captured_at': None,
              'status': 'unavailable', 'terms': {}, 'dilution': dilution({}, event),
              'source_url': event['url'], 'published_at': event['published_at']}
    if not supported_title(event['title']):
        result['status'] = 'unsupported_document'
        return result
    try:
        if event.get('source_type')=='newsweb_oam':
            from company_newsweb import document
            terms,status,digest=document(event,fetch)
        else:
            if not source_allowed(event['url']):
                raise ValueError('unverified source')
            html = (fetch or fetch_document)(event['url'])
            if not isinstance(html, str) or len(html.encode('utf-8')) > MAX_BYTES:
                raise ValueError('invalid document')
            terms, status = parse_terms(html, event)
            digest=hashlib.sha256(html.encode('utf-8')).hexdigest()
        result.update(status=status, terms=terms, captured_at=at.isoformat(),
                      content_sha256=digest,
                      dilution=dilution(terms, event))
    except Exception:
        # Retain evidence only for the exact same immutable document identity.
        if (previous.get('version') == VERSION and previous.get('captured_at') and previous.get('source_url') == event['url']
                and previous.get('published_at') == event['published_at']):
            result.update(previous, status='stale', attempted_at=at.isoformat())
    return result


def public_document(document):
    """Outdated extraction may have lost qualifications; never display as facts."""
    if document.get('version') == VERSION:
        return document
    return {**document, 'status':'revalidation_required', 'terms':{},
            'dilution':{'status':'unknown'}, 'stored_parser_version':document.get('version')}


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
        if old.get('version') != VERSION or not attempted or at - attempted >= timedelta(days=7 if old.get('status') in {'partial', 'no_supported_terms'} else 1):
            due.append((row, event, old))
    # Historical catch-up must not starve recent supported documents behind a
    # stream of older unsupported notices. Within each group, never-attempted
    # documents precede retries, then newest publication first.
    due.sort(key=lambda entry: (not supported_title(entry[1]['title']),
                               entry[2].get('attempted_at') or '',
                               -(stamp(entry[1].get('published_at')).timestamp() if stamp(entry[1].get('published_at')) else 0)))
    processed = 0
    for row, event, old in due:
        if processed >= max(0, min(int(limit), 4)):
            break
        token = claim(connect, row['event_key'], clock(), row['payload'])
        if not token:
            continue
        processed += 1
        started = clock()
        event['document'] = collect(event, started, old, fetch)
        finished = clock()
        if event['document']['status'] in {'partial', 'no_supported_terms'} and event['document'].get('captured_at'):
            event['document']['captured_at'] = finished.isoformat()
        c = connect()
        try:
            if not finish(c, row['event_key'], token, event['document']['status'], finished):
                continue
            cursor = c.execute('UPDATE company_context_events SET payload=? WHERE event_key=? AND payload=?',
                      (json.dumps(event), row['event_key'], row['payload']))
            if cursor.rowcount:
                from company_evidence import record
                record(c, row['event_key'], row['ticker'], row['identity'], 'financing_document', json.loads(row['payload']), finished)
                record(c, row['event_key'], row['ticker'], row['identity'], 'financing_document', event, finished)
            else:
                c.execute('UPDATE financing_document_jobs SET state=? WHERE event_key=?', ('superseded', row['event_key']))
            c.commit()
        finally:
            c.close()
    return {'processed': processed, 'due_observed': len(due)}
