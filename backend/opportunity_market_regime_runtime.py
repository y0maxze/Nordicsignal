"""Market-regime and benchmark-adjusted validation for Early Opportunity.

This is a measurement-only layer. It never changes the aggregate 0-100 score,
Opportunity thresholds, event generation or push policy. It adds two protections to
forward validation:

1) each event is classified against the broad Oslo market using only benchmark data
   from trading days *before* the event, preventing look-ahead in the regime label;
2) settled stock returns are compared with OSEBX close-to-close returns so Learning
   can distinguish raw gains from market-adjusted excess return (alpha).

Calibration readiness additionally requires regime diversity across the settled
5d/10d/20d samples. All raw events and raw forward returns remain untouched.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from statistics import median
import threading
import time

import opportunity_tracking_runtime as tracking
from providers import YahooProvider

BENCHMARK_ID = "OSEBX"
BENCHMARK_SYMBOLS = ("OSEBX.OL", "^OSEBX", "^OSEAX")
REQUIRED_HORIZONS = (5, 10, 20)
REGIME_LOOKBACK_DAYS = 20
REGIME_MA_DAYS = 50
REGIME_RETURN_THRESHOLD_PCT = 2.0
MIN_SUPPORTED_REGIMES = 2
MIN_EVENTS_PER_REGIME = 5
MAX_SINGLE_REGIME_SHARE_PCT = 75.0
MIN_POSITIVE_ALPHA_HORIZONS = 2
BENCHMARK_CACHE_TTL_SECONDS = 30 * 60
BENCHMARK_HISTORY_DAYS = 900

_BASE_REPORT = tracking.opportunity_performance
_BASE_RECORD = tracking.record_opportunity
_BASE_SETTLE = tracking.settle_forward_returns

_CACHE_LOCK = threading.RLock()
_BENCHMARK_CACHE = {"at": 0.0, "symbol": None, "rows": []}
_BACKFILL_LOCK = threading.Lock()
_BACKFILL_RUNNING = False


def _now():
    return datetime.now(timezone.utc).isoformat()


def _ensure_schema():
    conn = tracking.connect()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS opportunity_market_context (
          event_id BIGINT PRIMARY KEY,
          benchmark_id TEXT NOT NULL,
          benchmark_symbol TEXT NOT NULL,
          event_market_date TEXT,
          benchmark_entry_date TEXT,
          benchmark_entry_close DOUBLE PRECISION,
          regime_asof_date TEXT,
          regime TEXT,
          benchmark_ret20_pct DOUBLE PRECISION,
          benchmark_ma50_gap_pct DOUBLE PRECISION,
          captured_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS opportunity_market_returns (
          event_id BIGINT NOT NULL,
          horizon_days INTEGER NOT NULL,
          benchmark_target_date TEXT,
          benchmark_return_pct DOUBLE PRECISION,
          excess_return_pct DOUBLE PRECISION,
          settled_at TEXT NOT NULL,
          PRIMARY KEY(event_id,horizon_days)
        );
        """)
        conn.commit()
    finally:
        conn.close()


def _chart_rows(provider, symbol):
    end = datetime.now(timezone.utc) + timedelta(days=1)
    start = end - timedelta(days=BENCHMARK_HISTORY_DAYS)
    data = provider._get(
        f"{provider.BASE}/v8/finance/chart/{symbol}",
        {
            "period1": int(start.timestamp()),
            "period2": int(end.timestamp()),
            "interval": "1d",
            "events": "div,splits",
        },
    )
    result = ((data.get("chart") or {}).get("result") or [])
    if not result:
        raise RuntimeError(f"No benchmark history for {symbol}")
    result = result[0]
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    rows = []
    for i, ts in enumerate(timestamps):
        if i >= len(closes) or closes[i] is None:
            continue
        try:
            close = float(closes[i])
        except (TypeError, ValueError):
            continue
        if close <= 0:
            continue
        rows.append({
            "date": datetime.fromtimestamp(int(ts), timezone.utc).date().isoformat(),
            "close": close,
        })
    rows.sort(key=lambda row: row["date"])
    if len(rows) < REGIME_MA_DAYS + 1:
        raise RuntimeError(f"Insufficient benchmark history for {symbol}")
    return rows


