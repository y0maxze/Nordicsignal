import high_conviction_shadow_dataset_v2_runtime as dataset


def test_forward_outcome_measures_return_path_and_alpha(monkeypatch):
    snapshot = {
        "market_date": "2026-01-02",
        "entry_price": 100.0,
        "benchmark_entry_close": 1000.0,
    }
    rows = [
        {"date": "2026-01-02", "close": 100.0},
        {"date": "2026-01-05", "close": 95.0},
        {"date": "2026-01-06", "close": 110.0},
    ]
    benchmark = [
        {"date": "2026-01-02", "close": 1000.0},
        {"date": "2026-01-05", "close": 1010.0},
        {"date": "2026-01-06", "close": 1020.0},
    ]
    monkeypatch.setattr(
        dataset.market,
        "_market_return_for_target",
        lambda entry, target_date, bench: ({"date": target_date, "close": 1020.0}, 2.0),
    )
    out = dataset._forward_outcome(snapshot, rows, benchmark, 2)
    assert round(out["return_pct"], 4) == 10.0
    assert round(out["excess_return_pct"], 4) == 8.0
    assert round(out["max_drawdown_pct"], 4) == -5.0
    assert round(out["max_runup_pct"], 4) == 10.0


def test_forward_outcome_requires_mature_horizon():
    snapshot = {"market_date": "2026-01-02", "entry_price": 100.0, "benchmark_entry_close": None}
    rows = [{"date": "2026-01-02", "close": 100.0}, {"date": "2026-01-05", "close": 101.0}]
    assert dataset._forward_outcome(snapshot, rows, [], 5) is None


def test_market_date_prefers_frozen_close_date():
    result = {
        "generated_at": "2026-09-10T08:00:00+00:00",
        "reversal": {"metrics": {"close_date": "2026-09-09"}},
    }
    assert dataset._market_date(result) == "2026-09-09"


def test_dataset_policy_is_shadow_only(monkeypatch):
    class Row(dict):
        pass

    class FakeConn:
        def execute(self, sql, params=()):
            if "COUNT(*) AS n,COUNT(DISTINCT ticker)" in sql:
                return FakeResult([Row(n=0, tickers=0, first_date=None, last_date=None)])
            if "GROUP BY o.horizon_days" in sql:
                return FakeResult([])
            if "ORDER BY market_date DESC" in sql:
                return FakeResult([])
            raise AssertionError(sql)
        def close(self):
            pass

    class FakeResult:
        def __init__(self, rows):
            self.rows = rows
        def fetchone(self):
            return self.rows[0] if self.rows else None
        def fetchall(self):
            return self.rows

    monkeypatch.setattr(dataset, "connect", lambda: FakeConn())
    out = dataset.dataset_status()
    assert out["activation_enabled"] is False
    assert out["automatic_threshold_changes"] is False
    assert "correlated" in out["independence_warning"]
    assert out["selection_unit"] == "daily point-in-time snapshot"


def test_model_horizons_are_fixed():
    assert dataset.HORIZONS == (1, 5, 20, 60)
    assert dataset.MODEL_VERSION == "high_conviction_shadow_dataset_v2"
