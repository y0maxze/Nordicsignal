from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHELL = (ROOT / "frontend" / "ui_shell.js").read_text(encoding="utf-8")


def test_stock_tool_sort_only_mutates_dom_when_order_changes():
    assert "const needsReorder=desired.some" in SHELL
    assert "if(needsReorder)" in SHELL
    assert "tabs.appendChild(fragment)" in SHELL


def test_stock_tool_observer_does_not_unconditionally_append_every_tab():
    assert "TOOL_ORDER.forEach(key=>" not in SHELL
    assert "tabs.appendChild(btn)" not in SHELL
