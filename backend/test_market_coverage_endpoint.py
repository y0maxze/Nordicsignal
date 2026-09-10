from pathlib import Path


def test_coverage_endpoint_is_observability_not_recommendation():
    text = (Path(__file__).resolve().parent / "market_coverage_status_runtime.py").read_text(encoding="utf-8").lower()
    assert "observed_gap_additions" in text
    assert "coverage expansion only" in text
    assert "recommendation" not in text
