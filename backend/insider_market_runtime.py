"""Market-wide Oslo Børs primary-insider scanner.

The stock-specific insider endpoint is intentionally strict and detailed. This
runtime adds one lightweight market feed that scans recent official Euronext
company announcements once, extracts primary-insider transactions across the
market, classifies ordinary share trades separately from transfers/options/etc.,
and aggregates cluster/repeated activity for the Insider Activity dashboard.
"""

from collections import defaultdict
from datetime import datetime, timezone, timedelta
import re
import threading
import time

import extra_api
import general_news_runtime
import insider_runtime
import news_runtime


_CACHE_LOCK = threading.RLock()
_CACHE = {"at": 0.0, "value": None}
_CACHE_TTL = 120
_MAX_DISCLOSURES = 36

_INSIDER_WORDS = (
    "primary insider", "mandatory notification of trade", "mandatory notification",
    "insider transaction", "pdmr", "primærinsider", "primaerinsider",
    "meldepliktig handel",
)
_TRANSFER_WORDS = (
    "transfer of shares", "transferred shares", "internal transfer", "transferred from",
    "transferred to", "overføring av aksjer", "overforte aksjer", "overført aksjer",
)
_DERIVATIVE_WORDS = (
    "subscription right", "subscription rights", "warrant", "warrants", "option",
    "options", "synthetic share", "synthetic shares", "tegningsrett", "tegningsretter",
    "opsjon", "opsjoner", "syntetisk aksje", "syntetiske aksjer",
)
_EMPLOYEE_WORDS = (
    "employee share", "employee shares", "employee share purchase", "employee program",
    "employee programme", "share purchase programme", "share purchase program",
    "ansatteaksjer", "ansattprogram", "aksjespareprogram",
)
_AWARD_WORDS = (
    "allocation of", "allocated", "grant of", "granted", "vesting", "vested",
    "tildeling", "tildelt",
)


def _norm(value):
    return news_runtime._norm(value)


def _is_insider_title(title, category=None):
    low = _norm(title)
    return category == "Insider" or any(_norm(x) in low for x in _INSIDER_WORDS)


def _parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(str(value)[:10]).replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return None


def _company_and_ticker(item, body):
    title = " ".join(str(item.get("title") or "").split()).strip()
    ticker = str(item.get("ticker") or "").upper().strip() or None
    prefix = title.split(":", 1)[0].strip() if ":" in title else ""

    if not ticker and prefix and re.fullmatch(r"[A-Z0-9.\-]{2,12}", prefix):
        ticker = prefix.replace(".OL", "")

    company = None
    if ticker and ticker in insider_runtime.ISSUERS:
        company = insider_runtime.ISSUERS[ticker][0]
    elif prefix and not re.fullmatch(r"[A-Z0-9.\-]{2,12}", prefix):
        company = prefix

    if not company:
        # Many issuer releases use "Company ASA - Mandatory notification...".
        m = re.match(
            r"^\s*(.{3,100}?(?:ASA|AS|PLC|Ltd\.?|Limited))\s*(?:-|–|—|:)\s*",
            title,
            re.I,
        )
        if m:
            company = " ".join(m.group(1).split()).strip()

    if not company and ticker:
        company = ticker
    if not company:
        # Keep an identifiable label without pretending it is a verified issuer name.
        company = title[:90] or "Oslo Børs-selskap"
    return ticker, company


def _currency(body, price=None):
    text = str(body or "")
    if price is not None:
        p = re.escape(str(price))
        m = re.search(rf"\b(NOK|SEK|DKK|EUR|USD|GBP)\b.{{0,35}}{p}", text, re.I)
        if m:
            return m.group(1).upper()
    m = re.search(r"\b(NOK|SEK|DKK|EUR|USD|GBP)\b", text, re.I)
    return m.group(1).upper() if m else None


def _activity_type(body, row):
    low = _norm(body)
    if any(_norm(x) in low for x in _TRANSFER_WORDS):
        return "internal_transfer", False
    if any(_norm(x) in low for x in _DERIVATIVE_WORDS):
        return "rights_or_derivatives", False
    if any(_norm(x) in low for x in _EMPLOYEE_WORDS):
        return "employee_program", False
    if any(_norm(x) in low for x in _AWARD_WORDS) and row.get("direction") not in {"buy", "sell"}:
        return "award", False
    if row.get("direction") == "buy":
        return "share_purchase", True
    if row.get("direction") == "sell":
        return "share_sale", True
    return "other_disclosure", False


