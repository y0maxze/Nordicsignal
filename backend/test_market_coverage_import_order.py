from pathlib import Path


def test_coverage_runtime_loads_before_extra_api_install_in_main():
    root = Path(__file__).resolve().parent
    site = (root / "sitecustomize.py").read_text(encoding="utf-8")
    main = (root / "main.py").read_text(encoding="utf-8")
    assert '"market_coverage_runtime"' in site
    assert main.index("import sitecustomize") < main.index("extra_api.install(app)")
