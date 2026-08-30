"""Harden legacy insider price parsing without rewriting the base parser.

Euronext disclosure prose can place another number immediately after a disclosed
price. The legacy regex allowed spaces inside the captured price token and could
therefore concatenate the transaction price with a following share count/holding.
That can inflate transaction values by orders of magnitude.
"""
from __future__ import annotations

import re

import insider_runtime

# A price is one localized numeric token, not an arbitrary run of numbers/spaces.
# Supports 26.65, 26,65, 1 234,50 and 1234 while stopping before a second number.
_PRICE_TOKEN = r"([0-9]{1,3}(?:[ \u00a0][0-9]{3})*(?:[.,][0-9]{1,4})?|[0-9]{1,6}(?:[.,][0-9]{1,4})?)"
_PATTERNS = (
    rf"\b(?:at|for)\s+(?:a\s+)?(?:price\s+(?:of\s+)?)?(?:NOK|SEK|DKK|EUR|USD)\s*{_PRICE_TOKEN}",
    rf"\b(?:price|kurs)\s*(?:of|på|til|:)?\s*(?:NOK|SEK|DKK|EUR|USD)?\s*{_PRICE_TOKEN}",
    rf"\btil\s+(?:en\s+)?kurs\s+(?:på\s+)?(?:NOK|SEK|DKK|EUR|USD)?\s*{_PRICE_TOKEN}",
)


def guarded_price_of(body):
    text = body or ""
    for pattern in _PATTERNS:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        value = insider_runtime._number(match.group(1))
        if value is not None and value > 0:
            return value
    return None


def install():
    if getattr(insider_runtime, "_price_parser_guard_v1", False):
        return
    insider_runtime._price_of = guarded_price_of
    insider_runtime._price_parser_guard_v1 = True


install()
