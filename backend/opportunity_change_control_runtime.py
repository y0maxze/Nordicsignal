"""Read-only change-control guard for live Opportunity policy.

This module intentionally does not wrap or modify calculate_opportunity(). It audits
its source contract so future production-threshold changes must be explicit in code
review while research remains unable to promote itself into live behavior.
"""
from __future__ import annotations

import hashlib
import inspect

import extra_api
import opportunity_confluence_runtime as opportunity
import opportunity_counterfactual_sandbox_runtime as sandbox

VERSION = "opportunity-change-control-v1"

REQUIRED_SOURCE_CONTRACT = (
    "reversal_score >= 75",
    "reversal_score >= 70",
    "reversal_score >= 55",
    "volume_ratio >= 2.0",
    "volume_ratio >= 1.5",
    'insider_label == "STRONG"',
    'insider_label == "POSITIVE"',
    "independent_buyers >= 3",
    "buy_value >= 1_000_000",
    "evidence_count == 3 and score >= 80",
    "strong_reversal and volume_confirmed and score >= 60",
    "reversal_score >= 70 and (volume_confirmed or insider_positive)",
    '"score_effect": 0',
)


def _source():
    return inspect.getsource(opportunity.calculate_opportunity)


def _source_sha256(source):
    return hashlib.sha256(str(source).encode("utf-8")).hexdigest()


def _source_invariants(source):
    source = str(source or "")
    checks = {token: token in source for token in REQUIRED_SOURCE_CONTRACT}
    return checks


def change_control_status():
    source = _source()
    checks = _source_invariants(source)
    live_contract_ok = all(checks.values())
    sandbox_contract_ok = bool(
        getattr(sandbox, "CANDIDATES", None)
        and getattr(sandbox, "HOLDOUT_SHARE", None) is not None
    )
    return {
        "status": "PASS" if live_contract_ok and sandbox_contract_ok else "REVIEW",
        "version": VERSION,
        "live_policy_source_sha256": _source_sha256(source),
        "live_policy_contract_ok": live_contract_ok,
        "live_policy_checks": checks,
        "research_sandbox_contract_ok": sandbox_contract_ok,
        "promotion_policy": "manual_source_change_via_reviewed_pr_only",
        "research_can_modify_live_policy": False,
        "automatic_threshold_changes": False,
        "main_score_effect": 0,
        "meaning": (
            "Live Opportunity policy matches the reviewed source contract; research has no automatic promotion path."
            if live_contract_ok and sandbox_contract_ok else
            "Live Opportunity policy or research isolation changed; review the change-control contract before release."
        ),
    }


def install():
    if getattr(extra_api, "_opportunity_change_control_runtime", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)

        @app.get("/api/opportunity-shadow/change-control")
        def opportunity_change_control_route():
            return change_control_status()

    extra_api.install = patched_install
    extra_api._opportunity_change_control_runtime = True


install()
