"""Extend Opportunity model identity with event/discovery semantics.

The signal calculation alone is not enough to define a forward-validation cohort:
how a qualifying state first becomes an event and which discovery instruments are
eligible also change the observed sample. This layer folds those semantics into the
runtime fingerprint used by opportunity_versioned_learning_runtime.
"""
import opportunity_data_coverage_runtime as coverage
import opportunity_versioned_learning_runtime as versioned

_BASE_IDENTITY = versioned._current_identity


def _current_identity():
    base = dict(_BASE_IDENTITY())
    signal_fingerprint = versioned._fingerprint([
        base.get("signal_fingerprint"),
        versioned._source_text(coverage._record_first_observed),
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
    ])
    base["signal_fingerprint"] = signal_fingerprint
    base["signal_model_id"] = f"{base['signal_version']}:{signal_fingerprint}"
    base["learning_policy_fingerprint"] = policy_fingerprint
    base["learning_policy_id"] = f"{base['learning_policy_version']}:{policy_fingerprint}"
    base["identity_scope"] = "signal_rules+first_observed_semantics+discovery_policy"
    return base


def install():
    versioned._current_identity = _current_identity


install()
