"""Ensure NordicSignal runtime patches load regardless of Render working directory."""

import importlib.util
import logging
import os
import sys

log = logging.getLogger("nordicsignal.bootstrap")
_ROOT = os.path.dirname(__file__)
_BACKEND = os.path.join(_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

_PATCH = os.path.join(_BACKEND, "sitecustomize.py")
try:
    spec = importlib.util.spec_from_file_location("nordicsignal_backend_sitecustomize", _PATCH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load runtime bootstrap: {_PATCH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
except Exception:
    # Keep startup alive, but leave a useful trace in environments that import
    # the repository-level bootstrap instead of running with backend/ as cwd.
    log.exception("NordicSignal backend runtime bootstrap failed")
