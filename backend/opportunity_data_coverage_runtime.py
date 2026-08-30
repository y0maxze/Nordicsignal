"""Increase Early Opportunity learning coverage without weakening signal rules.

Two conservative changes live here:
1) a qualifying Opportunity state seen for the first time is recorded as a
   forward-validation event at the time NordicSignal first observes it;
2) recent Oslo primary-insider issuers can join a small rotating discovery scan
   only after Yahoo/Oslo identity checks and liquidity/history screening.

The core 24-stock universe, aggregate 0-100 score and Opportunity thresholds are
unchanged. Discovery instruments are persisted as inactive metadata rows so they
never enter the ordinary NordicSignal score refresh universe.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from difflib import SequenceMatcher
from statistics import median
import json
import re
import threading
import time

import extra_api
import insider_market_v2_runtime
import opportunity_tracking_runtime as tracking
from providers import YahooProvider

DISCOVERY_DAYS = 30
DISCOVERY_CACHE_SECONDS = 6 * 3600
MAX_DISCOVERY_CANDIDATES = 24
DISCOVERY_PER_SCAN = 8
MIN_HISTORY_BARS = 80
LIQUIDITY_WINDOW = 20
MIN_VALID_LIQUIDITY_BARS = 15
MIN_MEDIAN_DAILY_TURNOVER_NOK = 2_000_000.0
MAX_LAST_TRADE_AGE_DAYS = 10
MIN_NAME_MATCH = 0.58

_CACHE_LOCK = threading.RLock()
_DISCOVERY_CACHE = {"at": 0.0, "rows": [], "meta": {}}
_DISCOVERY_CURSOR = 0
_ORIGINAL_RECORD = tracking.record_opportunity
_ORIGINAL_RUN_SCAN = tracking._run_scan


def _now():
    return datetime.now(timezone.utc)


def _norm_name(value):
    value = str(value or "").lower()
    value = value.replace("ø", "o").replace("æ", "ae").replace("å", "a")
    value = re.sub(r"\b(asa|as|plc|limited|ltd|holding|holdings)\b", " ", value)
    return " ".join(re.findall(r"[a-z0-9]+", value))


def _name_similarity(left, right):
    a, b = _norm_name(left), _norm_name(right)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return min(1.0, max(len(a), len(b)) / max(1, min(len(a), len(b))) * 0.75)
    return SequenceMatcher(None, a, b).ratio()


def _resolve_oslo_equity(company, provider=None):
    """Resolve an Euronext issuer name to a Yahoo Oslo equity conservatively."""
    provider = provider or YahooProvider()
    params = {
        "q": str(company or "").strip(),
        "quotesCount": 12,
        "newsCount": 0,
        "enableFuzzyQuery": "true",
        "quotesQueryId": "tss_match_phrase_query",
        "region": "NO",
        "lang": "en-US",
    }
    candidates = []
    for base in tuple(dict.fromkeys(getattr(provider, "BASES", ()) or (provider.BASE,))):
        try:
            data = provider._get(f"{base}/v1/finance/search", params)
        except Exception:
            continue
        for row in (data or {}).get("quotes") or []:
            symbol = str(row.get("symbol") or "").upper().strip()
            quote_type = str(row.get("quoteType") or "").upper().strip()
            if quote_type != "EQUITY" or not symbol.endswith(".OL"):
                continue
            exchange_text = " ".join(str(row.get(key) or "") for key in ("exchange", "exchDisp", "market")).lower()
            if exchange_text and not any(token in exchange_text for token in ("oslo", "ose")):
                continue
            name = row.get("longname") or row.get("shortname") or symbol
            similarity = _name_similarity(company, name)
            if similarity < MIN_NAME_MATCH:
                continue
            candidates.append((similarity, symbol[:-3], str(name)))
        if candidates:
            break
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], len(item[2])), reverse=True)
    score, ticker, name = candidates[0]
    return {"ticker": ticker, "name": name, "match": round(score, 3)}


def _market_quality(history, now=None):
    """Require adequate history, current trading and non-trivial NOK turnover."""
    rows = [row for row in (history or []) if isinstance(row, dict)]
    if len(rows) < MIN_HISTORY_BARS:
        return {"qualified": False, "reason": "insufficient_history", "bars": len(rows)}

    valid = []
    for row in rows[-LIQUIDITY_WINDOW:]:
        try:
            close = float(row.get("close"))
            volume = float(row.get("volume"))
        except (TypeError, ValueError):
            continue
        if close > 0 and volume > 0:
            valid.append(close * volume)
    if len(valid) < MIN_VALID_LIQUIDITY_BARS:
        return {"qualified": False, "reason": "insufficient_liquidity_bars", "valid_bars": len(valid)}

    last_day = str(rows[-1].get("date") or "")[:10]
    try:
        last_date = datetime.fromisoformat(last_day).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return {"qualified": False, "reason": "invalid_last_trade_date"}
    reference = now or _now()
    age_days = max(0, (reference.date() - last_date.date()).days)
    if age_days > MAX_LAST_TRADE_AGE_DAYS:
        return {"qualified": False, "reason": "stale_market_data", "age_days": age_days}

    med_turnover = float(median(valid))
    if med_turnover < MIN_MEDIAN_DAILY_TURNOVER_NOK:
        return {
            "qualified": False,
            "reason": "below_turnover_floor",
            "median_daily_turnover_nok": round(med_turnover, 2),
        }
    return {
        "qualified": True,
        "bars": len(rows),
        "valid_liquidity_bars": len(valid),
        "median_daily_turnover_nok": round(med_turnover, 2),
        "last_trade_age_days": age_days,
    }


def _persist_discovery_row(row):
    conn = tracking.connect()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO stocks(ticker,name,sector,exchange,active) VALUES(?,?,?,?,0)",
            (row["ticker"], row["name"], "Discovery", "Oslo Børs"),
        )
        # Never set active=1 here: discovery must stay outside the core score universe.
        conn.execute(
            "UPDATE stocks SET name=?,exchange=? WHERE ticker=? AND active=0",
            (row["name"], "Oslo Børs", row["ticker"]),
        )
        conn.commit()
    finally:
        conn.close()


def _build_discovery_universe(provider=None):
    provider = provider or YahooProvider()
    try:
        announcements, feed_meta = insider_market_v2_runtime._announcements(DISCOVERY_DAYS)
    except Exception as exc:
        return [], {"status": "feed_error", "error": str(exc)}

    core = set()
    conn = tracking.connect()
    try:
        core = {str(row["ticker"]).upper() for row in conn.execute("SELECT ticker FROM stocks WHERE active=1").fetchall()}
    finally:
        conn.close()

    seen_companies = set()
    discovered = []
    rejected = {}
    for item in announcements or []:
        company = str(item.get("company") or "").strip()
        if not company:
            continue
        company_key = _norm_name(company)
        if not company_key or company_key in seen_companies:
            continue
        seen_companies.add(company_key)

        ticker = str(item.get("ticker") or "").upper().replace(".OL", "").strip()
        name = company
        match = 1.0 if ticker else None
        if not ticker:
            resolved = _resolve_oslo_equity(company, provider)
            if not resolved:
                rejected["unresolved"] = rejected.get("unresolved", 0) + 1
                continue
            ticker, name, match = resolved["ticker"], resolved["name"], resolved["match"]
        if ticker in core or any(row["ticker"] == ticker for row in discovered):
            continue

        try:
            history = provider.historical(ticker, "6m")
        except Exception:
            rejected["history_error"] = rejected.get("history_error", 0) + 1
            continue
        quality = _market_quality(history)
        if not quality.get("qualified"):
            reason = str(quality.get("reason") or "quality_rejected")
            rejected[reason] = rejected.get(reason, 0) + 1
            continue

        row = {
            "ticker": ticker,
            "name": name,
            "source": "recent_primary_insider_disclosure",
            "name_match": match,
            "quality": quality,
        }
        discovered.append(row)
        try:
            _persist_discovery_row(row)
        except Exception:
            pass
        if len(discovered) >= MAX_DISCOVERY_CANDIDATES:
            break

    meta = {
        "status": "ok",
        "announcements_seen": len(announcements or []),
        "qualified": len(discovered),
        "rejected": rejected,
        "feed_meta": feed_meta,
        "refreshed_at": _now().isoformat(),
    }
    return discovered, meta


def _discovery_rows(force=False):
    now = time.time()
    with _CACHE_LOCK:
        if not force and now - float(_DISCOVERY_CACHE.get("at") or 0) < DISCOVERY_CACHE_SECONDS:
            return [dict(row) for row in _DISCOVERY_CACHE.get("rows") or []]
    rows, meta = _build_discovery_universe()
    with _CACHE_LOCK:
        _DISCOVERY_CACHE.update({"at": now, "rows": [dict(row) for row in rows], "meta": dict(meta)})
    return [dict(row) for row in rows]


def _rotating_discovery_slice(rows):
    global _DISCOVERY_CURSOR
    rows = list(rows or [])
    if not rows:
        return []
    count = min(DISCOVERY_PER_SCAN, len(rows))
    start = _DISCOVERY_CURSOR % len(rows)
    chosen = [rows[(start + offset) % len(rows)] for offset in range(count)]
    _DISCOVERY_CURSOR = (start + count) % len(rows)
    return chosen


def _scan_rows():
    conn = tracking.connect()
    try:
        core = [dict(row) for row in conn.execute("SELECT ticker,name FROM stocks WHERE active=1 ORDER BY ticker").fetchall()]
    finally:
        conn.close()
    dynamic = _rotating_discovery_slice(_discovery_rows())
    core_tickers = {row["ticker"] for row in core}
    dynamic = [row for row in dynamic if row.get("ticker") not in core_tickers]
    return core + dynamic


def _record_first_observed(result, name=None):
    ticker = str(result.get("ticker") or "").upper().replace(".OL", "")
    if not ticker or result.get("status") != "ok":
        return {"emitted": False, "reason": "invalid_result"}
    opp = result.get("opportunity") or {}
    label = str(opp.get("label") or "NO_OPPORTUNITY")
    previous = tracking._state(ticker)
    if previous is not None or label not in tracking.TRACKED_LABELS:
        return _ORIGINAL_RECORD(result, name)

    components = opp.get("components") or {}
    observed_at = str(result.get("generated_at") or tracking._now())
    market_day = tracking._entry_date_from_result(result) or observed_at[:10]
    event_key = f"{market_day}:FIRST_OBSERVED->{label}"
    stored_result = dict(result)
    meta = dict(stored_result.get("tracking_meta") or {})
    meta.update({
        "event_kind": "first_observed_qualifying_state",
        "entry_semantics": "forward_from_first_nordicsignal_observation",
    })
    stored_result["tracking_meta"] = meta
    payload = json.dumps(stored_result, ensure_ascii=False, separators=(",", ":"), default=str)

    conn = tracking.connect()
    try:
        cur = conn.execute(
            "INSERT INTO opportunity_events(ticker,name,previous_label,label,score,entry_price,reversal_score,volume_ratio,insider_label,independent_buyers,buy_value_nok,payload,observed_at,created_at,event_key) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(ticker,event_key) DO NOTHING",
            (
                ticker, name or tracking._stock_name(ticker), None, label, opp.get("score"), tracking._entry_price(result),
                components.get("reversal_score"), components.get("volume_ratio"), components.get("insider_label"),
                components.get("independent_buyers"), components.get("buy_value_nok"), payload, observed_at,
                tracking._now(), event_key,
            ),
        )
        conn.commit()
        emitted = bool(getattr(cur, "rowcount", 0))
    finally:
        conn.close()
    tracking._set_state(ticker, stored_result)
    return {
        "emitted": emitted,
        "previous_label": None,
        "label": label,
        "event_kind": "first_observed_qualifying_state",
    }


def _run_scan_with_discovery():
    rows = []
    try:
        rows = _scan_rows()
    except Exception:
        # Core scan should remain available if discovery itself fails.
        conn = None
        try:
            conn = tracking.connect()
            rows = [dict(row) for row in conn.execute("SELECT ticker,name FROM stocks WHERE active=1 ORDER BY ticker").fetchall()]
        except Exception:
            rows = []
        finally:
            if conn is not None:
                conn.close()

    try:
        with ThreadPoolExecutor(max_workers=tracking.SCAN_WORKERS) as pool:
            futures = [pool.submit(tracking._scan_one, row) for row in rows]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    pass
    finally:
        with tracking._SCAN_LOCK:
            tracking._SCAN_RUNNING = False


def discovery_status():
    with _CACHE_LOCK:
        rows = [dict(row) for row in _DISCOVERY_CACHE.get("rows") or []]
        meta = dict(_DISCOVERY_CACHE.get("meta") or {})
        age = max(0.0, time.time() - float(_DISCOVERY_CACHE.get("at") or 0)) if _DISCOVERY_CACHE.get("at") else None
    return {
        "status": "ok",
        "core_score_universe_unchanged": True,
        "opportunity_thresholds_unchanged": True,
        "first_observed_qualifying_states_enabled": True,
        "discovery": {
            "cached_candidates": len(rows),
            "candidates_per_scan": DISCOVERY_PER_SCAN,
            "max_candidates": MAX_DISCOVERY_CANDIDATES,
            "cache_age_seconds": round(age, 1) if age is not None else None,
            "criteria": {
                "source": "recent Euronext primary-insider disclosures",
                "history_bars_min": MIN_HISTORY_BARS,
                "median_daily_turnover_nok_min": MIN_MEDIAN_DAILY_TURNOVER_NOK,
                "recent_trade_age_days_max": MAX_LAST_TRADE_AGE_DAYS,
                "name_match_min": MIN_NAME_MATCH,
            },
            "meta": meta,
        },
    }


def install():
    if getattr(extra_api, "_opportunity_data_coverage_runtime", False):
        return
    tracking.record_opportunity = _record_first_observed
    tracking._run_scan = _run_scan_with_discovery

    original_install = extra_api.install

    def patched_install(app):
        original_install(app)

        @app.get("/api/opportunity-discovery/status")
        def opportunity_discovery_status():
            return discovery_status()

    extra_api.install = patched_install
    extra_api._opportunity_data_coverage_runtime = True


install()
