"""Load optional NordicSignal runtime integrations without blocking API startup."""

import importlib
import logging

log = logging.getLogger("nordicsignal.runtime")

RUNTIME_MODULES = (
    "provider_resilience_runtime","insider_runtime","insider_parser_guard_runtime","insider_enrichment_runtime","regulatory_limits_runtime","insider_fresh_fallback_runtime","insider_position_runtime","insider_value_runtime","insider_signal_v2_runtime","insider_purchase_threshold_runtime","insider_smart_money_runtime","stock_intelligence_runtime","short_alert_runtime","paper_history_runtime","news_routes","news_cache_limits_runtime","issuer_reports_runtime","general_news_runtime","insider_market_runtime","insider_market_v2_runtime","insider_history_runtime","insider_detail_normalization_runtime","insider_company_cleanup_runtime","insider_detail_persistent_cache_runtime","market_calendar_runtime","holdings_routes","holdings_tax_runtime","portfolio_instruments_runtime","holdings_integrity_runtime","holding_purchase_lots_runtime","portfolio_benchmark_runtime","portfolio_events_runtime","portfolio_pulse_runtime","instrument_search_runtime","global_search_runtime","instrument_detail_runtime","instrument_analytics_runtime","instrument_signal_runtime","signal_events_runtime","signal_evidence_runtime","trend_reversal_runtime","opportunity_confluence_runtime","opportunity_insider_policy_bridge_runtime","opportunity_tracking_runtime","opportunity_performance_v2_runtime","opportunity_calibration_gate_runtime","opportunity_independence_gate_runtime","opportunity_data_coverage_runtime","opportunity_discovery_async_runtime","opportunity_market_regime_runtime","opportunity_versioned_learning_runtime","opportunity_temporal_independence_runtime","opportunity_version_identity_runtime","opportunity_statistical_gate_runtime","opportunity_walkforward_gate_runtime","opportunity_shadow_dataset_runtime","opportunity_shadow_smart_money_runtime","opportunity_shadow_quality_runtime","opportunity_counterfactual_sandbox_runtime","opportunity_change_control_runtime","opportunity_shadow_scan_audit_runtime","opportunity_shadow_repair_runtime","opportunity_autoscan_runtime","opportunity_learning_health_runtime","opportunity_shadow_health_runtime","opportunity_scan_failure_streak_runtime","fund_news_runtime","investment_readiness_runtime","generic_paper_runtime","push_runtime","alert_history_runtime","alert_local_record_runtime","data_quality_runtime","ops_readiness_runtime","refresh_access_runtime","security_runtime","system_health_runtime","persistent_feed_cache_runtime","performance_runtime","http_cache_runtime",
)


def _install(module_name):
    try:
        module = importlib.import_module(module_name)
        install = getattr(module, "install", None)
        if callable(install): install()
    except Exception:
        log.exception("Optional runtime module failed: %s", module_name)


for _module_name in RUNTIME_MODULES:
    _install(_module_name)
