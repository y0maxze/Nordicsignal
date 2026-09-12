from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_brand_config_is_single_runtime_source_for_shell_branding():
    brand = read(FRONTEND / "brand_config.js")
    shell = read(FRONTEND / "ui_shell.js")
    worker = read(ROOT / "worker.js")

    assert "NORDICSIGNAL_BRAND" in brand
    assert "name:'NordicSignal'" in brand
    assert "label:'NORDICSIGNAL'" in brand
    assert "mark:'/nordicsignal-brand.svg'" in brand
    assert "window.NORDICSIGNAL_BRAND" in shell
    assert "BRAND.label" in shell
    assert "BRAND.name" in shell
    assert 'import "./frontend/brand_config.js"' in worker
    assert "globalThis.NORDICSIGNAL_BRAND" in worker
    assert "BRAND.label" in worker
    assert "BRAND.name" in worker
    assert "BRAND.mark" in worker


def test_worker_bootstraps_theme_shell_and_mobile_nav_for_legacy_routes():
    worker = read(ROOT / "worker.js")
    assert '["/holdings", "/holdings.html"]' in worker
    assert 'ensureSharedScript(html, "/theme_mode.js")' in worker
    assert 'ensureSharedScript(html, "/ui_shell.js")' in worker
    assert 'ensureSharedScript(html, "/mobile_nav.js")' in worker
    assert 'src="/brand_config.js"' in worker


def test_worker_keeps_refresh_auth_forwarding_intact():
    worker = read(ROOT / "worker.js")
    assert "env.NORDICSIGNAL_WRITE_TOKEN" in worker
    assert 'headers.set("x-nordicsignal-internal-token", env.NORDICSIGNAL_WRITE_TOKEN)' in worker
    assert 'if (url.pathname.startsWith("/api/")) return proxyApi(request, url, env);' in worker


def test_pwa_caches_brand_config_without_bumping_cache_contract():
    sw = read(FRONTEND / "sw.js")
    assert "const CACHE_NAME='nordicsignal-shell-v5'" in sw
    assert "'/brand_config.js'" in sw


def test_holdings_legacy_source_is_served_through_worker_theme_bootstrap():
    holdings = read(FRONTEND / "holdings.html")
    worker = read(ROOT / "worker.js")
    assert 'href="/theme.css"' in holdings
    assert '["/holdings", "/holdings.html"]' in worker
    assert 'ensureSharedScript(html, "/theme_mode.js")' in worker
