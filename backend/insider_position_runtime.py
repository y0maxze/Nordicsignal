"""Persistent actor-level insider ledger and behavior classification.

This runtime sits after the live insider source patches. Every verified disclosed
buy/sell with an identified actor is stored in NordicSignal's existing database.
That lets a later sell be linked back to an earlier buy even after the original
announcement falls out of the provider's short recent-news window.

The classifications describe observable disclosure behavior, not investor intent.
"No later sale found" therefore means exactly that: no later sale exists in the
public transactions NordicSignal has observed/stored for that actor and ticker.
"""

from collections import defaultdict, deque
from datetime import date, datetime, timezone
import hashlib
import re
import threading

from database import connect
from insider_runtime import canonical_url, norm
from providers import NordicRegulatoryProvider


_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False
_MAX_LEDGER_ROWS = 500


def _date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except (TypeError, ValueError):
        return None


def _num(value):
    return float(value) if isinstance(value, (int, float)) else None


def _actor(row):
    name = row.get("person") or row.get("entity") or row.get("insider") or row.get("holder")
    name = " ".join(str(name or "").split()).strip()
    return name or None


def _release_identity(url):
    text = str(url or "")
    match = re.search(r"/news-release/20\d{2}/\d{1,2}/\d{1,2}/(\d+)/", text, re.I)
    if match:
        return "gnw:" + match.group(1)
    return canonical_url(text)


def trade_key(ticker, row):
    actor = norm(_actor(row))
    direction = row.get("direction") or row.get("transaction_type") or "unknown"
    traded = row.get("trade_date") or row.get("date") or ""
    shares = row.get("shares")
    price = row.get("price")
    # Actor/date/direction/size is deliberately source-independent so the same
    # regulated transaction syndicated by Euronext and GlobeNewswire is one event.
    # The release identity is only needed when size is unavailable.
    parts = [str(ticker or "").upper(), actor, str(traded), str(direction), str(shares)]
    if shares is None:
        parts.extend([str(price), _release_identity(row.get("url"))])
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _ensure_schema(conn):
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS insider_ledger (
                trade_key TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                actor_key TEXT NOT NULL,
                actor_name TEXT NOT NULL,
                actor_type TEXT,
                role TEXT,
                transaction_type TEXT NOT NULL,
                shares DOUBLE PRECISION,
                price DOUBLE PRECISION,
                trade_date TEXT,
                source TEXT,
                url TEXT,
                first_seen_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_insider_ledger_ticker_actor_date "
            "ON insider_ledger(ticker, actor_key, trade_date)"
        )
        conn.commit()
        _SCHEMA_READY = True


