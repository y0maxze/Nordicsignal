from pathlib import Path


def test_no_dvd_or_aker_score_override_exists():
    text = (Path(__file__).resolve().parent / "market_coverage_runtime.py").read_text(encoding="utf-8")
    assert "refresh_one" not in text
    assert "insider_score" not in text
    assert "signal_label" not in text
