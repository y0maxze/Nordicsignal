"""Conservative quality helpers for Capital Flow.

This module ranks evidence for presentation/research only. It MUST NOT alter the
NordicSignal score, Opportunity, High Conviction, alert thresholds or sizing.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^a-z0-9æøå]+", re.I)

EVENT_WEIGHT = {
    "PRIMARY_INSIDER": 5,
    "LARGE_HOLDING": 4,
    "OWNERSHIP_CHANGE": 3,
    "INSTITUTIONAL_FLOW": 3,
    "FOREIGN_OWNERSHIP": 2,
    "BLOCK_TRADE": 2,
}


def _norm(value):
    text = _WS.sub(" ", str(value or "").strip().lower())
    return _PUNCT.sub(" ", text).strip()


def quality_score(event):
    """Return a transparent 0-100 research-quality score."""
    score = 0
    if event.get("official"):
        score += 35
    if str(event.get("evidence_level") or "").lower() == "verified":
        score += 25
    if str(event.get("ticker") or "").strip():
        score += 15
    if event.get("source_url"):
        score += 5
    if event.get("actor"):
        score += 5
    if event.get("value_nok") is not None or event.get("shares") is not None:
        score += 5
    score += EVENT_WEIGHT.get(str(event.get("event_type") or "").upper(), 0) * 2
    return min(100, score)


def quality_band(event):
    score = quality_score(event)
    if score >= 85:
        return "HIGH"
    if score >= 65:
        return "MEDIUM"
    return "CONTEXT"


def dedupe_key(event):
    """Stable semantic key to collapse repeated representations of one event."""
    ticker = _norm(event.get("ticker"))
    kind = _norm(event.get("event_type"))
    actor = _norm(event.get("actor"))
    direction = _norm(event.get("direction"))
    title = _norm(event.get("title"))
    raw_date = str(event.get("event_at") or "")[:10]
    return "|".join((ticker, kind, actor, direction, raw_date, title))


def presentation_rank(event):
    """Higher is better; deterministic and independent of NordicSignal score."""
    try:
        dt = datetime.fromisoformat(str(event.get("event_at") or "").replace("Z", "+00:00"))
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        ts = dt.timestamp()
    except (TypeError, ValueError):
        ts = 0
    return quality_score(event), ts


def enrich(event):
    item = dict(event)
    item["research_quality"] = quality_score(item)
    item["quality_band"] = quality_band(item)
    return item
