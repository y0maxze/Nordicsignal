"""Harden legacy insider numeric parsing without rewriting the base parser.

Euronext disclosure prose can place multiple numbers close together. The legacy
price/share regexes allowed arbitrary spaces inside captured tokens and could therefore
concatenate separate values. These guards constrain both price and share counts to one
localized numeric token while leaving the established parsing pipeline intact.
"""
from __future__ import annotations

import re

import insider_runtime

_PRICE_TOKEN = r"([0-9]{1,3}(?:[ \u00a0][0-9]{3})*(?:[.,][0-9]{1,4})?|[0-9]{1,6}(?:[.,][0-9]{1,4})?)(?![0-9.,])"
_PRICE_PATTERNS = (
    rf"\b(?:at|for)\s+(?:a\s+)?(?:price\s+(?:of\s+)?)?(?:NOK|SEK|DKK|EUR|USD)\s*{_PRICE_TOKEN}",
    rf"\b(?:price|kurs)\s*(?:of|på|til|:)?\s*(?:NOK|SEK|DKK|EUR|USD)?\s*{_PRICE_TOKEN}",
    rf"\btil\s+(?:en\s+)?kurs\s+(?:på\s+)?(?:NOK|SEK|DKK|EUR|USD)?\s*{_PRICE_TOKEN}",
)

# Share counts are integers. Accept normal grouping (37 500 / 37,500 / 2 000 000)
# or an ungrouped integer, but never an arbitrary sequence of nearby numbers.
_SHARE_TOKEN = r"(\d{1,3}(?:[ \u00a0,]\d{3})+|\d{1,12})(?![\d.,])"
_SAFE_SHARES = re.compile(
    rf"(?:purchased|purchase|bought|buy|acquired|sold|sell|disposed(?:\s+of)?|kjøpt|kjøpte|kjøp|solgt|solgte|salg|ervervet)"
    rf".{{0,180}}?{_SHARE_TOKEN}\s+(?:shares|aksjer)\b",
    re.I | re.S,
)


def guarded_price_of(body):
    text = body or ""
    for pattern in _PRICE_PATTERNS:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        value = insider_runtime._number(match.group(1))
        if value is not None and value > 0:
            return value
    return None


def install():
    if getattr(insider_runtime, "_numeric_parser_guard_v2", False):
        return
    insider_runtime._price_of = guarded_price_of
    insider_runtime.SHARES = _SAFE_SHARES
    insider_runtime._price_parser_guard_v1 = True
    insider_runtime._numeric_parser_guard_v2 = True


install()
