from pathlib import Path


def test_market_coverage_contract_preserves_signal_policy():
    text = (Path(__file__).resolve().parent / "market_coverage_runtime_contract.md").read_text(encoding="utf-8").lower()
    assert "preserve the existing score formula and thresholds" in text
    assert "separate from primary-insider transactions" in text
    assert "never permission to invent transaction value" in text