def _benchmark_rows(force=False, provider=None):
    now = time.time()
    with _CACHE_LOCK:
        cached_rows = [dict(row) for row in _BENCHMARK_CACHE.get("rows") or []]
        cached_symbol = _BENCHMARK_CACHE.get("symbol")
        age = now - float(_BENCHMARK_CACHE.get("at") or 0)
        if cached_rows and not force and age < BENCHMARK_CACHE_TTL_SECONDS:
            return cached_symbol, cached_rows

    provider = provider or YahooProvider()
    last_error = None
    for symbol in BENCHMARK_SYMBOLS:
        try:
            rows = _chart_rows(provider, symbol)
            with _CACHE_LOCK:
                _BENCHMARK_CACHE.update({"at": now, "symbol": symbol, "rows": [dict(row) for row in rows]})
            return symbol, rows
        except Exception as exc:
            last_error = exc

    # A stale cache is preferable to dropping regime metadata during a transient
    # upstream outage. The cache is measurement-only and never drives a signal.
    if cached_rows:
        return cached_symbol, cached_rows
    raise RuntimeError(str(last_error or "OSEBX history unavailable"))


def _event_market_date(event):
    value = tracking._entry_date_from_event(event)
    if value:
        return value
    observed = str((event or {}).get("observed_at") or "")[:10]
    return observed if len(observed) == 10 else None


def _row_on_or_before(rows, target_date):
    chosen = None
    for row in rows or []:
        if str(row.get("date") or "") > str(target_date or ""):
            break
        chosen = row
    return chosen


def _classify_regime(event, rows):
    """Classify using benchmark closes strictly before the event market date."""
    event_date = _event_market_date(event)
    if not event_date:
        return None
    history = [row for row in (rows or []) if str(row.get("date") or "") < event_date]
    if len(history) < max(REGIME_MA_DAYS, REGIME_LOOKBACK_DAYS + 1):
        return None

    prior = history[-1]
    ma_window = history[-REGIME_MA_DAYS:]
    ret_window = history[-(REGIME_LOOKBACK_DAYS + 1):]
    prior_close = float(prior["close"])
    ma50 = sum(float(row["close"]) for row in ma_window) / len(ma_window)
    ret20 = (prior_close / float(ret_window[0]["close"]) - 1.0) * 100.0
    ma_gap = (prior_close / ma50 - 1.0) * 100.0 if ma50 > 0 else 0.0

    if ret20 >= REGIME_RETURN_THRESHOLD_PCT and ma_gap > 0:
        regime = "RISK_ON"
    elif ret20 <= -REGIME_RETURN_THRESHOLD_PCT and ma_gap < 0:
        regime = "RISK_OFF"
    else:
        regime = "NEUTRAL"

    entry = _row_on_or_before(rows, event_date)
    return {
        "event_market_date": event_date,
        "benchmark_entry_date": entry.get("date") if entry else None,
        "benchmark_entry_close": float(entry["close"]) if entry else None,
        "regime_asof_date": prior.get("date"),
        "regime": regime,
        "benchmark_ret20_pct": round(ret20, 4),
        "benchmark_ma50_gap_pct": round(ma_gap, 4),
    }


def _persist_market_context(event, symbol, rows):
    context = _classify_regime(event, rows)
    if not context:
        return False
    event_id = int(event["id"])
    conn = tracking.connect()
    try:
        cur = conn.execute(
            "INSERT INTO opportunity_market_context(event_id,benchmark_id,benchmark_symbol,event_market_date,benchmark_entry_date,benchmark_entry_close,regime_asof_date,regime,benchmark_ret20_pct,benchmark_ma50_gap_pct,captured_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(event_id) DO NOTHING",
            (
                event_id, BENCHMARK_ID, symbol, context["event_market_date"],
                context["benchmark_entry_date"], context["benchmark_entry_close"],
                context["regime_asof_date"], context["regime"],
                context["benchmark_ret20_pct"], context["benchmark_ma50_gap_pct"], _now(),
            ),
        )
        conn.commit()
        return bool(getattr(cur, "rowcount", 0))
    finally:
        conn.close()


