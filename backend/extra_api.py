"""Compatibility shim for the retired Paper Trading feature.

Paper Trading and the old user-facing historical backtest have been removed from
NordicSignal. ``main`` and additive stock-intelligence runtimes still use the shared
Yahoo provider symbol that historically lived in this module, so that compatibility
export remains while install intentionally registers no Paper/Backtest routes.
"""

from providers import YahooProvider


def install(app):
    """Keep startup compatibility without exposing retired product endpoints."""
    return app