def _candidate_announcements():
    items = []
    seen = set()
    for source_url in (news_runtime.EURONEXT_LATEST, news_runtime.EURONEXT_ARCHIVE):
        try:
            html = news_runtime._fetch_text(source_url)
            rows = general_news_runtime.parse_general_euronext_html(html, 60)
        except Exception:
            continue
        for row in rows:
            if not _is_insider_title(row.get("title"), row.get("category")):
                continue
            url = row.get("url") or ""
            if not url or url in seen:
                continue
            seen.add(url)
            items.append(row)
    items.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    return items[:_MAX_DISCLOSURES]


def _extract_disclosure(item):
    url = item.get("url") or ""
    detail = news_runtime._fetch_text(url)
    parser = insider_runtime._Parser()
    parser.feed(detail)
    body = parser.text
    low = _norm(body)
    if not any(_norm(x) in low for x in _INSIDER_WORDS):
        return []

    ticker, company = _company_and_ticker(item, body)
    parse_symbol = ticker or company
    rows = insider_runtime.parse_trades(
        body,
        parse_symbol,
        item.get("title") or "Primary insider transaction",
        "Euronext Oslo Børs Newspoint",
        url,
    )
    out = []
    for raw in rows:
        row = dict(raw)
        # parse_trades keeps the sentence/segment that produced each trade in
        # `summary`. Classify that segment, not the whole release: one disclosure
        # can contain an internal transfer and a separate genuine share purchase.
        segment = row.get("summary") or body
        activity_type, signal_eligible = _activity_type(segment, row)
        currency = _currency(segment, row.get("price")) or _currency(body, row.get("price"))
        value = row.get("transaction_value")
        row.update({
            "ticker": ticker,
            "company": company,
            "published_at": item.get("published_at"),
            "activity_type": activity_type,
            "signal_eligible": signal_eligible,
            "currency": currency,
            "display_value": value,
            "value_basis": "reported_transaction_price" if value is not None else None,
            "official": True,
            "source": "Euronext Oslo Børs Newspoint",
            "url": url,
        })
        out.append(row)
    return out


def _trade_identity(row):
    actor = insider_runtime.norm(row.get("person") or row.get("entity") or row.get("insider"))
    return (
        row.get("ticker") or insider_runtime.norm(row.get("company")),
        str(row.get("trade_date") or row.get("date") or "")[:10],
        row.get("direction"),
        row.get("shares"),
        actor,
        row.get("activity_type"),
    )


