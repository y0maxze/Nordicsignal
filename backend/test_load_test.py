import load_test


def test_percentile_uses_nearest_rank():
    values = [1, 2, 3, 4, 5]
    assert load_test.percentile(values, 50) == 3
    assert load_test.percentile(values, 95) == 5
    assert load_test.percentile([], 95) == 0.0


def test_run_load_test_aggregates_results(monkeypatch):
    outcomes = iter([
        (True, 10.0, 200),
        (True, 20.0, 200),
        (False, 30.0, 503),
        (True, 40.0, 200),
    ])

    monkeypatch.setattr(load_test, '_request', lambda base_url, path, timeout: next(outcomes))
    result = load_test.run_load_test(
        'https://example.test',
        users=2,
        requests=4,
        paths=('/api/health', '/api/stocks'),
        timeout=1.0,
    )

    assert result['requests'] == 4
    assert result['successes'] == 3
    assert result['failures'] == 1
    assert result['error_rate_pct'] == 25.0
    assert result['latency_ms']['p50'] == 20.0
    assert result['latency_ms']['p95'] == 40.0
    assert result['statuses'] == {'200': 3, '503': 1}
