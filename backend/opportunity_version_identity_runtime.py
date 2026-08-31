"""Extend Opportunity model identity with event/discovery/insider semantics."""
import insider_purchase_threshold_runtime as purchase_policy
import insider_smart_money_runtime as smart_money
import opportunity_data_coverage_runtime as coverage
import opportunity_insider_policy_bridge_runtime as insider_bridge
import opportunity_temporal_independence_runtime as temporal
import opportunity_versioned_learning_runtime as versioned

_BASE_IDENTITY = versioned._current_identity


def _current_identity():
    base = dict(_BASE_IDENTITY())
    signal_fingerprint = versioned._fingerprint([
        base.get("signal_fingerprint"),
        versioned._source_text(coverage._record_first_observed),
        versioned._source_text(purchase_policy.strict_analyze),
        purchase_policy.MIN_SIGNAL_BUY_NOK,
        purchase_policy.MEANINGFUL_BUY_NOK,
        purchase_policy.STRONG_TOTAL_BUY_NOK,
        purchase_policy.POLICY_VERSION,
        versioned._source_text(smart_money.enrich),
        smart_money.POLICY_VERSION,
        versioned._source_text(insider_bridge.analyze_insider_policy),
        versioned._source_text(insider_bridge.calculate_opportunity_with_smart_money),
    ])
    policy_fingerprint = versioned._fingerprint([
        base.get("learning_policy_fingerprint"),
        versioned._source_text(coverage._market_quality),
        versioned._source_text(coverage._rotating_discovery_slice),
        coverage.DISCOVERY_DAYS,
        coverage.MAX_DISCOVERY_CANDIDATES,
        coverage.DISCOVERY_PER_SCAN,
        coverage.MIN_HISTORY_BARS,
        coverage.MIN_MEDIAN_DAILY_TURNOVER_NOK,
        coverage.MAX_LAST_TRADE_AGE_DAYS,
        coverage.MIN_NAME_MATCH,
        versioned._source_text(temporal._temporal_stats),
        temporal.MIN_UNIQUE_EVENT_DAYS,
        temporal.MIN_CALENDAR_SPAN_DAYS,
        temporal.MAX_SINGLE_DAY_SHARE_PCT,
        temporal.CLUSTER_WINDOW_DAYS,
        temporal.MAX_CLUSTER_WINDOW_SHARE_PCT,
        temporal.POLICY_VERSION,
    ])
    base["signal_fingerprint"] = signal_fingerprint
    base["signal_model_id"] = f"{base['signal_version']}:{signal_fingerprint}"
    base["learning_policy_fingerprint"] = policy_fingerprint
    base["learning_policy_id"] = f"{base['learning_policy_version']}:{policy_fingerprint}"
    base["identity_scope"] = "signal_rules+meaningful_insider_buys+smart_money_role_quality+canonical_insider_routing+first_observed_semantics+discovery_policy+temporal_independence_policy"
    return base


def install():
    versioned._current_identity = _current_identity


install()
