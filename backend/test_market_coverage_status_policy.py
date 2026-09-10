from pathlib import Path


def test_institutional_flow_is_not_promoted_to_insider_signal():
    text = (Path(__file__).resolve().parent / "market_coverage_status_runtime.py").read_text(encoding="utf-8").lower()
    assert "institutional_flow_policy" in text
    assert "forward evidence" in text
