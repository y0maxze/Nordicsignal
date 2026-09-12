from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def test_history_page_uses_shared_product_shell():
    page = (FRONTEND / "history.html").read_text(encoding="utf-8")
    assert 'href="/theme.css"' in page
    assert 'src="/theme_mode.js"' in page
    assert 'src="/ui_shell.js"' in page
    assert 'src="/mobile_nav.js"' in page
    assert 'src="/history_nav_context.js"' in page
    assert 'viewport-fit=cover' in page
    assert 'Kurshistorikk' in page
    assert 'Price History' not in page


def test_history_page_preserves_backend_contract_and_url_state():
    page = (FRONTEND / "history.html").read_text(encoding="utf-8")
    assert '/api/history/${encodeURIComponent(ticker)}?period=${encodeURIComponent(period)}' in page
    assert "next.searchParams.set('ticker',ticker)" in page
    assert "next.searchParams.set('period',period)" in page
    assert "history.replaceState" in page
    for period in ("1m", "3m", "6m", "1y", "5y", "10y", "max"):
        assert f'data-period="{period}"' in page


def test_history_page_is_mobile_and_accessibility_ready():
    page = (FRONTEND / "history.html").read_text(encoding="utf-8")
    assert 'env(safe-area-inset-bottom)' not in page  # canonical mobile nav owns bottom safe area
    assert 'min-height:44px' in page
    assert 'aria-live="polite"' in page
    assert 'role="img"' in page
    assert 'aria-label="Velg periode"' in page
    assert '@media(prefers-reduced-motion:reduce)' in page


def test_history_mobile_nav_context_marks_more_route():
    context = (FRONTEND / "history_nav_context.js").read_text(encoding="utf-8")
    assert "location.pathname.startsWith('/history')" in context
    assert "nsMobileMoreToggle" in context
    assert 'a[href="/history"]' in context
    assert "Kurshistorikk" in context
    assert "aria-current','page'" in context


def test_history_surface_is_cached_and_worker_route_remains_wired():
    sw = (FRONTEND / "sw.js").read_text(encoding="utf-8")
    worker = (ROOT / "worker.js").read_text(encoding="utf-8")
    assert "'/history'" in sw
    assert "'/history_nav_context.js'" in sw
    assert '["/history", "/history.html"]' in worker
    assert '["/history/", "/history.html"]' in worker
