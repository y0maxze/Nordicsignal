from pathlib import Path
from unittest.mock import patch

import capital_flow_integrity_runtime as integrity

ROOT = Path(__file__).resolve().parents[1]


class _Cursor:
    rowcount = 2


class _Connection:
    def __init__(self):
        self.sql = []
        self.commits = 0
        self.closed = 0

    def execute(self, sql, params=()):
        self.sql.append((sql, params))
        return _Cursor()

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed += 1


def test_unlinked_capital_flow_alerts_are_suppressed_without_deleting_rows():
    conn = _Connection()
    with patch.object(integrity, "connect", return_value=conn):
        changed = integrity.suppress_unlinked_alerts()

    assert changed == 2
    assert conn.commits == 1
    assert conn.closed == 1
    sql = conn.sql[0][0]
    assert sql.startswith("UPDATE capital_flow_events SET alert_eligible=0")
    assert "ticker IS NULL OR TRIM(ticker)=''" in sql
    assert "DELETE" not in sql.upper()


def test_capital_flow_push_requires_ticker_even_when_alert_flag_is_set():
    bridge = (ROOT / "backend" / "capital_flow_push_bridge_runtime.py").read_text(encoding="utf-8")
    assert "alert_eligible=1 AND ticker IS NOT NULL AND TRIM(ticker)<>''" in bridge
    assert "if not ticker:" in bridge


def test_integrity_guard_loads_after_capital_flow_runtime_and_before_push_bridge():
    sitecustomize = (ROOT / "backend" / "sitecustomize.py").read_text(encoding="utf-8")
    radar = sitecustomize.index('"capital_flow_runtime"')
    integrity_guard = sitecustomize.index('"capital_flow_integrity_runtime"')
    push_bridge = sitecustomize.index('"capital_flow_push_bridge_runtime"')
    assert radar < integrity_guard < push_bridge
