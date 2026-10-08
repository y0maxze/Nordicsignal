"""Source-reviewed company research; never a model, quote or PIT input.

Versioned snapshots are updated through source review in a PR, not by GETs.
Ticker + normalized issuer name require independent ISIN or NewsWeb issuer
corroboration. Conflicting identifiers fail closed, including ticker reuse.
"""
from copy import deepcopy
from calendar import monthrange
from datetime import date, datetime, timedelta
from functools import lru_cache
import json
import math
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


@lru_cache(maxsize=1)
def profiles():
    return json.loads((Path(__file__).parent / 'data' / 'company_reviewed_research.json').read_text())['profiles']


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result if result.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def valid_source(source, reviewed):
    url = urlsplit(source['url'])
    published = date.fromisoformat(source['published_on']) if source.get('published_on') else None
    return (url.scheme == 'https' and bool(url.hostname) and not url.username and not url.password
            and (published is None or published <= reviewed.date()))


def validate(p):
    """Reject incomplete provenance and incompatible financial comparisons."""
    reviewed = timestamp(p['reviewed_at'])
    if not reviewed or not p['sources'] or not all(valid_source(s, reviewed) for s in p['sources'].values()):
        raise ValueError('Invalid research provenance')
    def sourced(item):
        if item['source_id'] not in p['sources'] or not item['locator']:
            raise ValueError('Missing source or locator')
    for item in [p['business'], *p['developments'], *p['risks'], p['next_event']]:
        sourced(item)
    for group in p['financial_groups']:
        sourced(group)
        if group['currency'] not in {'NOK', 'SEK'} or group['scale'] != 1000 or group['scope'] != 'group':
            raise ValueError('Invalid financial unit or scope')
        if group['kind'] not in {'quarter', 'half_year', 'annual', 'balance'}:
            raise ValueError('Invalid period type')
        end, previous_end = map(date.fromisoformat, (group['end'], group['previous_end']))
        if not previous_end < end <= reviewed.date():
            raise ValueError('Invalid period end')
        if group['kind'] != 'balance':
            start, previous_start = map(date.fromisoformat, (group['start'], group['previous_start']))
            months = {'quarter': 3, 'half_year': 6, 'annual': 12}[group['kind']]
            for first, last in ((start, end), (previous_start, previous_end)):
                if (first.day != 1 or last.day != monthrange(last.year, last.month)[1]
                        or last.month - first.month + 1 != months or first.year != last.year):
                    raise ValueError('Incompatible period duration')
            if (start.month, end.month) != (previous_start.month, previous_end.month):
                raise ValueError('Incompatible comparison season')
        for metric in group['metrics']:
            if not metric['label'] or any(type(metric[k]) not in (int, float) or not math.isfinite(metric[k]) for k in ('value', 'previous')):
                raise ValueError('Invalid financial value')
    for transaction in p['transactions']:
        if not transaction['steps']:
            raise ValueError('Missing transaction evidence')
        dates = []
        for step in transaction['steps']:
            sourced(step)
            day = date.fromisoformat(step['date'])
            if day > reviewed.date():
                raise ValueError('Future transaction evidence')
            dates.append(day)
        if dates != sorted(dates):
            raise ValueError('Unordered transaction evidence')
    return reviewed


def project(ticker, identity, profile, events, at):
    for original in profiles():
        if ticker != original['ticker'] or identity != original['identity']:
            continue
        reviewed = validate(original)
        if reviewed > at:
            return None
        if profile.get('isin_status') == 'ambiguous':
            return None
        isin = profile.get('isin')
        expected_isin = original.get('isin')
        issuer_ids = {e.get('source_issuer_id') for e in events if e.get('source_type') == 'newsweb_oam'}
        issuer_ids.discard(None)
        if issuer_ids and issuer_ids != {original['newsweb_issuer_id']}:
            return None
        if isin and expected_isin and isin != expected_isin:
            return None
        if not (isin and isin == expected_isin) and issuer_ids != {original['newsweb_issuer_id']}:
            return None
        p = deepcopy(original)
        p['status'] = 'reviewed_snapshot'
        p['newer_financing_count'] = len({e.get('url') for e in events
                                         if timestamp(e.get('published_at')) and timestamp(e['published_at']) > reviewed})
        reviewed_ids = {s.get('message_id') for s in p['sources'].values()} - {None}
        p['source_correction_observed'] = any((e.get('source_message_id') in reviewed_ids and e.get('corrected_by_message_id'))
                                              or e.get('correction_for_message_id') in reviewed_ids for e in events)
        p['needs_review'] = bool(at - reviewed > timedelta(days=35) or p['newer_financing_count'] or p['source_correction_observed'])
        today = at.astimezone(ZoneInfo('Europe/Oslo')).date()
        p['next_event']['passed'] = date.fromisoformat(p['next_event']['date']) < today
        return p
    return None