def _pulse_groups(items):
    groups = defaultdict(list)
    for item in items:
        key = item.get("ticker") or insider_runtime.norm(item.get("company"))
        if key:
            groups[key].append(item)

    pulses = []
    for key, rows in groups.items():
        rows.sort(key=lambda x: (x.get("trade_date") or x.get("date") or x.get("published_at") or ""))
        eligible = [x for x in rows if x.get("signal_eligible")]
        buys = [x for x in eligible if x.get("direction") == "buy"]
        sells = [x for x in eligible if x.get("direction") == "sell"]
        buy_actors = {insider_runtime.norm(x.get("person") or x.get("entity") or x.get("insider")) for x in buys}
        sell_actors = {insider_runtime.norm(x.get("person") or x.get("entity") or x.get("insider")) for x in sells}
        buy_actors.discard("")
        sell_actors.discard("")
        actor_buy_counts = defaultdict(int)
        for x in buys:
            actor = insider_runtime.norm(x.get("person") or x.get("entity") or x.get("insider"))
            if actor:
                actor_buy_counts[actor] += 1

        values = defaultdict(lambda: {"buy": 0.0, "sell": 0.0, "buy_count": 0, "sell_count": 0})
        for x in eligible:
            value = x.get("display_value")
            currency = x.get("currency")
            if value is None or not currency or x.get("direction") not in {"buy", "sell"}:
                continue
            values[currency][x["direction"]] += float(value)
            values[currency][x["direction"] + "_count"] += 1

        flags = []
        if len(buy_actors) >= 2:
            flags.append("cluster_buying")
        if any(count >= 2 for count in actor_buy_counts.values()):
            flags.append("repeated_buying")
        if len(sell_actors) >= 2:
            flags.append("cluster_selling")
        if any(
            x.get("currency") == "NOK" and isinstance(x.get("display_value"), (int, float)) and x["display_value"] >= 1_000_000
            for x in buys
        ):
            flags.append("large_buy")
        if buys and sells:
            flags.append("mixed_activity")

        if "cluster_buying" in flags:
            label, tone = "KLYNGEKJØP", "positive"
        elif "repeated_buying" in flags:
            label, tone = "GJENTATT KJØP", "positive"
        elif "large_buy" in flags:
            label, tone = "STORT KJØP", "positive"
        elif len(sell_actors) >= 2:
            label, tone = "SALGSAKTIVITET", "negative"
        elif sells and not buys:
            label, tone = "INNSIDERSALG", "negative"
        elif buys:
            label, tone = "INSIDERKJØP", "positive"
        else:
            label, tone = "IKKE SIGNAL", "neutral"

        latest = rows[-1]
        pulses.append({
            "ticker": latest.get("ticker"),
            "company": latest.get("company") or key,
            "latest_date": latest.get("trade_date") or latest.get("date") or latest.get("published_at"),
            "buy_count": len(buys),
            "sell_count": len(sells),
            "unique_buyers": len(buy_actors),
            "unique_sellers": len(sell_actors),
            "excluded_count": len(rows) - len(eligible),
            "flags": flags,
            "signal_label": label,
            "tone": tone,
            "values": [dict(currency=currency, **amounts) for currency, amounts in sorted(values.items())],
            "actors": list(dict.fromkeys(
                (x.get("person") or x.get("entity") or x.get("insider")) for x in reversed(eligible)
                if (x.get("person") or x.get("entity") or x.get("insider"))
            ))[:6],
            "url": latest.get("url"),
        })

    weight = {"KLYNGEKJØP": 6, "GJENTATT KJØP": 5, "STORT KJØP": 4, "SALGSAKTIVITET": 4, "INNSIDERSALG": 3, "INSIDERKJØP": 2, "IKKE SIGNAL": 0}
    pulses.sort(key=lambda x: (weight.get(x.get("signal_label"), 0), x.get("latest_date") or ""), reverse=True)
    return pulses


def market_insider_feed(limit=60, days=14, refresh=False):
    limit = max(1, min(int(limit or 60), 100))
    days = max(1, min(int(days or 14), 90))
    now = time.time()
    with _CACHE_LOCK:
        if not refresh and _CACHE["value"] is not None and now - _CACHE["at"] < _CACHE_TTL:
            cached = dict(_CACHE["value"])
            cached["items"] = list(cached.get("items") or [])[:limit]
            return cached

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    items = []
    errors = []
    for announcement in _candidate_announcements():
        published = _parse_iso(announcement.get("published_at"))
        if published and published < cutoff:
            continue
        try:
            items.extend(_extract_disclosure(announcement))
        except Exception as exc:
            errors.append(type(exc).__name__)

    dedup = {}
    for row in items:
        key = _trade_identity(row)
        current = dedup.get(key)
        if current is None or (current.get("display_value") is None and row.get("display_value") is not None):
            dedup[key] = row
    items = list(dedup.values())
    items.sort(key=lambda x: (x.get("trade_date") or x.get("date") or x.get("published_at") or ""), reverse=True)
    pulses = _pulse_groups(items)
    eligible_count = sum(1 for x in items if x.get("signal_eligible"))
    value = {
        "scope": "oslo_bors_market",
        "status": "live" if items else "no_recent_disclosures",
        "source": "Euronext Oslo Børs Newspoint",
        "items": items,
        "pulses": pulses,
        "eligible_trade_count": eligible_count,
        "excluded_non_signal_count": len(items) - eligible_count,
        "days": days,
        "errors": errors[:5],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": "Ordinary disclosed share purchases/sales are separated from transfers, rights/options, awards and employee-program activity. Classification describes the disclosed transaction, not investment intent.",
    }
    with _CACHE_LOCK:
        _CACHE.update({"at": now, "value": value})
    result = dict(value)
    result["items"] = items[:limit]
    return result


def install():
    if getattr(extra_api, "_insider_market_runtime_v1", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)

        @app.get("/api/insider-market")
        def insider_market(limit: int = 60, days: int = 14, refresh: bool = False):
            return market_insider_feed(limit=limit, days=days, refresh=refresh)

    extra_api.install = patched_install
    extra_api._insider_market_runtime_v1 = True


install()
