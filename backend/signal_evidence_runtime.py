"""Historical evidence for NordicSignal trend/activity events.

This module backtests the *same transparent event rules* used by Latest Signals.
It deliberately reports sample size and directional hit-rate instead of claiming
predictive certainty. Results are cached in Postgres/SQLite for 24 hours because
historical daily data changes slowly and Yahoo requests are relatively expensive.
"""
from datetime import datetime, timezone
import json
from statistics import mean, median

from fastapi import HTTPException

import extra_api
from database import connect
from providers import YahooProvider
import signal_events_runtime as signals

MODEL_VERSION = "trend_activity_v1"
CACHE_SECONDS = 24 * 60 * 60
HORIZONS = (5, 20, 60)
ALLOWED_YEARS = {1, 2, 5}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _ensure_schema():
    conn = connect()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS signal_evidence_cache (
          cache_key TEXT PRIMARY KEY,
          payload TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        """)
        conn.commit()
    finally:
        conn.close()


def _cache_key(ticker, years):
    return f"{MODEL_VERSION}:{str(ticker).upper()}:{int(years)}y"


def _cache_get(key):
    conn = connect()
    try:
        row = conn.execute("SELECT payload,updated_at FROM signal_evidence_cache WHERE cache_key=?", (key,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    updated = _parse_time(row["updated_at"])
    if not updated or (datetime.now(timezone.utc) - updated).total_seconds() > CACHE_SECONDS:
        return None
    try:
        payload = json.loads(row["payload"])
    except Exception:
        return None
    payload["cache"] = {"state": "fresh", "updated_at": row["updated_at"]}
    return payload


def _cache_put(key, payload):
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    now = _now()
    conn = connect()
    try:
        exists = conn.execute("SELECT cache_key FROM signal_evidence_cache WHERE cache_key=?", (key,)).fetchone()
        if exists:
            conn.execute("UPDATE signal_evidence_cache SET payload=?,updated_at=? WHERE cache_key=?", (encoded, now, key))
        else:
            conn.execute("INSERT INTO signal_evidence_cache(payload,updated_at,cache_key) VALUES(?,?,?)", (encoded, now, key))
        conn.commit()
    finally:
        conn.close()


def _history(provider, ticker, years):
    symbol = provider.symbol(ticker)
    data = provider._get(
        f"{provider.BASE}/v8/finance/chart/{symbol}",
        {"range": f"{years}y", "interval": "1d", "events": "div,splits"},
    )
    result = (((data.get("chart") or {}).get("result") or [None])[0] or {})
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    rows = []
    for i, ts in enumerate(timestamps):
        if i >= len(closes) or closes[i] is None:
            continue
        close = float(closes[i])
        if close <= 0:
            continue
        volume = volumes[i] if i < len(volumes) else None
        rows.append({
            "timestamp": int(ts),
            "date": datetime.fromtimestamp(int(ts), timezone.utc).isoformat(),
            "close": close,
            "volume": volume,
        })
    if len(rows) < 90:
        raise HTTPException(502, detail=f"Insufficient daily history for {ticker}")
    return rows


def _forward_return(rows, index, horizon):
    target = index + int(horizon)
    if target >= len(rows):
        return None
    start = float(rows[index]["close"])
    end = float(rows[target]["close"])
    if start <= 0:
        return None
    return (end / start - 1.0) * 100.0


def backtest_history(rows):
    """Replay the production event detector through historical daily observations."""
    rows = sorted(list(rows or []), key=lambda x: (x.get("timestamp") or 0, str(x.get("date") or "")))
    samples = []
    previous = None
    for i in range(24, len(rows)):
        window = rows[max(0, i - 80): i + 1]
        metrics = signals.analyze_trend_activity(window)
        if not metrics.get("eligible"):
            continue
        candidate = signals._trend_event_candidate(metrics, previous)
        previous = {
            "trend_state": metrics.get("trend_state") or "neutral",
            "activity_state": metrics.get("activity_state") or "normal",
        }
        if not candidate:
            continue
        forward = {str(h): _forward_return(rows, i, h) for h in HORIZONS}
        samples.append({
            "date": str(metrics.get("observed_at") or rows[i].get("date") or "")[:10],
            "kind": candidate.get("kind"),
            "direction": candidate.get("direction"),
            "signal": candidate.get("signal"),
            "event": candidate.get("event"),
            "detail": candidate.get("detail"),
            "price": rows[i].get("close"),
            "volume_ratio": metrics.get("volume_ratio"),
            "recent_volume_ratio": metrics.get("recent_volume_ratio"),
            "forward_return_pct": forward,
        })
    return samples


def _horizon_stats(samples, horizon):
    key = str(horizon)
    usable = [x for x in samples if x.get("forward_return_pct", {}).get(key) is not None]
    values = [float(x["forward_return_pct"][key]) for x in usable]
    directional = [
        (float(x["forward_return_pct"][key]) > 0 if x.get("direction") == "up" else
         float(x["forward_return_pct"][key]) < 0 if x.get("direction") == "down" else None)
        for x in usable
    ]
    directional = [x for x in directional if x is not None]
    return {
        "n": len(values),
        "mean_return_pct": round(mean(values), 3) if values else None,
        "median_return_pct": round(median(values), 3) if values else None,
        "directional_hit_rate_pct": round(sum(1 for x in directional if x) / len(directional) * 100.0, 1) if directional else None,
        "directional_n": len(directional),
    }


def summarize_samples(samples):
    samples = list(samples or [])
    groups = {}
    for item in samples:
        key = item.get("event") or item.get("kind") or "Signal"
        groups.setdefault(key, []).append(item)

    def summarize(group):
        return {
            "sample_count": len(group),
            "horizons": {str(h): _horizon_stats(group, h) for h in HORIZONS},
        }

    total = len(samples)
    maturity = "insufficient" if total < 20 else "early" if total < 50 else "useful_history"
    return {
        "maturity": maturity,
        "sample_count": total,
        "overall": summarize(samples),
        "by_event": [
            {"event": name, **summarize(group)}
            for name, group in sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[0]))
        ],
    }


def signal_evidence(ticker, years=2, refresh=False):
    symbol = str(ticker or "").strip().upper().replace(".OL", "")
    if not symbol or len(symbol) > 16 or not all(ch.isalnum() or ch in ".-" for ch in symbol):
        raise HTTPException(400, detail="Invalid ticker")
    try:
        years = int(years)
    except Exception:
        years = 2
    if years not in ALLOWED_YEARS:
        raise HTTPException(400, detail="years must be 1, 2 or 5")
    key = _cache_key(symbol, years)
    if not refresh:
        cached = _cache_get(key)
        if cached:
            return cached

    provider = YahooProvider()
    rows = _history(provider, symbol, years)
    samples = backtest_history(rows)
    summary = summarize_samples(samples)
    payload = {
        "ticker": symbol,
        "model": MODEL_VERSION,
        "period_years": years,
        "history_points": len(rows),
        "source": "Yahoo Finance daily price/volume history",
        "method": "Replay of the same trend/activity rules used by Latest Signals; forward returns measured from signal-day close.",
        "limitations": [
            "Historical replay is not proof of future performance.",
            "No transaction costs, slippage, tax or intraday execution are included.",
            "Small sample sizes must not be treated as statistically reliable.",
            "A signal is evaluated from end-of-day data and therefore is not an intraday prediction.",
        ],
        "summary": summary,
        "recent_samples": list(reversed(samples[-12:])),
        "generated_at": _now(),
    }
    _cache_put(key, payload)
    payload["cache"] = {"state": "refreshed", "updated_at": payload["generated_at"]}
    return payload


def install():
    if getattr(extra_api, "_signal_evidence_runtime_installed", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)
        _ensure_schema()

        @app.get("/api/signal-evidence/{ticker}")
        def signal_evidence_route(ticker: str, years: int = 2, refresh: bool = False):
            return signal_evidence(ticker, years=years, refresh=refresh)

    extra_api.install = patched_install
    extra_api._signal_evidence_runtime_installed = True


install()
