"""Explainable insider-signal layer for NordicSignal.

This layer deliberately does not change the 0-100 stock score yet. It enriches the
verified regulatory insider feed with a separate signal that can be backtested before
we allow it to influence BUY/WATCH/RISK.
"""
from datetime import datetime, timezone
import re
import unicodedata

from providers import NordicRegulatoryProvider


def _num(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _date(value):
    try:
        return datetime.fromisoformat(str(value)[:10]).date() if value else None
    except (TypeError, ValueError):
        return None


def _fold(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(ch for ch in text if not unicodedata.combining(ch)).lower().split())


def _actor_key(row):
    """Return a stable economic-actor key, not announcement-title noise."""
    value = (
        row.get("person")
        or row.get("related_primary_insider")
        or row.get("entity")
        or row.get("insider")
        or row.get("actor")
        or row.get("insider_name")
        or row.get("name")
    )
    text = " ".join(str(value or "").split()).strip(" ,.-–—")
    if not text:
        return ""

    # Remove generic Euronext/title prefixes that sometimes leak into actor fields.
    text = re.sub(r"^(?:primary\s+insider\s+transactions?|mandatory\s+notification(?:\s+of\s+trade)?|prim[aæ]rinsider(?:transaksjoner?|handel))\s*[:\-–—]*\s*", "", text, flags=re.I)

    # Remove repeated issuer prefix, while preserving a related company/person suffix.
    company = " ".join(str(row.get("company") or "").split()).strip(" ,.-–—")
    if company:
        pattern = re.compile(rf"^(?:{re.escape(company)}[\s:,.\-–—]*)+", re.I)
        text = pattern.sub("", text).strip(" ,.-–—") or text

    return _fold(text)


def _role_weight(row):
    text = " ".join(str(row.get(k) or "") for k in ("role", "position", "title", "summary")).lower()
    if "ceo" in text or "chief executive" in text:
        return 1.35
    if "cfo" in text or "chief financial" in text:
        return 1.25
    if "coo" in text or "chief operating" in text:
        return 1.15
    if "chair" in text or "styreleder" in text:
        return 1.15
    if "board" in text or "styremedlem" in text or "director" in text:
        return 1.05
    return 1.0


def _trade_value(row):
    for key in ("display_transaction_value", "transaction_value", "display_value", "value"):
        value = _num(row.get(key))
        if value is not None and value >= 0:
            return value
    shares, price = _num(row.get("shares")), _num(row.get("price"))
    return shares * price if shares is not None and price is not None and shares >= 0 and price >= 0 else None


def _is_transfer(row):
    text = " ".join(
        str(row.get(k) or "")
        for k in ("title", "summary", "description", "detail", "event", "transaction_type", "activity_type")
    ).lower()
    explicit = row.get("economic_exposure_unchanged") is True or row.get("internal_transfer") is True
    phrases = (
        "unchanged", "transfer", "transferred", "overføring", "redelivery", "borrowed shares",
        "same beneficial owner", "no change in economic exposure",
    )
    return explicit or any(p in text for p in phrases)


def _action(row):
    raw = str(
        row.get("transaction_type")
        or row.get("direction")
        or row.get("action")
        or row.get("activity_type")
        or ""
    ).strip().lower()
    if raw in {"buy", "purchase", "purchased", "acquisition", "acquire", "acquired"}:
        return "buy"
    if raw in {"sell", "sale", "sold", "disposal", "dispose", "disposed"}:
        return "sell"
    if any(word in raw for word in ("purchase", "acqui", "kjøp", "buy")):
        return "buy"
    if any(word in raw for word in ("sale", "sell", "sold", "dispos", "salg")):
        return "sell"
    return raw


def analyze(result, window_days=14):
    out = dict(result or {})
    items = [dict(x) for x in (out.get("items") or [])]
    buys = []
    sells = []
    excluded = []
    dates = [_date(x.get("trade_date") or x.get("date") or x.get("published_at")) for x in items]
    dates = [x for x in dates if x]
    anchor = max(dates) if dates else datetime.now(timezone.utc).date()

    for row in items:
        action = _action(row)
        day = _date(row.get("trade_date") or row.get("date") or row.get("published_at"))
        if day and (anchor - day).days > window_days:
            continue
        if _is_transfer(row):
            row["insider_signal_excluded"] = "economic exposure may be unchanged / transfer-like transaction"
            excluded.append(row)
            continue
        if action == "buy":
            buys.append(row)
        elif action == "sell":
            sells.append(row)

    actors = {x for x in (_actor_key(row) for row in buys) if x}
    buy_value = sum(v for v in (_trade_value(row) for row in buys) if v is not None)
    sell_value = sum(v for v in (_trade_value(row) for row in sells) if v is not None)
    weighted_buy_value = sum((_trade_value(row) or 0.0) * _role_weight(row) for row in buys)

    points = 0
    reasons = []
    if len(actors) >= 3:
        points += 3
        reasons.append(f"{len(actors)} independent insider buyers within {window_days} days")
    elif len(actors) == 2:
        points += 2
        reasons.append(f"2 independent insider buyers within {window_days} days")
    elif len(actors) == 1:
        points += 1
        reasons.append("1 insider buyer")
    if buy_value >= 1_000_000:
        points += 2
        reasons.append("disclosed/estimated buy value >= NOK 1m")
    elif buy_value >= 250_000:
        points += 1
        reasons.append("disclosed/estimated buy value >= NOK 250k")
    if weighted_buy_value > buy_value * 1.10 and buy_value > 0:
        points += 1
        reasons.append("senior-management purchases increase signal quality")
    if sells and sell_value > buy_value:
        points -= 2
        reasons.append("sell value exceeds buy value")

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
        "excluded_transfer_like_count": len(excluded),
        "reasons": reasons,
        "score_effect": 0,
        "policy": "informational_only_pending_backtest",
    }
    out["insider_signal_v2_version"] = "2026-08-30-v3"
    return out


def install():
    if getattr(NordicRegulatoryProvider, "_insider_signal_v2_runtime", False):
        return
    original = NordicRegulatoryProvider.insider

    def insider(self, ticker, company_name=""):
        return analyze(original(self, ticker, company_name))

    NordicRegulatoryProvider.insider = insider
    NordicRegulatoryProvider._insider_signal_v2_runtime = True


install()
