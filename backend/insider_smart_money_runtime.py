"""Role- and size-aware smart-money quality for qualified insider purchases.

This layer enriches insider_signal_v2 after the hard NOK 100k/500k purchase filter.
It does not change the main 0-100 stock score. Repeated purchases by one actor do not
create independent-buyer credit; distinct qualified actors remain the cluster unit.
"""
from __future__ import annotations

import re
from providers import NordicRegulatoryProvider
import insider_signal_v2_runtime as base
import insider_purchase_threshold_runtime as threshold

POLICY_VERSION = "2026-08-31-smart-money-v1"
EXECUTIVE_ROLES = ("ceo", "chief executive", "cfo", "chief financial")
CHAIR_ROLES = ("chair", "chairman", "chairwoman", "chairperson", "styreleder")
BOARD_ROLES = ("board member", "member of the board", "styremedlem", "director")


def _role_text(row):
    return " ".join(str(row.get(k) or "") for k in ("role", "position", "title", "summary")).lower()


def _role_class(row):
    text = _role_text(row)
    if any(x in text for x in EXECUTIVE_ROLES): return "CEO_CFO"
    if any(x in text for x in CHAIR_ROLES): return "CHAIR"
    if any(x in text for x in BOARD_ROLES): return "BOARD"
    return "OTHER"


def _role_multiplier(role):
    return {"CEO_CFO": 1.35, "CHAIR": 1.20, "BOARD": 1.10}.get(role, 1.0)


def _size_tier(value):
    value = float(value or 0.0)
    if value >= 1_000_000: return "VERY_LARGE"
    if value >= threshold.MEANINGFUL_BUY_NOK: return "MEANINGFUL"
    if value >= threshold.MIN_SIGNAL_BUY_NOK: return "QUALIFIED"
    return "SMALL"


def enrich(result):
    out = dict(result or {})
    signal = dict(out.get("insider_signal_v2") or {})
    items = base.prepare_items(out.get("items") or [])
    seen = set()
    qualified = []
    for row in items:
        if base._action(row) != "buy" or base._is_transfer(row):
            continue
        day = base._date(row.get("trade_date") or row.get("date") or row.get("published_at"))
        key = base._transaction_key(row, "buy", day)
        if key in seen:
            continue
        seen.add(key)
        value = base._trade_value(row)
        if value is None or value < threshold.MIN_SIGNAL_BUY_NOK:
            continue
        actor = base._actor_key(row)
        qualified.append((row, actor, float(value)))

    actor_totals = {}
    actor_roles = {}
    actor_trade_counts = {}
    for row, actor, value in qualified:
        if not actor:
            continue
        actor_totals[actor] = actor_totals.get(actor, 0.0) + value
        actor_trade_counts[actor] = actor_trade_counts.get(actor, 0) + 1
        role = _role_class(row)
        if _role_multiplier(role) > _role_multiplier(actor_roles.get(actor, "OTHER")):
            actor_roles[actor] = role
        else:
            actor_roles.setdefault(actor, role)

    independent = len(actor_totals)
    meaningful_actors = [a for a, v in actor_totals.items() if v >= threshold.MEANINGFUL_BUY_NOK]
    million_actors = [a for a, v in actor_totals.items() if v >= 1_000_000]
    senior_actors = [a for a, role in actor_roles.items() if role in {"CEO_CFO", "CHAIR"}]
    repeated_same_actor = sum(max(0, n - 1) for n in actor_trade_counts.values())
    role_adjusted_value = sum(actor_totals[a] * _role_multiplier(actor_roles.get(a, "OTHER")) for a in actor_totals)

    quality_points = 0
    reasons = []
    if meaningful_actors:
        quality_points += 2
        reasons.append(f"{len(meaningful_actors)} independent insider actor(s) accumulated >= NOK 500k")
    if million_actors:
        quality_points += 1
        reasons.append(f"{len(million_actors)} independent insider actor(s) accumulated >= NOK 1m")
    if senior_actors:
        quality_points += 1
        reasons.append("CEO/CFO/chair participation increases smart-money quality")
    if independent >= 3 and len(meaningful_actors) >= 2:
        quality_points += 2
        reasons.append("multi-actor cluster with at least two meaningful buyers")
    elif independent >= 2 and meaningful_actors:
        quality_points += 1
        reasons.append("multiple independent buyers with meaningful capital")

    quality = "HIGH" if quality_points >= 5 else "MEDIUM" if quality_points >= 3 else "LOW"
    signal["smart_money"] = {
        "quality": quality,
        "quality_points": quality_points,
        "independent_qualified_actors": independent,
        "meaningful_actors_500k_plus": len(meaningful_actors),
        "million_plus_actors": len(million_actors),
        "senior_actors": len(senior_actors),
        "repeated_same_actor_trades": repeated_same_actor,
        "role_adjusted_qualified_value_nok": round(role_adjusted_value, 2),
        "actor_summaries": [
            {"actor": actor, "role_class": actor_roles.get(actor, "OTHER"), "qualified_value_nok": round(value, 2), "size_tier": _size_tier(value), "trade_count": actor_trade_counts.get(actor, 0)}
            for actor, value in sorted(actor_totals.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "reasons": reasons,
        "policy": "distinct_actor_cluster+role_quality+500k_meaningful+1m_very_large",
        "score_effect": 0,
    }
    signal["score_effect"] = 0
    out["insider_signal_v2"] = signal
    out["insider_smart_money_version"] = POLICY_VERSION
    return out


def install():
    if getattr(NordicRegulatoryProvider, "_insider_smart_money_runtime", False):
        return
    original = NordicRegulatoryProvider.insider
    def insider(self, ticker, company_name=""):
        return enrich(original(self, ticker, company_name))
    NordicRegulatoryProvider.insider = insider
    NordicRegulatoryProvider._insider_smart_money_runtime = True

install()
