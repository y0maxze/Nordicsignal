"""Read-only change-control guard for live Opportunity policy.

Audits the reviewed base Opportunity thresholds and the canonical insider-policy bridge
separately. Research cannot promote itself into live behavior and no automatic policy
mutation occurs here.
"""
from __future__ import annotations

import hashlib
import inspect

import extra_api
import opportunity_counterfactual_sandbox_runtime as sandbox
import opportunity_insider_policy_bridge_runtime as bridge

VERSION = "opportunity-change-control-v2-canonical-insider-bridge"

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

REQUIRED_BRIDGE_CONTRACT = (
    "purchase_policy.strict_analyze",
    "smart_money.enrich",
    '"smart_money_quality"',
    '"meaningful_actors_500k_plus"',
    '"score_effect"] = 0',
)


def _base_source():
    return inspect.getsource(bridge._BASE_CALCULATE)


def _bridge_source():
    return inspect.getsource(bridge.calculate_opportunity_with_smart_money) + "\n" + inspect.getsource(bridge.analyze_insider_policy)


def _source_sha256(source):
    return hashlib.sha256(str(source).encode("utf-8")).hexdigest()


def _source_invariants(source, contract):
    source = str(source or "")
    return {token: token in source for token in contract}


def change_control_status():
    base_source = _base_source()
    bridge_source = _bridge_source()
    checks = _source_invariants(base_source, REQUIRED_SOURCE_CONTRACT)
    bridge_checks = _source_invariants(bridge_source, REQUIRED_BRIDGE_CONTRACT)
    live_contract_ok = all(checks.values())
    bridge_contract_ok = all(bridge_checks.values())
    sandbox_contract_ok = bool(
        getattr(sandbox, "CANDIDATES", None)
        and getattr(sandbox, "HOLDOUT_SHARE", None) is not None
    )
    passed = live_contract_ok and bridge_contract_ok and sandbox_contract_ok
    return {
        "status": "PASS" if passed else "REVIEW",
        "version": VERSION,
        "live_policy_source_sha256": _source_sha256(base_source),
        "insider_bridge_source_sha256": _source_sha256(bridge_source),
        "live_policy_contract_ok": live_contract_ok,
        "live_policy_checks": checks,
        "canonical_insider_bridge_contract_ok": bridge_contract_ok,
        "canonical_insider_bridge_checks": bridge_checks,
        "research_sandbox_contract_ok": sandbox_contract_ok,
        "promotion_policy": "manual_source_change_via_reviewed_pr_only",
        "research_can_modify_live_policy": False,
        "automatic_threshold_changes": False,
        "main_score_effect": 0,
        "meaning": (
            "Base Opportunity thresholds, canonical insider bridge and research isolation match the reviewed contracts."
            if passed else
            "A live threshold, canonical insider bridge or research-isolation contract changed; review before release."
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
