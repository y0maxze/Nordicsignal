from pathlib import Path

ROOT = Path(__file__).parent


def test_image_first_homepage_contract():
    html = (ROOT / "home.html").read_text()
    css = (ROOT / "home.css").read_text()
    artwork = ROOT / "nordicsignal-intro.jpg"
    assert artwork.stat().st_size > 10_000
    assert artwork.read_bytes()[:2] == b"\xff\xd8"
    for token in (
        "/nordicsignal-intro.jpg",
        "NS-RISK-2026-08-27-2",
        "nordicsignal_policy_session_acceptance",
        "nordicsignal_policy_acceptance",
        "riskAccept",
        "Godta og åpne NordicSignal",
        "location.assign('/app')",
    ):
        assert token in html
    assert "/home.js" not in html
    assert ".introArt" in css
    assert ".riskGate" in css
    assert "prefers-reduced-motion" in css


def test_blue_brand_asset_exists():
    svg = (ROOT / "nordicsignal-brand.svg").read_text()
    assert "#19a7ff" in svg
    assert "NordicSignal" in svg


def test_dashboard_does_not_duplicate_landing_hero():
    src = (ROOT / "ui_shell.js").read_text()
    assert "installHero" not in src
    assert "NORDICSIGNAL" in src
