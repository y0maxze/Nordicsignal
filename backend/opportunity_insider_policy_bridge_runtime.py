"""Bridge Opportunity to the canonical qualified insider + Smart Money policy.

Historically Opportunity imported the base insider analyzer directly, which bypassed
later policy layers. This runtime replaces that function reference before Opportunity
is used so every live path applies the same NOK 100k/500k filtering and Smart Money
quality enrichment. It also exposes Smart Money metadata in Opportunity components
without changing the Opportunity score formula or the main 0-100 stock score.
"""
from __future__ import annotations

import opportunity_confluence_runtime as opportunity
import insider_purchase_threshold_runtime as purchase_policy
import insider_smart_money_runtime as smart_money

_BASE_CALCULATE = opportunity.calculate_opportunity


def analyze_insider_policy(payload, window_days=14):
    strict = purchase_policy.strict_analyze(payload, window_days=window_days)
    return smart_money.enrich(strict)


def calculate_opportunity_with_smart_money(reversal=None, insider=None):
    raw_insider = insider or {}
    signal = raw_insider.get("insider_signal_v2") if isinstance(raw_insider, dict) and "insider_signal_v2" in raw_insider else raw_insider
    signal = signal or {}
    result = _BASE_CALCULATE(reversal, signal)
    smart = signal.get("smart_money") or {}
    components = dict((result or {}).get("components") or {})
    components.update({
        "smart_money_quality": str(smart.get("quality") or "LOW"),
        "smart_money_points": int(smart.get("quality_points") or 0),
        "meaningful_actors_500k_plus": int(smart.get("meaningful_actors_500k_plus") or 0),
        "million_plus_actors": int(smart.get("million_plus_actors") or 0),
        "senior_actors": int(smart.get("senior_actors") or 0),
        "role_adjusted_qualified_value_nok": float(smart.get("role_adjusted_qualified_value_nok") or 0.0),
    })
    result = dict(result or {})
    result["components"] = components
    result["score_effect"] = 0
    return result


def install():
    if getattr(opportunity, "_canonical_insider_policy_bridge_runtime", False):
        return
    opportunity.analyze_insider = analyze_insider_policy
    opportunity.calculate_opportunity = calculate_opportunity_with_smart_money
    opportunity._canonical_insider_policy_bridge_runtime = True


install()
