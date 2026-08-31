import opportunity_scan_failure_streak_runtime as runtime


def run(run_id, outcomes):
    return (
        {"run_id": run_id, "started_at": f"2026-08-3{run_id}T08:00:00+00:00"},
        [
            {"ticker": ticker, "outcome": outcome, "error_class": None, "error_message": None}
            for ticker, outcome in outcomes.items()
        ],
    )


def by_ticker(items):
    return {item["ticker"]: item for item in items}


def test_one_failure_is_transient():
    items = by_ticker(runtime._ticker_streaks([
        run(1, {"AAA": "SCAN_ERROR"}),
    ]))
    assert items["AAA"]["consecutive_failures"] == 1
    assert items["AAA"]["status"] == "TRANSIENT"


def test_two_consecutive_failures_are_warn():
    items = by_ticker(runtime._ticker_streaks([
        run(2, {"AAA": "RESULT_ERROR"}),
        run(1, {"AAA": "SCAN_ERROR"}),
    ]))
    assert items["AAA"]["consecutive_failures"] == 2
    assert items["AAA"]["status"] == "WARN"


def test_three_consecutive_failures_are_fail():
    items = by_ticker(runtime._ticker_streaks([
        run(3, {"AAA": "SNAPSHOT_MISSING"}),
        run(2, {"AAA": "RESULT_ERROR"}),
        run(1, {"AAA": "SCAN_ERROR"}),
    ]))
    assert items["AAA"]["consecutive_failures"] == 3
    assert items["AAA"]["status"] == "FAIL"


def test_success_breaks_failure_streak():
    items = by_ticker(runtime._ticker_streaks([
        run(3, {"AAA": "SCAN_ERROR"}),
        run(2, {"AAA": "SNAPSHOT_PRESENT"}),
        run(1, {"AAA": "SCAN_ERROR"}),
    ]))
    assert items["AAA"]["consecutive_failures"] == 1
    assert items["AAA"]["status"] == "TRANSIENT"


def test_missing_result_row_counts_as_collection_failure():
    items = by_ticker(runtime._ticker_streaks([
        run(3, {"BBB": "SNAPSHOT_PRESENT"}),
        run(2, {"AAA": "SCAN_ERROR", "BBB": "SNAPSHOT_PRESENT"}),
        run(1, {"AAA": "SCAN_ERROR", "BBB": "SNAPSHOT_PRESENT"}),
    ]))
    # AAA is missing from the newest completed run, then failed in the two before it.
    assert items["AAA"]["consecutive_failures"] == 3
    assert items["AAA"]["latest_outcome"] == "NOT_ATTEMPTED"
    assert items["AAA"]["status"] == "FAIL"


def test_successful_ticker_has_no_failure_item():
    items = by_ticker(runtime._ticker_streaks([
        run(2, {"AAA": "SNAPSHOT_PRESENT"}),
        run(1, {"AAA": "SCAN_ERROR"}),
    ]))
    assert "AAA" not in items


def test_policy_never_auto_deactivates():
    assert runtime.WARN_STREAK == 2
    assert runtime.FAIL_STREAK == 3