def _latest_event(ticker):
    conn = tracking.connect()
    try:
        row = conn.execute(
            "SELECT * FROM opportunity_events WHERE ticker=? ORDER BY id DESC LIMIT 1",
            (str(ticker or "").upper().replace(".OL", ""),),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _record_with_market_context(result, name=None):
    outcome = _BASE_RECORD(result, name)
    if not outcome.get("emitted"):
        return outcome
    ticker = str((result or {}).get("ticker") or "").upper().replace(".OL", "")
    try:
        event = _latest_event(ticker)
        symbol, rows = _benchmark_rows()
        if event:
            _persist_market_context(event, symbol, rows)
    except Exception:
        pass
    return outcome


def _market_return_for_target(entry_close, target_date, rows):
    if entry_close is None or not target_date:
        return None
    target = _row_on_or_before(rows, target_date)
    if not target:
        return None
    try:
        start = float(entry_close)
        finish = float(target["close"])
    except (TypeError, ValueError):
        return None
    if start <= 0 or finish <= 0:
        return None
    return target, (finish / start - 1.0) * 100.0


def _settle_market_returns_for_ticker(ticker, rows=None):
    ticker = str(ticker or "").upper().replace(".OL", "")
    if not ticker:
        return 0
    if rows is None:
        _, rows = _benchmark_rows()
    conn = tracking.connect()
    try:
        pending = [dict(row) for row in conn.execute(
            "SELECT r.event_id,r.horizon_days,r.target_date,r.return_pct,c.benchmark_entry_close "
            "FROM opportunity_forward_returns r "
            "JOIN opportunity_events e ON e.id=r.event_id "
            "JOIN opportunity_market_context c ON c.event_id=e.id "
            "LEFT JOIN opportunity_market_returns m ON m.event_id=r.event_id AND m.horizon_days=r.horizon_days "
            "WHERE e.ticker=? AND r.return_pct IS NOT NULL AND m.event_id IS NULL",
            (ticker,),
        ).fetchall()]
        settled = 0
        for item in pending:
            result = _market_return_for_target(item.get("benchmark_entry_close"), item.get("target_date"), rows)
            if not result:
                continue
            target, benchmark_return = result
            excess = float(item["return_pct"]) - benchmark_return
            conn.execute(
                "INSERT INTO opportunity_market_returns(event_id,horizon_days,benchmark_target_date,benchmark_return_pct,excess_return_pct,settled_at) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(event_id,horizon_days) DO NOTHING",
                (
                    item["event_id"], item["horizon_days"], target["date"],
                    benchmark_return, excess, _now(),
                ),
            )
            settled += 1
        conn.commit()
        return settled
    finally:
        conn.close()


def _settle_with_market_returns(ticker, rows=None):
    count = _BASE_SETTLE(ticker, rows)
    try:
        _settle_market_returns_for_ticker(ticker)
    except Exception:
        pass
    return count


def _market_rows_for_report():
    conn = tracking.connect()
    try:
        rows = conn.execute(
            "SELECT r.event_id,r.horizon_days,r.return_pct,e.ticker,c.regime,m.benchmark_return_pct,m.excess_return_pct "
            "FROM opportunity_forward_returns r "
            "JOIN opportunity_events e ON e.id=r.event_id "
            "LEFT JOIN opportunity_market_context c ON c.event_id=e.id "
            "LEFT JOIN opportunity_market_returns m ON m.event_id=r.event_id AND m.horizon_days=r.horizon_days "
            "WHERE r.horizon_days IN (5,10,20) AND r.return_pct IS NOT NULL"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _regime_stats(rows, minimum_sample):
    rows = list(rows or [])
    total = len(rows)
    classified = [row for row in rows if row.get("regime")]
    counts = Counter(str(row.get("regime")) for row in classified)
    supported = sorted(regime for regime, count in counts.items() if count >= MIN_EVENTS_PER_REGIME)
    largest_count = max(counts.values(), default=0)
    largest_share = (largest_count / len(classified) * 100.0) if classified else 0.0
    checks = {
        "minimum_sample": total >= int(minimum_sample),
        "classified_sample": len(classified) >= int(minimum_sample),
        "supported_regimes": len(supported) >= MIN_SUPPORTED_REGIMES,
        "regime_concentration": largest_share <= MAX_SINGLE_REGIME_SHARE_PCT if classified else False,
    }
    if not checks["minimum_sample"] or not checks["classified_sample"]:
        status = "COLLECTING_DATA"
    elif all(checks.values()):
        status = "PASS"
    else:
        status = "REVIEW"
    return {
        "status": status,
        "observations": total,
        "classified_observations": len(classified),
        "coverage_pct": round(len(classified) / total * 100.0, 2) if total else 0.0,
        "regime_counts": dict(sorted(counts.items())),
        "supported_regimes": supported,
        "largest_regime": counts.most_common(1)[0][0] if counts else None,
        "largest_regime_share_pct": round(largest_share, 2),
        "checks": checks,
    }


def _alpha_stats(rows):
    values = []
    benchmark_values = []
    for row in rows or []:
        try:
            if row.get("excess_return_pct") is not None:
                values.append(float(row["excess_return_pct"]))
            if row.get("benchmark_return_pct") is not None:
                benchmark_values.append(float(row["benchmark_return_pct"]))
        except (TypeError, ValueError):
            continue
    n = len(values)
    return {
        "n": n,
        "mean_excess_return_pct": round(sum(values) / n, 3) if n else None,
        "median_excess_return_pct": round(float(median(values)), 3) if n else None,
        "positive_excess_rate_pct": round(sum(value > 0 for value in values) / n * 100.0, 2) if n else None,
        "mean_benchmark_return_pct": round(sum(benchmark_values) / len(benchmark_values), 3) if benchmark_values else None,
    }


def _schedule_backfill():
    global _BACKFILL_RUNNING
    with _BACKFILL_LOCK:
        if _BACKFILL_RUNNING:
            return False
        _BACKFILL_RUNNING = True

    def worker():
        global _BACKFILL_RUNNING
        try:
            symbol, rows = _benchmark_rows()
            conn = tracking.connect()
            try:
                events = [dict(row) for row in conn.execute(
                    "SELECT e.* FROM opportunity_events e LEFT JOIN opportunity_market_context c ON c.event_id=e.id "
                    "WHERE c.event_id IS NULL ORDER BY e.id"
                ).fetchall()]
                tickers = [str(row["ticker"]) for row in conn.execute(
                    "SELECT DISTINCT e.ticker FROM opportunity_forward_returns r "
                    "JOIN opportunity_events e ON e.id=r.event_id "
                    "LEFT JOIN opportunity_market_returns m ON m.event_id=r.event_id AND m.horizon_days=r.horizon_days "
                    "WHERE r.return_pct IS NOT NULL AND m.event_id IS NULL"
                ).fetchall()]
            finally:
                conn.close()
            for event in events:
                try:
                    _persist_market_context(event, symbol, rows)
                except Exception:
                    pass
            for ticker in tickers:
                try:
                    _settle_market_returns_for_ticker(ticker, rows)
                except Exception:
                    pass
        finally:
            with _BACKFILL_LOCK:
                _BACKFILL_RUNNING = False

    threading.Thread(target=worker, daemon=True, name="nordicsignal-opportunity-market-backfill").start()
    return True


def opportunity_performance(limit=100):
    report = _BASE_REPORT(limit)
    calibration = report.setdefault("calibration", {})
    minimum_sample = int(calibration.get("minimum_sample_size") or 20)
    previous_ready = bool(calibration.get("ready"))

    try:
        rows = _market_rows_for_report()
    except Exception:
        rows = []
    grouped = {horizon: [] for horizon in REQUIRED_HORIZONS}
    for row in rows:
        try:
            horizon = int(row.get("horizon_days") or 0)
        except (TypeError, ValueError):
            continue
        if horizon in grouped:
            grouped[horizon].append(row)

    regime_horizons = {
        str(horizon): _regime_stats(grouped[horizon], minimum_sample)
        for horizon in REQUIRED_HORIZONS
    }
    regime_ready = all(
        regime_horizons[str(horizon)]["status"] == "PASS"
        for horizon in REQUIRED_HORIZONS
    )
    alpha_horizons = {
        str(horizon): _alpha_stats(grouped[horizon])
        for horizon in REQUIRED_HORIZONS
    }
    positive_alpha_horizons = [
        horizon for horizon in REQUIRED_HORIZONS
        if (alpha_horizons[str(horizon)].get("median_excess_return_pct") is not None
            and float(alpha_horizons[str(horizon)]["median_excess_return_pct"]) > 0)
    ]
    alpha_consistent = len(positive_alpha_horizons) >= MIN_POSITIVE_ALPHA_HORIZONS

    report["market_regime_gate"] = {
        "status": "PASS" if regime_ready else ("REVIEW" if previous_ready else "COLLECTING_DATA"),
        "ready": regime_ready,
        "benchmark": BENCHMARK_ID,
        "horizons": regime_horizons,
        "criteria": {
            "required_horizons": list(REQUIRED_HORIZONS),
            "minimum_supported_regimes": MIN_SUPPORTED_REGIMES,
            "minimum_observations_per_supported_regime": MIN_EVENTS_PER_REGIME,
            "maximum_single_regime_share_pct": MAX_SINGLE_REGIME_SHARE_PCT,
            "regime_definition": {
                "RISK_ON": f"prior OSEBX close above 50d MA and 20d return >= +{REGIME_RETURN_THRESHOLD_PCT:.0f}%",
                "RISK_OFF": f"prior OSEBX close below 50d MA and 20d return <= -{REGIME_RETURN_THRESHOLD_PCT:.0f}%",
                "NEUTRAL": "all other conditions",
            },
            "lookahead_policy": "regime uses benchmark trading data strictly before the Opportunity event market date",
        },
        "meaning": (
            "The settled sample spans sufficiently different Oslo market regimes."
            if regime_ready
            else "Do not treat the sample as regime-independent yet; too much evidence may come from one broad market environment."
        ),
        "automatic_threshold_changes": False,
    }
    report["market_adjusted"] = {
        "benchmark": BENCHMARK_ID,
        "method": "stock_forward_return_minus_OSEBX_close_to_close_return",
        "horizons": alpha_horizons,
        "positive_median_excess_horizons": positive_alpha_horizons,
        "positive_median_excess_consistent": alpha_consistent,
        "minimum_positive_horizons": MIN_POSITIVE_ALPHA_HORIZONS,
        "meaning": "Positive excess return means the Opportunity observation outperformed OSEBX over the same close-to-close evaluation window.",
    }

    calibration["pre_regime_ready"] = previous_ready
    calibration["market_regime_ready"] = regime_ready
    calibration["ready"] = previous_ready and regime_ready
    calibration["rule"] = (
        "Do not tune Opportunity thresholds until sample size, ticker/sector independence and "
        "market-regime diversity all pass across 5d, 10d and 20d."
    )

    quality = report.get("quality_gate") or {}
    if quality:
        checks = quality.setdefault("checks", {})
        checks["market_regime_diversity"] = regime_ready
        checks["positive_market_adjusted_median"] = alpha_consistent
        quality["positive_alpha_horizons"] = positive_alpha_horizons
        quality["criteria"] = dict(quality.get("criteria") or {})
        quality["criteria"]["minimum_positive_market_adjusted_horizons"] = MIN_POSITIVE_ALPHA_HORIZONS
        if quality.get("status") == "PASS_CANDIDATE" and not (regime_ready and alpha_consistent):
            quality["status"] = "REVIEW" if previous_ready else "COLLECTING_DATA"
            quality["quality_pass_candidate"] = False
            quality["meaning"] = (
                "Directional checks may pass, but market-regime diversity or OSEBX-adjusted median performance is not yet strong enough for a pass candidate."
            )
        report["quality_gate"] = quality

    # Backfill missing context/benchmark returns without making this API request wait
    # on Yahoo. This also repairs events created before this runtime was deployed.
    try:
        _schedule_backfill()
    except Exception:
        pass

    report["policy"] = "measurement_only_manual_calibration_review_with_independence_and_market_regime_gates"
    return report


def install():
    _ensure_schema()
    tracking.record_opportunity = _record_with_market_context
    tracking.settle_forward_returns = _settle_with_market_returns
    tracking.opportunity_performance = opportunity_performance
    try:
        _schedule_backfill()
    except Exception:
        pass


install()
