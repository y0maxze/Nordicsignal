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
