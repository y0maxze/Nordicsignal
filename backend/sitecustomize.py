"""Runtime loaders for NordicSignal integrations."""

try:
    from insider_runtime import install
    install()
except Exception:
    # The API must still start if an optional market-data patch is unavailable.
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
    from paper_history_runtime import install
    install()
except Exception:
    # Paper journal endpoints are additive; keep core API available if unavailable.
    pass
