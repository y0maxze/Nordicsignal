from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def read(name: str) -> str:
    return (FRONTEND / name).read_text(encoding="utf-8")


def test_theme_mode_loads_contrast_layer_and_tracks_system_theme():
    js = read("theme_mode.js")
    assert "/theme_light_fix.css" in js
    assert "prefers-color-scheme: light" in js
    assert "addEventListener('change',syncSystemTheme)" in js
    assert "localStorage.getItem(STORAGE_KEY)" in js


def test_light_theme_keeps_blue_identity_with_readable_surfaces():
    css = read("theme_light_fix.css")
    assert 'html[data-theme="light"]' in css
    assert "--accent:#126fda" in css
    assert "--t:#0b1930" in css
    assert "--surface:#ffffff" in css
    assert 'html[data-theme="light"] .top h1' in css
    assert 'html[data-theme="light"] .card' in css
    assert 'html[data-theme="light"] .btn' in css
    assert 'html[data-theme="light"] input' in css
    assert "prefers-reduced-motion:reduce" in css


def test_insider_uses_shared_theme_shell_and_mobile_contract():
    html = read("insider.html")
    for asset in ("/theme.css", "/theme_mode.js", "/ui_shell.js", "/mobile_nav.js"):
        assert asset in html
    assert "viewport-fit=cover" in html
    assert "min-height:44px" in html
    assert 'aria-live="polite"' in html
    assert 'id="nsMobileNav"' in html


def test_404_uses_shared_theme_and_accessible_touch_targets():
    html = read("404.html")
    assert "/theme.css" in html
    assert "/theme_mode.js" in html
    assert "viewport-fit=cover" in html
    assert "min-height:44px" in html
    assert "data-ns-theme-toggle" in html
    assert "--bg:#070707" not in html


def test_service_worker_caches_contrast_layer_without_cache_contract_bump():
    sw = read("sw.js")
    assert "const CACHE_NAME='nordicsignal-shell-v5'" in sw
    assert "'/theme_light_fix.css'" in sw
