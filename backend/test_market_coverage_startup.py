import importlib
import sys
from pathlib import Path


def test_market_coverage_runtime_parses_and_has_unique_tickers():
    source = (Path(__file__).resolve().parent / "market_coverage_runtime.py").read_text(encoding="utf-8")
    compile(source, "market_coverage_runtime.py", "exec")
    assert source.count('(\"DVD\", \"Deep Value Driller\"') == 1
    assert source.count('(\"AKER\", \"Aker ASA\"') == 1


def test_sitecustomize_parses_after_runtime_addition():
    source = (Path(__file__).resolve().parent / "sitecustomize.py").read_text(encoding="utf-8")
    compile(source, "sitecustomize.py", "exec")
