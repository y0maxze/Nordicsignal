from pathlib import Path

ROOT = Path(__file__).parent


def test_cinematic_homepage_contract():
    html = (ROOT / "home.html").read_text()
    css = (ROOT / "home.css").read_text()
    js = (ROOT / "home.js").read_text()
    for token in ("NORDICSIGNAL", "MARKET DATA", "FUNDAMENTALS", "INSIDER DATA", "EVENT RADAR", "HIGH CONVICTION", "IPO · PUSH · BRIEF"):
        assert token in html
    assert "prefers-reduced-motion" in css
    assert "IntersectionObserver" in js
    assert "/api/stocks" in js
    assert "/api/push/status" in js
    assert "/api/ipo-radar/autoscan/status" in js


def test_blue_brand_asset_exists():
    svg = (ROOT / "nordicsignal-brand.svg").read_text()
    assert "#19a7ff" in svg
    assert "NordicSignal" in svg


def test_dashboard_does_not_duplicate_landing_hero():
    src = (ROOT / "ui_shell.js").read_text()
    assert "installHero" not in src
    assert "NORDICSIGNAL" in src
