"""Historical walk-forward backtest for Trend/Reversal Engine v2.

Uses only information available up to each signal date. Designed for CI diagnostics,
not production scoring. Results are written to reversal_backtest.json.
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone

from providers import YahooProvider
from trend_reversal_runtime import calculate_reversal

TICKERS = [
    "LSG", "MPCC", "ELO", "PEXIP", "XPLRA", "EQNR", "DNB", "NHY", "YAR", "MOWI",
    "SALM", "GJF", "TEL", "ORK", "TOM", "KOG", "NAS", "AKRBP", "AKSO", "SUBC",
    "BWLPG", "HAUTO", "CMBTO", "VAR",
]
HORIZONS = (5, 10, 20, 60)
MIN_HISTORY = 35
INDICATOR_WINDOW = 180
COOLDOWN = 10


def fetch_daily(provider, ticker):
    symbol = provider.symbol(ticker)
    data = provider._get(
        f"{provider.BASE}/v8/finance/chart/{symbol}",
        {"range": "5y", "interval": "1d", "events": "div,splits"},
    )
    result = data["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    rows = []
    for i, ts in enumerate(timestamps):
        if i >= len(closes) or closes[i] is None:
            continue
        rows.append({
            "timestamp": ts,
            "date": datetime.fromtimestamp(ts, timezone.utc).date().isoformat(),
            "close": float(closes[i]),
            "volume": volumes[i] if i < len(volumes) else None,
        })
    return rows


def pct(a, b):
    return ((b / a) - 1.0) * 100.0 if a else None


def summarize(values):
    values = [float(x) for x in values if x is not None]
    if not values:
        return {"n": 0, "mean_pct": None, "median_pct": None, "positive_rate_pct": None}
    return {
        "n": len(values),
        "mean_pct": round(statistics.fmean(values), 3),
        "median_pct": round(statistics.median(values), 3),
        "positive_rate_pct": round(sum(x > 0 for x in values) / len(values) * 100.0, 2),
    }


def backtest_ticker(ticker, rows):
    events = []
    baseline = {h: [] for h in HORIZONS}
    last_event_i = -10_000
    prev_score = None

    for i in range(MIN_HISTORY - 1, len(rows)):
        for h in HORIZONS:
            if i + h < len(rows):
                baseline[h].append(pct(rows[i]["close"], rows[i + h]["close"]))

        start = max(0, i - INDICATOR_WINDOW + 1)
        result = calculate_reversal(rows[start : i + 1])
        score = result.get("score")
        if score is None:
            prev_score = score
            continue

        crossed_55 = score >= 55 and (prev_score is None or prev_score < 55)
        crossed_75 = score >= 75 and (prev_score is None or prev_score < 75)
        if (crossed_55 or crossed_75) and i - last_event_i >= COOLDOWN:
            forward = {}
            for h in HORIZONS:
                forward[str(h)] = pct(rows[i]["close"], rows[i + h]["close"]) if i + h < len(rows) else None
            events.append({
                "ticker": ticker,
                "date": rows[i]["date"],
                "close": rows[i]["close"],
                "score": score,
                "regime": result.get("regime"),
                "threshold": 75 if crossed_75 else 55,
                "metrics": result.get("metrics") or {},
                "forward_return_pct": forward,
            })
            last_event_i = i
        prev_score = score

    return events, baseline


def main():
    provider = YahooProvider()
    all_events = []
    baseline = {h: [] for h in HORIZONS}
    coverage = {}
    errors = {}

    for ticker in TICKERS:
        try:
            rows = fetch_daily(provider, ticker)
            coverage[ticker] = len(rows)
            events, ticker_baseline = backtest_ticker(ticker, rows)
            all_events.extend(events)
            for h in HORIZONS:
                baseline[h].extend(ticker_baseline[h])
            print(f"{ticker}: {len(rows)} daily rows, {len(events)} reversal events")
        except Exception as exc:
            errors[ticker] = str(exc)
            print(f"{ticker}: ERROR {exc}")

    by_threshold = {}
    for threshold in (55, 75):
        selected = [e for e in all_events if e["threshold"] >= threshold]
        horizon_stats = {}
        for h in HORIZONS:
            event_values = [e["forward_return_pct"][str(h)] for e in selected]
            event_stats = summarize(event_values)
            baseline_stats = summarize(baseline[h])
            excess = None
            if event_stats["mean_pct"] is not None and baseline_stats["mean_pct"] is not None:
                excess = round(event_stats["mean_pct"] - baseline_stats["mean_pct"], 3)
            horizon_stats[str(h)] = {
                "signal": event_stats,
                "baseline_all_dates": baseline_stats,
                "mean_excess_pct_points": excess,
            }
        by_threshold[str(threshold)] = {"events": len(selected), "horizons": horizon_stats}

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine_version": "2026-08-29-v2",
        "method": {
            "universe": "current NordicSignal Oslo universe",
            "lookback": "5y daily Yahoo chart data",
            "indicator_window_trading_days": INDICATOR_WINDOW,
            "entry": "first cross above 55 or 75 after being below threshold",
            "cooldown_trading_days": COOLDOWN,
            "horizons_trading_days": list(HORIZONS),
            "lookahead": "none in signal calculation",
            "baseline": "all eligible stock-days in the same downloaded history",
            "limitations": [
                "current-universe survivorship bias",
                "no transaction costs/slippage",
                "dividends are not included in close-to-close returns",
                "insider-cluster confluence is not included in this first trend-only backtest",
            ],
        },
        "coverage_rows": coverage,
        "errors": errors,
        "event_count": len(all_events),
        "results": by_threshold,
        "events": all_events,
    }

    with open("reversal_backtest.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n=== REVERSAL BACKTEST SUMMARY ===")
    print(f"events: {len(all_events)} | tickers with errors: {len(errors)}")
    for threshold, block in by_threshold.items():
        print(f"threshold >= {threshold}: {block['events']} events")
        for h in HORIZONS:
            x = block["horizons"][str(h)]
            s = x["signal"]
            print(
                f"  {h:>2}d: n={s['n']} mean={s['mean_pct']}% median={s['median_pct']}% "
                f"positive={s['positive_rate_pct']}% excess={x['mean_excess_pct_points']}pp"
            )

    if len(coverage) < max(10, len(TICKERS) // 2):
        raise SystemExit("Backtest data coverage too low to verify the engine")
    if not all_events:
        raise SystemExit("Backtest produced no reversal events")


if __name__ == "__main__":
    main()
