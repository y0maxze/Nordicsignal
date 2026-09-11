"""Capital Flow integrity guard for unlinked events.

Verified official disclosures may be useful research context before NordicSignal can
resolve them to a tracked issuer. They must never become actionable Web Push events
until an explicit ticker link exists. This module preserves those rows, suppresses
alert eligibility, and keeps the rule enforced after every Capital Flow scan.
"""
from __future__ import annotations

import extra_api
from database import connect
import capital_flow_runtime as capital_flow


def suppress_unlinked_alerts():
    """Disable alert eligibility for Capital Flow rows without an issuer ticker."""
    conn = connect()
    try:
        cursor = conn.execute(
            "UPDATE capital_flow_events SET alert_eligible=0 "
            "WHERE alert_eligible=1 AND (ticker IS NULL OR TRIM(ticker)='')"
        )
        changed = max(0, int(getattr(cursor, "rowcount", 0) or 0))
        conn.commit()
        return changed
    finally:
        conn.close()


def install():
    if getattr(extra_api, "_capital_flow_integrity_runtime_v1", False):
        return

    original_scan_once = capital_flow.scan_once

    def scan_once_with_integrity():
        result = original_scan_once()
        if not isinstance(result, dict) or result.get("status") == "busy":
            return result
        result = dict(result)
        result["unlinked_alerts_suppressed"] = suppress_unlinked_alerts()
        return result

    capital_flow.scan_once = scan_once_with_integrity
    suppress_unlinked_alerts()
    extra_api._capital_flow_integrity_runtime_v1 = True


install()
