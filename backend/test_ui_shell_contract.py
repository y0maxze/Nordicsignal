from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def test_shared_ui_assets_exist_and_are_cached():
    theme = (FRONTEND / "theme_mode.js").read_text(encoding="utf-8")
    shell = (FRONTEND / "ui_shell.js").read_text(encoding="utf-8")
    sw = (FRONTEND / "sw.js").read_text(encoding="utf-8")
    loader = (FRONTEND / "alert_nav_ui.js").read_text(encoding="utf-8")

    assert "nordicsignal-theme" in theme
    assert "data-theme" in (FRONTEND / "theme.css").read_text(encoding="utf-8")
    assert "Analyser valgt aksje" in shell
    assert "Hjem" in shell and "Før børs" in shell and "Signaler" in shell and "Portefølje" in shell and "Søk" in shell
    assert "/morning" in sw
    assert "/theme_mode.js" in sw and "/ui_shell.js" in sw
    assert "loadScript('/theme_mode.js'" in loader
    assert "loadScript('/ui_shell.js'" in loader


def test_morning_brief_page_uses_shared_theme_and_api():
    page = (FRONTEND / "morning.html").read_text(encoding="utf-8")
    assert "/theme.css" in page
    assert "/theme_mode.js" in page
    assert "/ui_shell.js" in page
    assert "/api/morning-brief" in page
    assert "Før børs" in page


def test_morning_brief_rows_open_related_stock():
    page = (FRONTEND / "morning.html").read_text(encoding="utf-8")
    assert "'/stock?ticker='" in page
    assert "data-stock-url" in page
    assert "Trykk for å åpne aksjen" in page
    assert "data-source-link" in page
    assert "e.target.closest('[data-source-link]')" in page


def test_mobile_bottom_nav_is_pinned_to_viewport():
    shell = (FRONTEND / "ui_shell.js").read_text(encoding="utf-8")
    assert "position:fixed!important" in shell
    assert "bottom:0!important" in shell
    assert "env(safe-area-inset-bottom)" in shell
    assert "translate3d(0,0,0)" in shell
    assert "contain:layout paint" in shell


def test_stock_tool_shell_keeps_core_tools_available():
    shell = (FRONTEND / "ui_shell.js").read_text(encoding="utf-8")
    for tool in ("overview", "opportunity", "readiness", "pressure", "insider", "news", "reports", "dividend", "short", "evidence", "backtest", "paper"):
        assert f"'{tool}'" in shell


def test_stock_tool_reorder_is_idempotent():
    shell = (FRONTEND / "ui_shell.js").read_text(encoding="utf-8")
    assert "const needsReorder=desired.some" in shell
    assert "if(needsReorder)" in shell
    assert "TOOL_ORDER.forEach(key=>" not in shell


def test_theme_is_visual_only():
    theme = (FRONTEND / "theme_mode.js").read_text(encoding="utf-8")
    shell = (FRONTEND / "ui_shell.js").read_text(encoding="utf-8")
    combined = theme + shell
    for forbidden in ("/api/refresh", "score=", "threshold", "EARLY_OPPORTUNITY_HIGH"):
        assert forbidden not in combined
