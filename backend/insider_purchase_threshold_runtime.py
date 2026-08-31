"""Meaningful-purchase policy layered on verified insider data.

Raw regulatory rows remain available for audit, but small buy transactions do not
contribute to insider-signal strength. This changes signal evidence only; the main
0-100 stock score remains untouched by insider_signal_v2.score_effect=0.
"""
from __future__ import annotations

from datetime import datetime, timezone

from providers import NordicRegulatoryProvider
import insider_signal_v2_runtime as base

MIN_SIGNAL_BUY_NOK = 100_000.0
MEANINGFUL_BUY_NOK = 500_000.0
STRONG_TOTAL_BUY_NOK = 1_000_000.0
POLICY_VERSION = "2026-08-31-meaningful-buys-v1"


def strict_analyze(result, window_days=14):
    out = dict(result or {})
    items = base.prepare_items(out.get("items") or [])
    buys, sells, excluded, small_buys = [], [], [], []
    seen_transactions = set()
    duplicate_count = 0
    dates = [base._date(x.get("trade_date") or x.get("date") or x.get("published_at")) for x in items]
    dates = [x for x in dates if x]
    anchor = max(dates) if dates else datetime.now(timezone.utc).date()

    for row in items:
        action = base._action(row)
        day = base._date(row.get("trade_date") or row.get("date") or row.get("published_at"))
        if day and (anchor - day).days > window_days:
            continue
        if base._is_transfer(row):
            excluded.append(row)
            continue
        if action not in {"buy", "sell"}:
            continue
        key = base._transaction_key(row, action, day)
        if key in seen_transactions:
            duplicate_count += 1
            continue
        seen_transactions.add(key)
        if action == "buy":
            value = base._trade_value(row)
            if value is None or value < MIN_SIGNAL_BUY_NOK:
                small_buys.append(row)
                continue
            buys.append(row)
        else:
            sells.append(row)

    actors = {x for x in (base._actor_key(row) for row in buys) if x}
    buy_values = [base._trade_value(row) for row in buys]
    buy_values = [float(v) for v in buy_values if v is not None]
    buy_value = sum(buy_values)
    meaningful_buys = [v for v in buy_values if v >= MEANINGFUL_BUY_NOK]
    sell_value = sum(v for v in (base._trade_value(row) for row in sells) if v is not None)
    weighted_buy_value = sum((base._trade_value(row) or 0.0) * base._role_weight(row) for row in buys)

    points = 0
    reasons = []
    if len(actors) >= 3:
        points += 3
        reasons.append(f"{len(actors)} independent qualified insider buyers within {window_days} days")
    elif len(actors) == 2:
        points += 2
        reasons.append(f"2 independent qualified insider buyers within {window_days} days")
    elif len(actors) == 1:
        points += 1
        reasons.append("1 qualified insider buyer")

    if buy_value >= STRONG_TOTAL_BUY_NOK:
        points += 2
        reasons.append("qualified buy value >= NOK 1m")
    elif meaningful_buys:
        points += 1
        reasons.append("at least one meaningful insider purchase >= NOK 500k")

    if weighted_buy_value > buy_value * 1.10 and buy_value > 0:
        points += 1
        reasons.append("senior-management purchases increase signal quality")
    if sells and sell_value > buy_value:
        points -= 2
        reasons.append("sell value exceeds qualified buy value")

    label = "STRONG" if points >= 5 else "POSITIVE" if points >= 3 else "MIXED" if buys or sells else "NONE"
    out["insider_signal_v2"] = {
        "label": label,
        "points": points,
        "window_days": window_days,
        "independent_buyers": len(actors),
        "buy_count": len(buys),
        "sell_count": len(sells),
        "buy_value_nok": round(buy_value, 2),
        "sell_value_nok": round(sell_value, 2),
        "meaningful_buy_count": len(meaningful_buys),
        "minimum_signal_buy_nok": MIN_SIGNAL_BUY_NOK,
        "meaningful_buy_threshold_nok": MEANINGFUL_BUY_NOK,
        "ignored_small_buy_count": len(small_buys),
        "ignored_small_buy_value_nok": round(sum((base._trade_value(row) or 0.0) for row in small_buys), 2),
        "excluded_transfer_like_count": len(excluded),
        "deduplicated_row_count": duplicate_count,
        "prepared_item_count": len(items),
        "reasons": reasons,
        "score_effect": 0,
        "policy": "qualified_buys_min_100k_meaningful_500k_no_main_score_effect",
    }
    out["insider_signal_v2_version"] = POLICY_VERSION
    return out


def install():
    if getattr(NordicRegulatoryProvider, "_meaningful_purchase_threshold_runtime", False):
        return
    original = NordicRegulatoryProvider.insider

    def insider(self, ticker, company_name=""):
        return strict_analyze(original(self, ticker, company_name))

    NordicRegulatoryProvider.insider = insider
    NordicRegulatoryProvider._meaningful_purchase_threshold_runtime = True


install()
