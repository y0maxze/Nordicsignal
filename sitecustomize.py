"""Ensure NordicSignal runtime patches load regardless of Render working directory."""

import importlib.util
import os
import sys

_ROOT = os.path.dirname(__file__)
_BACKEND = os.path.join(_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

_PATCH = os.path.join(_BACKEND, "sitecustomize.py")
try:
    spec = importlib.util.spec_from_file_location("nordicsignal_backend_sitecustomize", _PATCH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
except Exception:
    # Keep application startup unaffected if the optional patch cannot load.
    pass
