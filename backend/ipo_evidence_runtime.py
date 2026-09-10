"""Post-listing outcome evidence for official Oslo IPO/listing observations.

Returns are measured from the first available listed close, benchmarked against OSEBX
on the same trading-day horizons. If an archived verified offer price exists, the
listing-day close vs offer price is reported separately rather than mixed into the
benchmark-relative close-to-close series.
"""
from datetime import datetime, timedelta, timezone
from statistics import mean, median

import extra_api
from database import connect
from providers import YahooProvider
import ipo_listing_registry_runtime as registry
import portfolio_benchmark_runtime as benchmarks

MODEL_VERSION = "ipo_evidence_v1"
BENCHMARK_ID = "OSEBX"
HORIZONS = (1, 5, 20, 60)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _ensure_schema():
    conn = connect()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS ipo_listing_outcomes (
          listing_id TEXT NOT NULL,
          horizon_days INTEGER NOT NULL,
          benchmark_id TEXT NOT NULL,
          entry_date TEXT NOT NULL,
          exit_date TEXT NOT NULL,
          entry_close REAL NOT NULL,
          exit_close REAL NOT NULL,
          return_pct REAL NOT NULL,
          benchmark_return_pct REAL,
          excess_return_pct REAL,
          max_drawdown_pct REAL,
          max_runup_pct REAL,
          first_day_vs_offer_pct REAL,
          settled_at TEXT NOT NULL,
          PRIMARY KEY(listing_id,horizon_days,benchmark_id)
        );
        CREATE INDEX IF NOT EXISTS idx_ipo_listing_outcomes_listing ON ipo_listing_outcomes(listing_id,horizon_days);
        """)
        conn.commit()
    finally:
        conn.close()


def _daily_rows(provider, symbol, start_date, calendar_days=180):
    start = datetime.fromisoformat(str(start_date)).replace(tzinfo=timezone.utc) - timedelta(days=5)
    end = min(datetime.now(timezone.utc) + timedelta(days=1), start + timedelta(days=max(120, int(calendar_days))))
    data = provider._get(
        f"{provider.BASE}/v8/finance/chart/{symbol}",
        {"period1": int(start.timestamp()), "period2": int(end.timestamp()), "interval": "1d", "events": "div,splits"},
    )
    result = ((data.get("chart") or {}).get("result") or [])
    if not result:
        return []
    result = result[0]
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    rows = []
    for i, ts in enumerate(timestamps):
        if i >= len(closes) or closes[i] is None:
            continue
        rows.append({"date": datetime.fromtimestamp(int(ts), timezone.utc).date().isoformat(), "close": float(closes[i])})
    return rows


def _start_index(rows, listing_date):
    return next((i for i, row in enumerate(rows or []) if str(row.get("date") or "") >= str(listing_date or "")), None)


def _return(start, end):
    start = float(start); end = float(end)
    return (end / start - 1.0) * 100.0 if start > 0 else None


def _measure(rows, start_idx, horizon):
    if start_idx is None or start_idx + int(horizon) >= len(rows):
        return None
    end_idx = start_idx + int(horizon)
    entry = float(rows[start_idx]["close"])
    if entry <= 0:
        return None
    path = [_return(entry, rows[i]["close"]) for i in range(start_idx, end_idx + 1)]
    path = [x for x in path if x is not None]
    return {
        "entry_date": rows[start_idx]["date"],
        "exit_date": rows[end_idx]["date"],
        "entry_close": entry,
        "exit_close": float(rows[end_idx]["close"]),
        "return_pct": _return(entry, rows[end_idx]["close"]),
        "max_drawdown_pct": min(path) if path else None,
        "max_runup_pct": max(path) if path else None,
    }


def _benchmark_measure(rows, entry_date, horizon):
    idx = _start_index(rows, entry_date)
    measured = _measure(rows, idx, horizon)
    return measured.get("return_pct") if measured else None


def _offer_price(listing):
    ticker = str((listing or {}).get("ticker") or "").strip().upper()
    company = str((listing or {}).get("company") or "").strip()
    conn = connect()
    try:
        row = None
        if ticker:
            row = conn.execute(
                "SELECT offer_price_nok FROM ipo_candidates WHERE ticker=? AND offer_price_nok IS NOT NULL ORDER BY first_seen_at DESC LIMIT 1",
                (ticker,),
            ).fetchone()
        if not row and company:
            row = conn.execute(
                "SELECT offer_price_nok FROM ipo_candidates WHERE lower(company)=lower(?) AND offer_price_nok IS NOT NULL ORDER BY first_seen_at DESC LIMIT 1",
                (company,),
            ).fetchone()
        value = row["offer_price_nok"] if row else None
        return float(value) if isinstance(value, (int, float)) and float(value) > 0 else None
    except Exception:
        return None
    finally:
        conn.close()


def settle_outcomes(provider=None, benchmark_rows=None):
    _ensure_schema()
    provider = provider or YahooProvider()
    rows = registry.listings(limit=500)
    if not rows:
        return 0
    settled = 0
    bench_cache = {}
    for listing in rows:
        ticker = str(listing.get("ticker") or "").strip().upper()
        listing_date = listing.get("listing_date")
        if not ticker or not listing_date:
            continue
        try:
            stock = _daily_rows(provider, provider.symbol(ticker), listing_date)
        except Exception:
            continue
        stock_idx = _start_index(stock, listing_date)
        if stock_idx is None:
            continue
        entry_date = stock[stock_idx]["date"]
        try:
            if benchmark_rows is not None:
                bench = benchmark_rows
            elif listing_date in bench_cache:
                bench = bench_cache[listing_date]
            else:
                definition = benchmarks.BENCHMARKS[BENCHMARK_ID]
                bench = []
                for symbol in definition["symbols"]:
                    try:
                        bench = _daily_rows(provider, symbol, listing_date)
                        if bench:
                            break
                    except Exception:
                        continue
                bench_cache[listing_date] = bench
        except Exception:
            bench = []
        offer = _offer_price(listing)
        first_day_vs_offer = _return(offer, stock[stock_idx]["close"]) if offer else None
        conn = connect()
        try:
            for horizon in HORIZONS:
                own = _measure(stock, stock_idx, horizon)
                if not own:
                    continue
                exists = conn.execute(
                    "SELECT listing_id FROM ipo_listing_outcomes WHERE listing_id=? AND horizon_days=? AND benchmark_id=?",
                    (listing["listing_id"], horizon, BENCHMARK_ID),
                ).fetchone()
                if exists:
                    continue
                bench_ret = _benchmark_measure(bench, entry_date, horizon) if bench else None
                excess = own["return_pct"] - bench_ret if bench_ret is not None else None
                conn.execute(
                    "INSERT INTO ipo_listing_outcomes(listing_id,horizon_days,benchmark_id,entry_date,exit_date,entry_close,exit_close,return_pct,benchmark_return_pct,excess_return_pct,max_drawdown_pct,max_runup_pct,first_day_vs_offer_pct,settled_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (listing["listing_id"], horizon, BENCHMARK_ID, own["entry_date"], own["exit_date"], own["entry_close"], own["exit_close"], own["return_pct"], bench_ret, excess, own["max_drawdown_pct"], own["max_runup_pct"], first_day_vs_offer, _now()),
                )
                settled += 1
            conn.commit()
        finally:
            conn.close()
    return settled


def _maturity(n):
    return "insufficient" if n < 20 else "early" if n < 50 else "useful_history"


def _stats(values):
    values = [float(x) for x in values if isinstance(x, (int, float))]
    return {
        "n": len(values),
        "mean_pct": round(mean(values), 3) if values else None,
        "median_pct": round(median(values), 3) if values else None,
        "positive_rate_pct": round(sum(1 for x in values if x > 0) / len(values) * 100.0, 1) if values else None,
    }


def build_evidence(refresh=False, provider=None):
    sync = None
    settled = 0
    if refresh:
        try:
            sync = registry.sync_listings()
        except Exception:
            sync = {"status": "unavailable", "inserted": 0}
        try:
            settled = settle_outcomes(provider=provider)
        except Exception:
            settled = 0
    _ensure_schema()
    conn = connect()
    try:
        outcomes = [dict(x) for x in conn.execute(
            "SELECT o.*,l.company,l.ticker,l.market,l.listing_date FROM ipo_listing_outcomes o JOIN ipo_listings l ON l.listing_id=o.listing_id ORDER BY l.listing_date,o.horizon_days"
        ).fetchall()]
    finally:
        conn.close()
    listing_ids = sorted(set(x["listing_id"] for x in outcomes))
    horizons = {}
    for horizon in HORIZONS:
        group = [x for x in outcomes if int(x["horizon_days"]) == horizon]
        returns = [x.get("return_pct") for x in group]
        excess = [x.get("excess_return_pct") for x in group]
        horizons[str(horizon)] = {
            "return": _stats(returns),
            "excess_vs_osebx": _stats(excess),
            "maturity": _maturity(len([x for x in returns if isinstance(x, (int, float))])),
        }
    by_market = []
    markets = sorted(set(str(x.get("market") or "unknown") for x in outcomes))
    for market in markets:
        group = [x for x in outcomes if str(x.get("market") or "unknown") == market and int(x["horizon_days"]) == 20]
        by_market.append({"market": market, "horizon_days": 20, "excess_vs_osebx": _stats([x.get("excess_return_pct") for x in group]), "maturity": _maturity(len(group))})
    return {
        "status": "collecting" if len(listing_ids) < 20 else "evidence_building",
        "model": MODEL_VERSION,
        "sample_count": len(listing_ids),
        "maturity": _maturity(len(listing_ids)),
        "benchmark": BENCHMARK_ID,
        "horizons": horizons,
        "by_market_20d": by_market,
        "settled_now": settled,
        "sync": sync,
        "method": "Official Euronext listing date; first listed close as entry; 1/5/20/60 trading-day close-to-close outcomes; OSEBX on the same dates. Offer-price first-day return is stored separately when verified.",
        "policy": "Measurement only. IPO evidence does not change NordicSignal scores, signals or thresholds.",
        "generated_at": _now(),
    }


def install():
    if getattr(extra_api, "_ipo_evidence_runtime_v1", False):
        return
    original_install = extra_api.install
    def patched_install(app):
        original_install(app)
        _ensure_schema()
        @app.get("/api/ipo-radar/evidence")
        def ipo_evidence(refresh: bool = False):
            return build_evidence(refresh=refresh)
    extra_api.install = patched_install
    extra_api._ipo_evidence_runtime_v1 = True

install()
