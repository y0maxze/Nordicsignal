import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _source(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_runtime_is_loaded_before_insider_market_modules():
    source = _source("sitecustomize.py")
    assert '"market_coverage_runtime"' in source
    assert source.index('"market_coverage_runtime"') < source.index('"insider_market_runtime"')


def test_observed_blind_spots_are_registered():
    source = _source("market_coverage_runtime.py")
    tree = ast.parse(source)
    assert '"DVD", "Deep Value Driller"' in source
    assert '"AKER", "Aker ASA"' in source
    assert '"DVD": ("Deep Value Driller AS"' in source
    assert '"AKER": ("Aker ASA"' in source
    assert "main.UNIVERSE.append(row)" in source
    assert "main.TICKERS[:]" in source


def test_coverage_fix_does_not_tune_investment_policy():
    source = _source("market_coverage_runtime.py").lower()
    forbidden = ("score_threshold", "signal_threshold", "position_size", "activation = true")
    assert all(token not in source for token in forbidden)
