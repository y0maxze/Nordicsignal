"""Fail-closed issuer identity resolution against the canonical stock registry.

Exact normalized names only. No fuzzy matching, aliases, or inferred tickers.
"""
from __future__ import annotations
import re
from database import connect

_SUFFIX = re.compile(r"\b(asa|as|plc|ltd|limited|nv|n\.v\.)\b", re.I)
_PUNCT = re.compile(r"[^a-z0-9æøå]+", re.I)


def normalize_issuer_name(value):
    text = _PUNCT.sub(" ", str(value or "").strip().lower())
    text = _SUFFIX.sub(" ", text)
    return " ".join(text.split())


def canonical_issuers():
    conn = connect()
    try:
        rows = conn.execute("SELECT ticker,name FROM stocks WHERE active=1 ORDER BY ticker").fetchall()
    finally:
        conn.close()
    return [(str(row["ticker"]).upper(), str(row["name"]).strip()) for row in rows]


def resolve_exact_name(name):
    needle = normalize_issuer_name(name)
    if not needle:
        return None
    matches = [(ticker, canonical) for ticker, canonical in canonical_issuers()
               if normalize_issuer_name(canonical) == needle]
    if len(matches) != 1:
        return None
    ticker, canonical = matches[0]
    return {"ticker": ticker, "name": canonical, "method": "canonical_exact_name", "verified": True}
