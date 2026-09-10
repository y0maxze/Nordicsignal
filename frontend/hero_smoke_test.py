from pathlib import Path


def test_system_hero_brand_contract():
    src = (Path(__file__).parent / "ui_shell.js").read_text()
    assert "nsHero" in src
    assert "nsMark" in src
    assert "HIGH CONVICTION" in src
    assert "prefers-reduced-motion" in src
    assert "SYSTEM ONLINE" in src
    assert "view')==='signals'" in src


def test_blue_brand_asset_exists():
    svg = (Path(__file__).parent / "nordicsignal-brand.svg").read_text()
    assert "#19a7ff" in svg
    assert "NordicSignal" in svg
