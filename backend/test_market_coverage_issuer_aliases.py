from pathlib import Path


def test_market_coverage_registers_observed_issuer_names():
    text = (Path(__file__).resolve().parent / "market_coverage_runtime.py").read_text(encoding="utf-8").lower()
    assert "deep value driller as" in text
    assert "aker asa" in text
    assert "insider_runtime.issuers.update" in text
