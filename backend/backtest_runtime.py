"""Backtest runtime compatibility layer.

The canonical production implementation lives in ``extra_api._backtest``.
This module is imported by ``sitecustomize`` for historical compatibility, but
it deliberately does not replace the canonical implementation with an older
helper that lacks strategies, costs, and benchmark support.
"""


def install():
    """Leave the canonical extra_api backtest implementation untouched."""
    return None
