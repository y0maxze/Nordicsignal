"""Ensure NordicSignal runtime patches load regardless of Render working directory."""

try:
    from backend import sitecustomize as _backend_sitecustomize  # noqa: F401
except Exception:
    # Keep application startup unaffected if the optional patch cannot load.
    pass
