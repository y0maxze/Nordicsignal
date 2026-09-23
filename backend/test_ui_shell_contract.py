from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def test_shared_ui_assets_exist_and_are_cached():
    theme = (FRONTEND / "theme_mode.js").read_text(encoding="utf-8")
    shell = (FRONTEND / "ui_shell.js").read_text(encoding="utf-8")
    mobile_nav = (FRONTEND / "mobile_nav.js").read_text(encoding="utf-8")
    sw = (FRONTEND / "sw.js").read_text(encoding="utf-8")
    loader = (FRONTEND / "alert_nav_ui.js").read_text(encoding="utf-8")

    assert "nordicsignal-theme" in theme
    assert "data-theme" in (FRONTEND / "theme.css").read_text(encoding="utf-8")
    assert "Analyser valgt aksje" in shell
    assert "Marked" in mobile_nav and "Før børs" in mobile_nav and "Portefølje" not in mobile_nav
    assert "/app" in sw and "/morning" in sw
    assert "access_gate.js" not in sw and "portfolio_dashboard.js" not in sw
    assert "/theme_mode.js" in sw and "/ui_shell.js" in sw and "/mobile_nav.js" in sw
    assert "loadScript('/theme_mode.js'" in loader
    assert "loadScript('/mobile_nav.js'" in loader
    assert "loadScript('/ui_shell.js'" in loader


def test_morning_brief_page_uses_shared_theme_and_api():
    page = (FRONTEND / "morning.html").read_text(encoding="utf-8")
    assert "/theme.css" in page
    assert "/theme_mode.js" in page
    assert "/ui_shell.js" in page
    assert "/api/morning-brief" in page
    assert "Før børs" in page
    assert "RADAR" in page
    assert "Originalmelding" in page
    assert "source_context==='radar'" in page


def test_morning_brief_rows_open_related_stock():
    page = (FRONTEND / "morning.html").read_text(encoding="utf-8")
    assert "'/stock?ticker='" in page
    assert "data-stock-url" in page
    assert "Trykk for å åpne aksjen" in page
    assert "data-source-link" in page
    assert "e.target.closest('[data-source-link]')" in page


def test_mobile_nav_has_single_canonical_owner():
    nav = (FRONTEND / "mobile_nav.js").read_text(encoding="utf-8")
    shell = (FRONTEND / "ui_shell.js").read_text(encoding="utf-8")
    loader = (FRONTEND / "alert_nav_ui.js").read_text(encoding="utf-8")
    assert "function mount()" in nav
    assert "position:fixed!important" in nav
    assert "bottom:max(8px,env(safe-area-inset-bottom))!important" in nav
    assert "env(safe-area-inset-bottom)" in nav
    assert "nsMobileMoreToggle" not in nav
    assert "installMobileNav" not in shell
    assert "nsMobileMoreMenu" not in shell
    mobile_pos = loader.index("loadScript('/mobile_nav.js'")
    shell_pos = loader.index("loadScript('/ui_shell.js'")
    assert mobile_pos < shell_pos
    assert loader.count("loadScript('/mobile_nav.js'") == 1


def test_private_mobile_navigation_stays_minimal():
    nav = (FRONTEND / "mobile_nav.js").read_text(encoding="utf-8")
    assert "/app" in nav and "/morning" in nav
    for route in ("/capital-flow", "/alerts", "/ipo-radar", "/history", "/calendar", "/readiness", "/legal", "/holdings"):
        assert route not in nav


def test_capital_flow_mobile_ownership_rows_have_explicit_layout_and_touch_targets():
    page = (FRONTEND / "capital-flow.html").read_text(encoding="utf-8")
    assert 'grid-template-areas:"holder delta" "kind kind"' in page
    assert ".ownershipRow>div{grid-area:holder" in page
    assert ".ownershipRow>span{grid-area:kind" in page
    assert ".ownershipRow>strong{grid-area:delta" in page
    assert ".cfBtn,.cfChip{min-height:44px}" in page
    assert ".cfFilters{flex-wrap:nowrap;overflow-x:auto" in page


def test_stock_tool_shell_keeps_core_tools_available():
    shell = (FRONTEND / "ui_shell.js").read_text(encoding="utf-8")
    for tool in ("overview", "opportunity", "readiness", "events", "pressure", "insider", "news", "reports", "dividend", "short", "evidence"):
        assert f"'{tool}'" in shell
    assert "REMOVED_STOCK_TOOLS=new Set(['backtest','paper'])" in shell
    assert "href=\"/development\"" not in shell
    assert "href=\"/paper\"" not in shell


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


def test_market_command_center_contract():
    page = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
    assert 'Markedsrangering' in page
    assert 'Alle</button>' in page and 'Early</button>' in page and 'Opportunity</button>' in page
    assert 'Nye/IPO</button>' in page and 'Eier/Insider</button>' in page
    assert 'Rel. styrke' in page and 'Volum' in page and 'Trend' in page
    assert '/api/early-discovery?limit=100' in page
    assert '/api/opportunity/' in page
    assert '/api/ipo-radar?limit=50' in page
    assert 'rangering er analysegrunnlag, ikke kjøpssignal' in page
    for retired in ('Min oversikt','Min beholdning','Porteføljeverdi','Administrer beholdning'):
        assert retired not in page

def test_stock_decision_chain_contract():
    page = (ROOT / 'frontend' / 'stock.html').read_text(encoding='utf-8')
    for label in ('Aksjer Score','Markedsrangering','Opportunity','Early Discovery','Hvorfor følge denne?','Hva skjer nå?'):
        assert label in page
    assert '/api/opportunity/' in page
    assert 'Ingen handling ennå' in page
    assert 'UI legger ikke til nye signalregler' in page
    assert 'Viser bare forhold som finnes i lastede systemdata' in page
    assert 'Ikke verifisert' in page
