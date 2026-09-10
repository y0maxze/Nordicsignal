from pathlib import Path


def test_market_coverage_notes_keep_data_quality_distinctions():
    text = (Path(__file__).resolve().parent / "MARKET_COVERAGE_NOTES.md").read_text(encoding="utf-8")
    assert "1,700,000 shares" in text
    assert "outside the fixed 24-stock scored universe" in text
    assert "no DVD row" in text
    assert "must not be mislabeled as primary-insider trades" in text