def _persist_and_load(ticker, items):
    """Persist verified current rows and return accumulated rows for the ticker."""
    conn = connect()
    try:
        _ensure_schema(conn)
        now = datetime.now(timezone.utc).isoformat()
        for row in items or []:
            actor_name = _actor(row)
            actor_key = norm(actor_name)
            direction = row.get("direction") or row.get("transaction_type")
            traded = row.get("trade_date") or row.get("date")
            if not actor_key or direction not in {"buy", "sell"} or not traded:
                continue
            if not (row.get("verified_detail") or row.get("issuer_verified")):
                continue
            key = trade_key(ticker, row)
            conn.execute(
                """
                INSERT OR IGNORE INTO insider_ledger
                (trade_key,ticker,actor_key,actor_name,actor_type,role,transaction_type,
                 shares,price,trade_date,source,url,first_seen_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    key, ticker, actor_key, actor_name, row.get("actor_type"), row.get("role"),
                    direction, _num(row.get("shares")), _num(row.get("price")), str(traded)[:10],
                    row.get("source"), row.get("url"), now,
                ),
            )
            # A later parse may contain richer role/price/source information.
            conn.execute(
                """
                UPDATE insider_ledger SET
                    actor_name=?,
                    actor_type=COALESCE(?,actor_type),
                    role=COALESCE(?,role),
                    price=COALESCE(?,price),
                    source=COALESCE(?,source),
                    url=COALESCE(?,url)
                WHERE trade_key=?
                """,
                (
                    actor_name, row.get("actor_type"), row.get("role"), _num(row.get("price")),
                    row.get("source"), row.get("url"), key,
                ),
            )
        conn.commit()
        cursor = conn.execute(
            """
            SELECT trade_key,ticker,actor_key,actor_name,actor_type,role,transaction_type,
                   shares,price,trade_date,source,url,first_seen_at
            FROM insider_ledger
            WHERE ticker=?
            ORDER BY trade_date ASC, first_seen_at ASC
            LIMIT ?
            """,
            (ticker, _MAX_LEDGER_ROWS),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def _match_lots(trades):
    """FIFO-match disclosed buy quantities against disclosed sells.

    This is a disclosure-flow model, not a claim about the actor's actual tax lots.
    It is used only to estimate how quickly a publicly observed purchase was later
    reduced/sold.
    """
    lots = deque()
    matches = []
    for row in trades:
        traded = _date(row.get("trade_date"))
        shares = _num(row.get("shares"))
        direction = row.get("transaction_type")
        if not traded or direction not in {"buy", "sell"}:
            continue
        if direction == "buy":
            lots.append({"date": traded, "remaining": shares})
            continue

        # If size is unavailable, still create an event-level pair to preserve the
        # buy->sell chronology without pretending that quantities matched.
        if shares is None:
            candidate = next((lot for lot in reversed(lots) if lot["date"] <= traded), None)
            if candidate:
                matches.append({
                    "buy_date": candidate["date"].isoformat(),
                    "sell_date": traded.isoformat(),
                    "days": (traded - candidate["date"]).days,
                    "shares": None,
                })
            continue

        remaining = max(0.0, shares)
        while remaining > 0 and lots:
            lot = lots[0]
            if lot["date"] > traded:
                break
            lot_qty = lot["remaining"]
            if lot_qty is None:
                matches.append({
                    "buy_date": lot["date"].isoformat(), "sell_date": traded.isoformat(),
                    "days": (traded - lot["date"]).days, "shares": None,
                })
                lots.popleft()
                break
            used = min(remaining, max(0.0, lot_qty))
            if used <= 0:
                lots.popleft()
                continue
            matches.append({
                "buy_date": lot["date"].isoformat(), "sell_date": traded.isoformat(),
                "days": (traded - lot["date"]).days, "shares": used,
            })
            remaining -= used
            lot["remaining"] -= used
            if lot["remaining"] <= 1e-9:
                lots.popleft()
    return matches


def _classification(trades, matches, today):
    buys = [x for x in trades if x.get("transaction_type") == "buy"]
    sells = [x for x in trades if x.get("transaction_type") == "sell"]
    latest = trades[-1] if trades else {}
    latest_direction = latest.get("transaction_type")
    last_buy = _date(buys[-1].get("trade_date")) if buys else None
    last_sell = _date(sells[-1].get("trade_date")) if sells else None
    quick = [m for m in matches if m["days"] <= 30]

    if latest_direction == "sell":
        later_matches = [m for m in matches if m.get("sell_date") == str(latest.get("trade_date"))[:10]]
        holding_days = max((m["days"] for m in later_matches), default=None)
        if len(quick) >= 2:
            return "short_term_trading", "Kortvarig handel", holding_days
        if holding_days is not None and holding_days <= 30:
            return "quick_exit", "Solgte raskt etter kjøp", holding_days
        if holding_days is not None and holding_days >= 180:
            return "long_hold_exit", "Solgte etter lang holdetid", holding_days
        if buys:
            return "reducing", "Reduserer etter tidligere kjøp", holding_days
        return "sell_only", "Salg – tidligere kjøp ikke observert", None

    if latest_direction == "buy":
        days_open = (today - last_buy).days if last_buy else None
        if sells:
            return "reaccumulating", "Kjøper igjen etter tidligere salg", days_open
        if days_open is not None and days_open >= 180:
            return "long_hold_observed", "Holdt lenge uten senere salg", days_open
        if days_open is not None and days_open >= 30:
            return "holding", "Holder – intet senere salg funnet", days_open
        return "recent_buy", "Nytt kjøp – intet senere salg funnet", days_open

    return "activity", "Blandet/ukjent aktivitet", None


def build_actor_history(rows, now=None):
    """Build an actor behavior summary from accumulated disclosed transactions."""
    today = (now.date() if isinstance(now, datetime) else now) if now else date.today()
    groups = defaultdict(list)
    for raw in rows or []:
        actor_name = _actor(raw)
        actor_key = raw.get("actor_key") or norm(actor_name)
        traded = _date(raw.get("trade_date") or raw.get("date"))
        direction = raw.get("transaction_type") or raw.get("direction")
        if not actor_key or not traded or direction not in {"buy", "sell"}:
            continue
        row = dict(raw)
        row["actor_key"] = actor_key
        row["actor_name"] = actor_name or raw.get("actor_name") or actor_key
        row["transaction_type"] = direction
        row["trade_date"] = traded.isoformat()
        groups[actor_key].append(row)

    histories = []
    for actor_key, trades in groups.items():
        trades.sort(key=lambda x: (x.get("trade_date") or "", x.get("first_seen_at") or ""))
        buys = [x for x in trades if x["transaction_type"] == "buy"]
        sells = [x for x in trades if x["transaction_type"] == "sell"]
        matches = _match_lots(trades)
        code, label, holding_days = _classification(trades, matches, today)
        known_buys = sum(_num(x.get("shares")) or 0.0 for x in buys)
        known_sells = sum(_num(x.get("shares")) or 0.0 for x in sells)
        all_sizes_known = all(_num(x.get("shares")) is not None for x in trades)
        net = known_buys - known_sells if all_sizes_known else None
        last_buy = buys[-1].get("trade_date") if buys else None
        last_sell = sells[-1].get("trade_date") if sells else None
        latest = trades[-1]
        first_date = trades[0].get("trade_date")
        latest_date = latest.get("trade_date")
        no_sale_after_latest_buy = bool(last_buy and (not last_sell or last_sell < last_buy))
        histories.append({
            "actor_key": actor_key,
            "actor": latest.get("actor_name") or _actor(latest),
            "actor_type": latest.get("actor_type"),
            "role": latest.get("role") or next((x.get("role") for x in reversed(trades) if x.get("role")), None),
            "pattern": code,
            "pattern_label": label,
            "buy_count": len(buys),
            "sell_count": len(sells),
            "known_buy_shares": known_buys if buys else 0.0,
            "known_sell_shares": known_sells if sells else 0.0,
            "net_observed_shares": net,
            "last_buy_date": last_buy,
            "last_sell_date": last_sell,
            "latest_action": latest.get("transaction_type"),
            "latest_trade_date": latest_date,
            "first_observed_trade_date": first_date,
            "observed_span_days": (_date(latest_date) - _date(first_date)).days if first_date and latest_date else 0,
            "holding_days": holding_days,
            "no_sale_after_latest_buy": no_sale_after_latest_buy,
            "round_trips": matches[-8:],
            "timeline": [
                {
                    "date": x.get("trade_date"),
                    "action": x.get("transaction_type"),
                    "shares": _num(x.get("shares")),
                    "price": _num(x.get("price")),
                    "url": x.get("url"),
                }
                for x in reversed(trades[-12:])
            ],
        })

    histories.sort(key=lambda x: x.get("latest_trade_date") or "", reverse=True)
    return histories


def enrich_result(result, ticker):
    out = dict(result or {})
    current_items = [dict(x) for x in (out.get("items") or [])]
    history_rows = current_items
    source = "current_response"
    try:
        stored = _persist_and_load(ticker, current_items)
        if stored:
            history_rows = stored
            source = "persistent_ledger"
    except Exception as exc:
        # Insider data must remain available if the database is temporarily down.
        out["actor_history_storage_error"] = type(exc).__name__

    histories = build_actor_history(history_rows)
    by_actor = {x["actor_key"]: x for x in histories}
    for item in current_items:
        actor_key = norm(_actor(item))
        summary = by_actor.get(actor_key)
        if summary:
            item["actor_pattern"] = summary.get("pattern")
            item["actor_pattern_label"] = summary.get("pattern_label")
            item["actor_last_sell_date"] = summary.get("last_sell_date")
            item["actor_no_sale_after_latest_buy"] = summary.get("no_sale_after_latest_buy")
    out["items"] = current_items
    out["actor_history"] = histories
    dates = [_date(x.get("trade_date")) for x in history_rows]
    dates = [x for x in dates if x]
    out["actor_history_source"] = source
    out["actor_history_observed_from"] = min(dates).isoformat() if dates else None
    out["actor_history_observed_to"] = max(dates).isoformat() if dates else None
    out["actor_history_note"] = (
        "Mønsteret bygger på offentlige insiderhandler NordicSignal har observert og lagret. "
        "'Ingen senere salg funnet' betyr ikke at NordicSignal kjenner hele investorens beholdning eller motiv."
    )
    out["insider_behavior_version"] = "2026-08-27-v1"
    return out


def install():
    if getattr(NordicRegulatoryProvider, "_insider_position_runtime_v1", False):
        return
    original = NordicRegulatoryProvider.insider

    def insider(self, ticker, company_name=""):
        symbol = str(ticker or "").upper().strip()
        return enrich_result(original(self, symbol, company_name), symbol)

    NordicRegulatoryProvider.insider = insider
    NordicRegulatoryProvider._insider_position_runtime_v1 = True


install()
