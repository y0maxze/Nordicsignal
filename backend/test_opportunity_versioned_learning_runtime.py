import json

import opportunity_version_identity_runtime as identity_extension
import opportunity_versioned_learning_runtime as versioned


def _balanced_rows(per_horizon=24):
    tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"]
    sectors = ["Energy", "Financials", "Seafood", "Technology"]
    regimes = ["RISK_ON", "NEUTRAL"]
    rows = []
    event_id = 1
    for horizon in versioned.REQUIRED_HORIZONS:
        for i in range(per_horizon):
            rows.append({
                "event_id": event_id,
                "horizon_days": horizon,
                "return_pct": 4.0 if i % 4 else -1.0,
                "label": "EARLY_OPPORTUNITY" if i % 2 else "WATCH_CONFLUENCE",
                "ticker": tickers[i % len(tickers)],
                "sector": sectors[i % len(sectors)],
                "regime": regimes[i % len(regimes)],
                "benchmark_return_pct": 1.0,
                "excess_return_pct": 2.0 if i % 4 else -0.5,
            })
            event_id += 1
    return rows


def _base_report():
    by_label = {}
    for label in ("WATCH_CONFLUENCE", "EARLY_OPPORTUNITY", "EARLY_OPPORTUNITY_HIGH"):
        horizons = {}
        for horizon in versioned.HORIZONS:
            n = 12 if horizon == 10 and label != "EARLY_OPPORTUNITY_HIGH" else 0
            horizons[str(horizon)] = {
                "n": n,
                "event_count": 12,
                "settled_event_pct": 100.0 if n else 0.0,
                "mean_return_pct": 2.0 if n else None,
                "median_return_pct": 2.0 if n else None,
                "positive_rate_pct": 75.0 if n else None,
                "sample_status": "insufficient",
                "minimum_sample_size": versioned.MIN_SAMPLE,
            }
        by_label[label] = {"events": 12, "horizons": horizons, "calibration_ready": False}

    horizons = {}
    for horizon in versioned.HORIZONS:
        required = horizon in versioned.REQUIRED_HORIZONS
        horizons[str(horizon)] = {
            "n": 24 if required else 0,
            "event_count": 24,
            "settled_event_pct": 100.0 if required else 0.0,
            "mean_return_pct": 2.5 if required else None,
            "median_return_pct": 2.0 if required else None,
            "positive_rate_pct": 75.0 if required else None,
            "sample_status": "usable" if required else "insufficient",
            "minimum_sample_size": versioned.MIN_SAMPLE,
        }
    return {
        "events": 24,
        "horizons": horizons,
        "by_label": by_label,
        "calibration": {
            "ready": True,
            "minimum_sample_size": versioned.MIN_SAMPLE,
            "required_horizons": list(versioned.REQUIRED_HORIZONS),
        },
    }


def test_fingerprint_is_stable_and_sensitive():
    assert versioned._fingerprint(["a", "b", 1]) == versioned._fingerprint(["a", "b", 1])
    assert versioned._fingerprint(["a", "b", 1]) != versioned._fingerprint(["a", "b", 2])
    assert len(versioned._fingerprint(["anything"])) == 16


def test_active_identity_is_deterministic_and_scoped():
    first = identity_extension._current_identity()
    second = identity_extension._current_identity()
    assert first == second
    assert len(first["signal_fingerprint"]) == 16
    assert len(first["learning_policy_fingerprint"]) == 16
    assert first["signal_model_id"].startswith(first["signal_version"] + ":")
    scope = first["identity_scope"]
    assert scope.startswith("signal_rules+meaningful_insider_buys+smart_money_role_quality+canonical_insider_routing+first_observed_semantics+discovery_policy")
    assert "statistical_confidence_policy" in scope
    assert "chronological_walk_forward_policy" in scope


def test_discovery_policy_change_changes_learning_identity(monkeypatch):
    before = identity_extension._current_identity()
    monkeypatch.setattr(identity_extension.coverage, "DISCOVERY_PER_SCAN", identity_extension.coverage.DISCOVERY_PER_SCAN + 1)
    after = identity_extension._current_identity()
    assert before["signal_fingerprint"] == after["signal_fingerprint"]
    assert before["learning_policy_fingerprint"] != after["learning_policy_fingerprint"]
    assert before["learning_policy_id"] != after["learning_policy_id"]


def test_first_observed_semantics_change_changes_signal_identity(monkeypatch):
    before = identity_extension._current_identity()

    def changed_first_observed(result, name=None):
        return {"emitted": False, "reason": "test_changed_semantics"}

    monkeypatch.setattr(identity_extension.coverage, "_record_first_observed", changed_first_observed)
    after = identity_extension._current_identity()
    assert before["signal_fingerprint"] != after["signal_fingerprint"]
    assert before["signal_model_id"] != after["signal_model_id"]


def test_canonical_insider_routing_change_changes_signal_identity(monkeypatch):
    before = identity_extension._current_identity()

    def changed_router(payload, window_days=14):
        return {"insider_signal_v2": {"policy": "changed-for-test"}}

    monkeypatch.setattr(identity_extension.insider_bridge, "analyze_insider_policy", changed_router)
    after = identity_extension._current_identity()
    assert before["signal_fingerprint"] != after["signal_fingerprint"]
    assert before["signal_model_id"] != after["signal_model_id"]


def test_payload_version_is_audit_metadata_not_verified_fingerprint():
    event = {"payload": json.dumps({"opportunity": {"version": "2026-08-30-v1.4"}})}
    assert versioned._payload_signal_version(event) == "2026-08-30-v1.4"
    assert versioned._payload_signal_version({"payload": "{}"}) == "unknown"
    active = identity_extension._current_identity()["signal_model_id"]
    assert f"legacy:{versioned._payload_signal_version(event)}" != active


def test_version_scoped_sample_must_pass_all_existing_gates():
    report = _base_report()
    versioned._apply_scoped_gates(report, _balanced_rows())
    assert report["calibration"]["raw_sample_ready"] is True
    assert report["calibration"]["independence_ready"] is True
    assert report["calibration"]["market_regime_ready"] is True
    assert report["calibration"]["ready"] is True
    assert report["quality_gate"]["checks"]["sample_independence"] is True
    assert report["quality_gate"]["checks"]["market_regime_diversity"] is True
    assert report["quality_gate"]["checks"]["positive_market_adjusted_median"] is True
    assert report["quality_gate"]["status"] == "PASS_CANDIDATE"


def test_version_scoped_regime_concentration_blocks_readiness():
    rows = _balanced_rows()
    for row in rows:
        row["regime"] = "RISK_ON"
    report = _base_report()
    versioned._apply_scoped_gates(report, rows)
    assert report["calibration"]["raw_sample_ready"] is True
    assert report["calibration"]["independence_ready"] is True
    assert report["calibration"]["market_regime_ready"] is False
    assert report["calibration"]["ready"] is False
    assert report["quality_gate"]["status"] == "REVIEW"
