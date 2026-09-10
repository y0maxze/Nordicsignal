from pathlib import Path


def test_runtime_declares_coverage_only_change():
    text = (Path(__file__).resolve().parent / "market_coverage_runtime.py").read_text(encoding="utf-8").lower()
    assert "changes coverage only" in text
    assert "does not change component" in text
