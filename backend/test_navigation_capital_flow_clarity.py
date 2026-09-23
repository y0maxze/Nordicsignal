from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"

def text(name):
    return (FRONTEND / name).read_text(encoding="utf-8")

def test_secondary_history_stays_available_in_analysis_shell_not_primary_mobile_nav():
    shell = text("ui_shell.js")
    nav = text("mobile_nav.js")
    assert 'href="/history"' not in shell
    assert 'href="/learning">Historikk' not in shell
    assert 'href="/history"' not in nav

def test_capital_flow_exposes_research_quality_without_signal_claim():
    js = text("capital-flow.js")
    html = text("capital-flow.html")
    assert "research_quality" in js
    assert "quality_band" in js
    assert "Kildekvalitet er kun et transparent forsknings-/presentasjonsmål" in html
    assert "uten at dette påvirker NordicSignal-score" in html

def test_capital_flow_is_available_offline_with_its_runtime():
    sw = text("sw.js")
    assert "'/capital-flow'" in sw
    assert "'/capital-flow.js'" in sw
    assert "nordicsignal-shell-v5" in sw
