"""Conservative Event Radar hardening.

Prevents substring false positives (for example ``order`` inside ``border``) and
keeps newest announcements first within the existing priority buckets. This layer
changes neither event priority definitions nor NordicSignal scores/thresholds.
"""
import re

import event_radar_runtime as radar
import news_runtime

_ORIGINAL_BUILD = radar.build_event_radar


def _term_present(text, term):
    normalized = news_runtime._norm(term)
    if not normalized:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(normalized) + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def _classify(item):
    text = news_runtime._norm(" ".join(str(item.get(k) or "") for k in ("title", "topic", "summary")))
    for kind, label, priority, terms in radar._RULES:
        if any(_term_present(text, term) for term in terms):
            return kind, label, priority
    return None


def _sort_items(items):
    rank = {"high": 0, "watch": 1, "normal": 2}
    ordered = list(items or [])
    # Stable two-pass sort: newest first within each canonical priority bucket.
    ordered.sort(key=lambda x: str(x.get("published_at") or ""), reverse=True)
    ordered.sort(key=lambda x: rank.get(x.get("priority"), 9))
    return ordered


def build_event_radar(limit=40, ticker=None, force=False, provider=None):
    requested = max(1, min(int(limit or 40), 100))
    result = _ORIGINAL_BUILD(limit=100, ticker=ticker, force=force, provider=provider)
    items = _sort_items(result.get("items") or [])
    result = dict(result)
    result["items"] = items[:requested]
    result["count"] = min(len(items), requested)
    return result


def install():
    if getattr(radar, "_event_radar_hardening_v1", False):
        return
    radar._classify = _classify
    radar.build_event_radar = build_event_radar
    radar._event_radar_hardening_v1 = True


install()
