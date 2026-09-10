"""Compatibility shim for the retired Paper Trading feature.

Paper Trading and the old user-facing historical backtest have been removed from
NordicSignal. ``main`` still imports this module during the migration so existing
startup wiring remains stable; install intentionally registers no routes.
"""


def install(app):
    """Keep startup compatibility without exposing retired product endpoints."""
    return app
