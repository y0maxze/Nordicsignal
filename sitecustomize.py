"""Ensure NordicSignal runtime patches load regardless of Render working directory."""

import os
import sys

# Render may start Uvicorn from the repository root while the application
# imports backend modules as top-level modules. Put backend on sys.path so
# the existing backend/sitecustomize patch can import the same providers.py
# module that main.py uses.
_ROOT = os.path.dirname(__file__)
_BACKEND = os.path.join(_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

try:
    import sitecustomize as _backend_sitecustomize  # noqa: F401
except Exception:
    # Keep application startup unaffected if the optional patch cannot load.
    pass
