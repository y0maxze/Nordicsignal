"""Load optional NordicSignal runtime integrations without blocking API startup."""

import importlib
import logging

log = logging.getLogger("nordicsignal.runtime")

RUNTIME_MODULES = (
    "provider_resilience_runtime",
    "insider_runtime",
    "insider_enrichment_runtime",
    "regulatory_limits_runtime",
    "backtest_runtime",
    "stock_intelligence_runtime",
    "short_alert_runtime",
    "paper_history_runtime",
    "news_routes",
    "news_cache_limits_runtime",
    "issuer_reports_runtime",
    "general_news_runtime",
    "holdings_routes",
    "holdings_tax_runtime",
    "portfolio_instruments_runtime",
    "holdings_integrity_runtime",
    "holding_purchase_lots_runtime",
    "portfolio_benchmark_runtime",
    "portfolio_events_runtime",
    "instrument_search_runtime",
    "global_search_runtime",
    "instrument_detail_runtime",
    "instrument_analytics_runtime",
    "instrument_signal_runtime",
    "signal_events_runtime",
    "fund_news_runtime",
    "generic_paper_runtime",
    "http_cache_runtime",
)


def _install(module_name):
    try:
        module = importlib.import_module(module_name)
        install = getattr(module, "install", None)
        if callable(install):
            install()
    except Exception:
        # Optional integrations must not stop the core FastAPI service, but the
        # failure must be visible in Render logs so production gaps are debuggable.
        log.exception("Optional runtime module failed: %s", module_name)


for _module_name in RUNTIME_MODULES:
    _install(_module_name)
