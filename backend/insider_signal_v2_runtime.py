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


def _clean_actor_text(value, company=""):
    text = " ".join(str(value or "").split()).strip(" ,.-–—")
    if not text:
        return ""
    # Euronext rendered text sometimes leaks page chrome into the actor field.
    text = re.sub(r"^.*?\bSubscribe\s+Issuer\b\s*", "", text, flags=re.I)
    company = " ".join(str(company or "").split()).strip(" ,.-–—")
    if company:
        text = re.sub(rf"^(?:{re.escape(company)}[\s:,.\-–—]*)+", "", text, flags=re.I).strip(" ,.-–—") or text
    text = re.sub(
        r"^(?:primary\s+insider\s+transactions?|mandatory\s+notification(?:\s+of\s+trade)?|prim[aæ]rinsider(?:transaksjoner?|handel))\s*[:\-–—]*\s*",
        "", text, flags=re.I,
    )
    return text.strip(" ,.-–—")


def _summary_actor(row):
    text = " ".join(str(row.get("summary") or row.get("description") or "").split())
    if not text:
        return ""
    text = re.sub(r"^.*?\bSubscribe\s+Issuer\b\s*", "", text, flags=re.I)
    company = " ".join(str(row.get("company") or "").split()).strip()
    if company:
        text = re.sub(rf"^(?:{re.escape(company)}[\s:,.\-–—]*)+", "", text, flags=re.I)
    role_words = (
        r"CEO|CFO|COO|CLO|CTO|EVP|chief\s+[^,]{2,40}|president|member\s+of\s+the\s+board|"
        r"board\s+member|chair(?:man|woman|person)?|business\s+unit\s+director|director|general\s+counsel"
    )
    matches = list(re.finditer(
        rf"([A-ZÆØÅ][A-Za-zÀ-ÿ'’.-]+(?:\s+[A-ZÆØÅ][A-Za-zÀ-ÿ'’.-]+){{1,5}})\s*,\s*(?=(?:{role_words})\b)",
        text,
        re.I,
    ))
    if not matches:
        return ""
    return _clean_actor_text(matches[-1].group(1), company)


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
    text = _clean_actor_text(value, row.get("company"))
    generic = _fold(text) in {
        "and primary insider", "primary insider", "insider", "the primary insider",
        "issuer", "company", "unknown",
    }
    inferred = _summary_actor(row)
    if inferred and (not text or generic or len(text.split()) < 2):
        text = inferred
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
    beneficial_reorg = (
        ("owned 100% by" in text or "100% owned by" in text or "wholly owned by" in text or "wholly-owned by" in text)
        and " from " in f" {text} "
        and (" personally" in text or " personal" in text)
    )
    return explicit or beneficial_reorg or any(p in text for p in phrases)


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


def _int_token(value):
    digits = re.sub(r"[^0-9]", "", str(value or ""))
    return int(digits) if digits else None


def _second_leg(row):
    """Extract an additional same-actor buy/sell leg from one disclosure sentence."""
    summary = " ".join(str(row.get("summary") or "").split())
    if not summary or _action(row) not in {"buy", "sell"}:
        return None
    match = re.search(
        r"\band\s+(\d{1,3}(?:[ ,\u00a0]\d{3})+|\d{1,12})\s+shares\b.{0,100}?"
        r"(?:at\s+)?(?:a\s+)?price\s+(?:of\s+)?(?:NOK\s*)?([0-9]{1,6}(?:[.,][0-9]{1,4})?)\s*(?:NOK)?\b",
        summary,
        re.I,
    )
    if not match:
        return None
    shares = _int_token(match.group(1))
    price = _num(match.group(2).replace(",", "."))
    if not shares or price is None or price <= 0:
        return None
    if shares == _num(row.get("shares")) and abs(price - (_num(row.get("price")) or 0)) < 1e-9:
        return None
    leg = dict(row)
    leg["shares"] = shares
    leg["price"] = price
    leg["transaction_value"] = shares * price
    leg["display_transaction_value"] = shares * price
    leg["display_value"] = shares * price
    leg["multi_leg_expanded"] = True
    return leg


def prepare_items(items):
    """Return signal-ready copies with inferred actors, transfer flags and extra legs."""
    prepared = []
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        inferred = _summary_actor(row)
        current = _clean_actor_text(
            row.get("person") or row.get("related_primary_insider") or row.get("entity") or row.get("insider") or row.get("actor"),
            row.get("company"),
        )
        if inferred and (not current or _fold(current) in {"and primary insider", "primary insider", "insider", "unknown"}):
            row["person"] = inferred
        elif current and row.get("person"):
            row["person"] = current
        if _is_transfer(row):
            row["internal_transfer"] = True
        prepared.append(row)
        extra = _second_leg(row)
        if extra:
            if inferred:
                extra["person"] = inferred
            prepared.append(extra)
    return prepared


def _transaction_key(row, action, day):
    actor = _actor_key(row)
    shares = _num(row.get("shares"))
    price = _num(row.get("price"))
    publication_day = _date(row.get("published_at"))
    dedupe_day = publication_day or day
    # Across correction/bilingual releases, the same economic transaction often has
    # a different node id but identical actor/day/action/shares/price. Prefer that
    # economic identity; use source id only when the core identity is incomplete.
    if actor and shares is not None and price is not None:
        return (actor, str(dedupe_day or ""), action, shares, price)
    source_id = str(row.get("node_id") or row.get("url") or row.get("source_url") or "").strip()
    return (actor, str(dedupe_day or ""), action, shares, price, source_id)


def analyze(result, window_days=14):
    out = dict(result or {})
    items = prepare_items(out.get("items") or [])
    buys, sells, excluded = [], [], []
    seen_transactions = set()
    duplicate_count = 0
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
        if action not in {"buy", "sell"}:
            continue
        key = _transaction_key(row, action, day)
        if key in seen_transactions:
            duplicate_count += 1
            continue
        seen_transactions.add(key)
        (buys if action == "buy" else sells).append(row)

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
        "deduplicated_row_count": duplicate_count,
        "prepared_item_count": len(items),
        "reasons": reasons,
        "score_effect": 0,
        "policy": "informational_only_pending_backtest",
    }
    out["insider_signal_v2_version"] = "2026-08-30-v4"
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
