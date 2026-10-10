"""Reviewed context only. Never settles returns or certifies complete coverage."""
from collections import Counter
from copy import deepcopy
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from instrument_identifiers import valid_isin

DATA = Path(__file__).parent / 'data' / 'corporate_action_evidence.json'


def _day(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('invalid date')
    return date.fromisoformat(value)


def _instant(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timezone required')
    return parsed


def _source(value):
    url = urlparse(value)
    return url.scheme == 'https' and bool(url.hostname) and not url.username and not url.password


def project(document, now=None):
    """Invalid, conflicting and future-reviewed records stay out of the projection."""
    now = now or datetime.now(timezone.utc)
    output = {'status': 'partial', 'coverage': 'selected_events_only',
              'complete_for_returns': False, 'score_effect': 0, 'items': [], 'quarantined_count': 0}
    if not isinstance(document, dict) or document.get('schema_version') != 1 or not isinstance(document.get('items'), list):
        return output | {'status': 'unavailable'}
    valid = []
    for original in document['items']:
        try:
            x = deepcopy(original)
            if not (isinstance(x['id'], str) and x['id']): raise ValueError('invalid evidence')
            if not (type(x['revision']) is int and x['revision'] >= 1): raise ValueError('invalid evidence')
            if not (re.fullmatch(r'[A-Z0-9.-]{1,16}', x['ticker']) and valid_isin(x['isin'])): raise ValueError('invalid evidence')
            if not (x['type'] == 'cash_dividend' and x['status'] == 'declared'): raise ValueError('invalid evidence')
            if not (isinstance(x['amount'], (int, float)) and not isinstance(x['amount'], bool) and 0 < x['amount'] < 1e9): raise ValueError('invalid evidence')
            if not (re.fullmatch(r'[A-Z]{3}', x['currency'])): raise ValueError('invalid evidence')
            if not (_day(x['approval_date']) < _day(x['ex_date']) <= _day(x['record_date']) <= _day(x['payment_date_expected'])): raise ValueError('invalid evidence')
            if not (x['payment_status'] == 'expected_not_confirmed'): raise ValueError('invalid evidence')
            if not (_day(x['source_published_date']) <= _instant(x['reviewed_at']).date()): raise ValueError('invalid evidence')
            if not (_instant(x['reviewed_at']) <= now): raise ValueError('invalid evidence')
            if not (_source(x['source_url']) and _source(x['identity_source_url'])): raise ValueError('invalid evidence')
            # The identity citation must actually identify this ISIN, not merely a ticker search.
            if not (urlparse(x['identity_source_url']).hostname == 'live.euronext.com'): raise ValueError('invalid evidence')
            if not ('/product/equities/' + x['isin'] + '-' in urlparse(x['identity_source_url']).path): raise ValueError('invalid evidence')
            if not (x['source_pages'] and x['source_title'] and x['issuer']): raise ValueError('invalid evidence')
            valid.append(x)
        except (AssertionError, KeyError, TypeError, ValueError, AttributeError):
            output['quarantined_count'] += 1
    keys = Counter((x['isin'], x['type'], x['ex_date']) for x in valid)
    ids = Counter(x['id'] for x in valid)
    for x in valid:
        if keys[(x['isin'], x['type'], x['ex_date'])] > 1 or ids[x['id']] > 1:
            output['quarantined_count'] += 1
        else:
            output['items'].append(x)
    return output


def snapshot(ticker=None):
    try:
        result = project(json.loads(DATA.read_text()))
    except (OSError, ValueError):
        return {'status': 'unavailable', 'coverage': 'unknown', 'complete_for_returns': False,
                'score_effect': 0, 'items': [], 'quarantined_count': 0}
    if ticker is not None:
        ticker = str(ticker).upper().removesuffix('.OL')
        result['items'] = [x for x in result['items'] if x['ticker'] == ticker]
    return result


def window_context(items, ticker, start, end):
    """Retrospective ticker context, NOT proof of the old record's instrument identity."""
    try:
        first, last = _day(start), _day(end)
    except (TypeError, ValueError):
        return []
    return [dict(x, association='ticker_context_not_historical_identity', retrospective=True)
            for x in items if x['ticker'] == ticker and first < _day(x['ex_date']) <= last]
