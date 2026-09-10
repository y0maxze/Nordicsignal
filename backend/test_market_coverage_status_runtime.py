from pathlib import Path


def test_market_coverage_status_is_loaded_and_keeps_flow_as_context():
    root = Path(__file__).resolve().parent
    site = (root / "sitecustomize.py").read_text(encoding="utf-8")
    source = (root / "market_coverage_status_runtime.py").read_text(encoding="utf-8")
    assert '"market_coverage_status_runtime"' in site
    assert '/api/market-coverage/status' in source
    assert 'institutional_flow_policy' in source
    assert 'context only' in source
