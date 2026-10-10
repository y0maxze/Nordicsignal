from copy import deepcopy
from datetime import datetime, timezone
import json
import pytest
import corporate_action_evidence as evidence

NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)


def document():
    return json.loads(evidence.DATA.read_text())


def test_reviewed_pilot_has_partial_coverage_and_distinct_payment_status():
    result = evidence.project(document(), NOW)
    assert len(result['items']) == 1 and result['quarantined_count'] == 0
    x = result['items'][0]
    assert x['isin'] == 'NO0010955917' and x['amount'] == 20.6 and x['ex_date'] == '2026-10-08'
    assert x['payment_status'] == 'expected_not_confirmed'
    assert result['complete_for_returns'] is False and result['score_effect'] == 0


@pytest.mark.parametrize('key,value', [
    ('isin', 'NO0010955918'), ('amount', None), ('amount', float('nan')),
    ('amount', True), ('ex_date', '2026-02-30'), ('record_date', '2026-10-01'),
    ('reviewed_at', '2026-10-10T05:00:00'), ('reviewed_at', '2026-10-12T00:00:00Z'),
    ('source_url', 'javascript:alert(1)'), ('identity_source_url', 'https://example.test/NO0010955917'),
])
def test_invalid_records_are_quarantined(key, value):
    d = document(); d['items'][0][key] = value
    result = evidence.project(d, NOW)
    assert result['items'] == [] and result['quarantined_count'] == 1


def test_conflicting_revisions_are_not_silently_selected():
    d = document(); other = deepcopy(d['items'][0]); other['amount'] = 21; other['revision'] = 2
    d['items'].append(other)
    result = evidence.project(d, NOW)
    assert result['items'] == [] and result['quarantined_count'] == 2


def test_window_excludes_buying_on_ex_date_and_unknown_periods():
    items = evidence.project(document(), NOW)['items']
    assert len(evidence.window_context(items, 'DVD', '2026-09-11', '2026-10-08')) == 1
    for ticker, start, end in [('DVD', '2026-10-08', '2026-10-09'), ('DVD', None, '2026-10-09'), ('OTHER', '2026-09-11', '2026-10-09')]:
        assert evidence.window_context(items, ticker, start, end) == []
    context = evidence.window_context(items, 'DVD', '2026-09-11', '2026-10-09')[0]
    assert context['retrospective'] is True and context['association'] == 'ticker_context_not_historical_identity'
