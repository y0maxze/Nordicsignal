"""Runtime loader for NordicSignal insider integration."""
try:
    from insider_runtime import install
    install()
except Exception:
    # The API must still start if an optional market-data patch is unavailable.
    pass
