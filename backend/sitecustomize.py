"""Runtime loaders for NordicSignal integrations."""

try:
    from insider_runtime import install
    install()
except Exception:
    # The API must still start if an optional market-data patch is unavailable.
    pass

try:
    from insider_enrichment_runtime import install
    install()
except Exception:
    # Rich insider parsing is additive; keep core insider feed available if unavailable.
    pass

try:
    from backtest_runtime import install
    install()
except Exception:
    # Keep API startup independent of the optional backtest patch.
    pass

try:
    from stock_intelligence_runtime import install
    install()
except Exception:
    # Reports/dividends are additive; never block API startup if unavailable.
    pass

try:
    from short_alert_runtime import install
    install()
except Exception:
    # Short alerts and volume-pressure proxies are additive.
    pass

try:
    from paper_history_runtime import install
    install()
except Exception:
    # Paper journal endpoints are additive; keep core API available if unavailable.
    pass

try:
    from news_runtime import install
    install()
except Exception:
    # Multi-source news is additive; Yahoo/core endpoints must still start if unavailable.
    pass
