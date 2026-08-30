"""Historical insider-cluster + reversal confluence backtest.

Diagnostic only. Uses official Euronext primary-insider disclosures and Yahoo daily
prices. A cluster is actionable only from a verified disclosure publication date;
trade dates are never used as signal-availability dates. No production score changes.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import insider_market_v2_runtime as market
import insider_runtime
from insider_signal_v2_runtime import analyze as analyze_insider
from providers import YahooProvider, NordicRegulatoryProvider, _TextParser
from trend_reversal_runtime import calculate_reversal

TICKERS = {
    "LSG","MPCC","ELO","PEXIP","XPLRA","EQNR","DNB","NHY","YAR","MOWI","SALM","GJF",
    "TEL","ORK","TOM","KOG","NAS","AKRBP","AKSO","SUBC","BWLPG","HAUTO","CMBTO","VAR"
}
HORIZONS = (5, 10, 20, 60)
DAYS = 730
CLUSTER_WINDOW_DAYS = 14
MAX_TOPIC_DETAIL_RELEASES = 320
COMPANY_PAGES = 12


def _day(value):
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except Exception:
        return None


def _actor(row):
    return str(
        row.get("person") or row.get("related_primary_insider") or row.get("insider")
        or row.get("entity") or row.get("actor") or ""
    ).strip().lower()


def _is_buy(row):
    return str(row.get("direction") or row.get("transaction_type") or row.get("activity_type") or "").lower() in {"buy","purchase","acquisition","acquire"}


def _normalise_trade(row, ticker, source_url):
    out = dict(row or {})
    out["ticker"] = ticker
    direction = str(out.get("direction") or out.get("transaction_type") or "").lower()
    if direction:
        out["transaction_type"] = direction
    out["url"] = out.get("url") or source_url
    return out


def collect_company_archive(days):
    """Collect additional rows for diagnostics only.

    Legacy company-page parsing often lacks a machine-verifiable publication timestamp.
    Such rows may help assess parser coverage, but build_cluster_events deliberately
    excludes them from return attribution unless published_at exists.
    """
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)
    provider = NordicRegulatoryProvider()
    all_trades = []
    seen_urls = set()
    stats = {}
    keywords = ("insider","primary","primær","pdmr","mandatory notification")

    for ticker in sorted(TICKERS):
        links = []
        empty_pages = 0
        for page in range(COMPANY_PAGES):
            try:
                html = provider._html(provider.EURONEXT_NEWS,{"keys":ticker,"page":page})
                parser = _TextParser(); parser.feed(html)
            except Exception:
                continue
            page_links = []
            for href,text in parser.links:
                if not href:
                    continue
                low = str(text or "").lower()
                if any(k in low for k in keywords):
                    full = href if href.startswith("http") else "https://live.euronext.com" + href
                    if full not in seen_urls:
                        page_links.append((full,text)); seen_urls.add(full)
            if not page_links:
                empty_pages += 1
                if empty_pages >= 2:
                    break
            else:
                empty_pages = 0
                links.extend(page_links)

        parsed_count = 0
        for url,title in links:
            try:
                html = provider._html(url)
                p = _TextParser(); p.feed(html); body = p.text
                raw_rows = insider_runtime.parse_trades(
                    body,ticker,title or "Primary insider transaction",
                    "Euronext Oslo Børs Newspoint",url,
                )
            except Exception:
                continue
            for raw in raw_rows or []:
                row = _normalise_trade(raw,ticker,url)
                trade_day = _day(row.get("trade_date") or row.get("date"))
                if trade_day and trade_day < cutoff:
                    continue
                meaningful = _is_buy(row) or str(row.get("direction") or "").lower() == "sell" or row.get("shares") is not None
                if meaningful:
                    all_trades.append(row); parsed_count += 1
        stats[ticker] = {"release_links":len(links),"parsed_trades":parsed_count}
    return all_trades, stats


def fetch_prices(provider, ticker):
    symbol = provider.symbol(ticker)
    data = provider._get(f"{provider.BASE}/v8/finance/chart/{symbol}",{"range":"5y","interval":"1d","events":"div,splits"})
    result = data["chart"]["result"][0]
    ts = result.get("timestamp") or []
    quote = (result.get("indicators",{}).get("quote") or [{}])[0]
    closes = quote.get("close") or []; volumes = quote.get("volume") or []
    rows = []
    for i,t in enumerate(ts):
        if i >= len(closes) or closes[i] is None:
            continue
        rows.append({
            "date":datetime.fromtimestamp(t,timezone.utc).date().isoformat(),
            "close":float(closes[i]),
            "volume":volumes[i] if i < len(volumes) else None,
        })
    return rows


def last_index_before(rows, target):
    eligible = [(i,_day(r["date"])) for i,r in enumerate(rows) if _day(r["date"]) and _day(r["date"]) < target]
    return eligible[-1][0] if eligible else None


def first_index_after(rows, target):
    for i,row in enumerate(rows):
        day = _day(row.get("date"))
        if day and day > target:
            return i
    return None


def pct(a,b):
    return ((b/a)-1.0)*100.0 if a else None


def summarize(values):
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return {"n":0,"mean_pct":None,"median_pct":None,"positive_rate_pct":None}
    return {
        "n":len(vals),
        "mean_pct":round(statistics.fmean(vals),3),
        "median_pct":round(statistics.median(vals),3),
        "positive_rate_pct":round(sum(v>0 for v in vals)/len(vals)*100,2),
    }


def dedup_trades(trades):
    out = []; seen = set()
    for row in trades:
        key = (
            str(row.get("ticker") or "").upper(),
            str(row.get("published_at") or "")[:19],
            str(row.get("trade_date") or row.get("date") or "")[:10],
            _actor(row),
            str(row.get("direction") or row.get("transaction_type") or "").lower(),
            row.get("shares"), row.get("price"),
        )
        if key in seen:
            continue
        seen.add(key); out.append(row)
    return out


def build_cluster_events(trades):
    grouped = defaultdict(list)
    excluded_without_publication = 0
    for row in trades:
        ticker = str(row.get("ticker") or "").upper()
        publication_day = _day(row.get("published_at"))
        if ticker not in TICKERS or not _is_buy(row):
            continue
        if not publication_day:
            excluded_without_publication += 1
            continue
        grouped[ticker].append((publication_day,row))

    events = []
    for ticker,items in grouped.items():
        items.sort(key=lambda x:x[0]); last_event = None
        for anchor,_ in items:
            window = [dict(r) for d,r in items if timedelta(0) <= anchor-d <= timedelta(days=CLUSTER_WINDOW_DAYS)]
            actors = {_actor(r) for r in window if _actor(r)}
            if len(actors) < 2:
                continue
            if last_event and (anchor-last_event).days < CLUSTER_WINDOW_DAYS:
                continue
            enriched = analyze_insider({"items":window},window_days=CLUSTER_WINDOW_DAYS)["insider_signal_v2"]
            events.append({
                "ticker":ticker,
                "publication_date":anchor.isoformat(),
                "actors":len(actors),
                "insider":enriched,
            })
            last_event = anchor
    return events, excluded_without_publication


def main():
    market.MAX_EURONEXT_PAGES = 40
    announcements,meta = market._announcements(DAYS)
    relevant = [a for a in announcements if str(a.get("ticker") or "").upper() in TICKERS]
    topic_trades = []; detail_errors = []
    for ann in relevant[:MAX_TOPIC_DETAIL_RELEASES]:
        try:
            rows,_ = market._euronext_ajax_rows(ann,allow_network=True)
            topic_trades.extend(rows or [])
        except Exception as exc:
            detail_errors.append({"node_id":ann.get("node_id"),"error":str(exc)})

    archive_trades,archive_stats = collect_company_archive(DAYS)
    trades = dedup_trades(topic_trades + archive_trades)
    clusters,excluded_without_publication = build_cluster_events(trades)

    provider = YahooProvider(); price_cache = {}; evaluated = []
    for event in clusters:
        ticker = event["ticker"]
        if ticker not in price_cache:
            try:
                price_cache[ticker] = fetch_prices(provider,ticker)
            except Exception:
                price_cache[ticker] = []
        rows = price_cache[ticker]
        publication_day = _day(event["publication_date"])
        signal_idx = last_index_before(rows,publication_day)
        entry_idx = first_index_after(rows,publication_day)
        if signal_idx is None or signal_idx < 35 or entry_idx is None:
            continue

        # Reversal evidence uses only completed daily bars strictly before disclosure.
        reversal = calculate_reversal(rows[max(0,signal_idx-179):signal_idx+1])
        entry_price = rows[entry_idx]["close"]
        fwd = {
            str(h): pct(entry_price,rows[entry_idx+h]["close"]) if entry_idx+h < len(rows) else None
            for h in HORIZONS
        }
        vr = (reversal.get("metrics") or {}).get("volume_ratio")
        evaluated.append({
            **event,
            "signal_data_through":rows[signal_idx]["date"],
            "entry_date":rows[entry_idx]["date"],
            "entry_close":entry_price,
            "reversal":reversal,
            "forward_return_pct":fwd,
            "confluence_70":bool((reversal.get("score") or 0) >= 70),
            "confluence_75":bool((reversal.get("score") or 0) >= 75),
            "confluence_75_vol15":bool((reversal.get("score") or 0) >= 75 and (vr or 0) >= 1.5),
        })

    cohorts = {
        "cluster_all":evaluated,
        "cluster_strong":[e for e in evaluated if (e["insider"] or {}).get("label") == "STRONG"],
        "cluster_plus_reversal70":[e for e in evaluated if e["confluence_70"]],
        "cluster_plus_reversal75":[e for e in evaluated if e["confluence_75"]],
        "cluster_plus_reversal75_vol15":[e for e in evaluated if e["confluence_75_vol15"]],
    }
    results = {
        name:{"events":len(events),"horizons":{str(h):summarize([e["forward_return_pct"][str(h)] for e in events]) for h in HORIZONS}}
        for name,events in cohorts.items()
    }
    status = "validated" if len(evaluated) >= 20 else "inconclusive_insufficient_publication_history"
    report = {
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "status":status,
        "source":"Euronext topic 1081 + per-company Euronext archive + Yahoo daily",
        "days":DAYS,
        "method":{
            "signal_availability":"verified disclosure published_at only",
            "reversal_data":"completed daily bars strictly before publication date",
            "entry":"first trading-day close strictly after publication date",
            "forward_horizons":"5/10/20/60 trading sessions after conservative entry",
            "no_lookahead":True,
        },
        "announcement_meta":meta,
        "announcements":len(announcements),
        "relevant_announcements":len(relevant),
        "topic_trades":len(topic_trades),
        "archive_trades":len(archive_trades),
        "parsed_trades":len(trades),
        "excluded_without_verified_publication":excluded_without_publication,
        "cluster_events":len(clusters),
        "evaluated_events":len(evaluated),
        "archive_stats":archive_stats,
        "detail_errors":detail_errors[:30],
        "results":results,
        "events":evaluated,
        "limitations":[
            "Public Euronext archive depth/pagination may still limit historical coverage",
            "Rows without machine-verifiable publication date are excluded from return attribution",
            "current-universe survivorship bias",
            "no transaction costs/slippage",
            "actor parsing depends on disclosure text quality",
        ],
    }
    with open("insider_confluence_backtest.json","w",encoding="utf-8") as f:
        json.dump(report,f,ensure_ascii=False,indent=2)

    print("=== INSIDER CONFLUENCE BACKTEST ===")
    print(
        f"status={status} topic_announcements={len(announcements)} relevant={len(relevant)} "
        f"topic_trades={len(topic_trades)} archive_trades={len(archive_trades)} dedup_trades={len(trades)} "
        f"excluded_no_publication={excluded_without_publication} clusters={len(clusters)} evaluated={len(evaluated)}"
    )
    for name,block in results.items():
        print(f"{name}: {block['events']} events")
        for h in HORIZONS:
            s = block['horizons'][str(h)]
            print(f"  {h}d n={s['n']} mean={s['mean_pct']}% median={s['median_pct']}% positive={s['positive_rate_pct']}%")

    # Insufficient public history is a diagnostic result, not a code failure. The
    # workflow remains green while status prevents us from treating the sample as proof.
    if not announcements:
        raise SystemExit("No Euronext disclosure data available for diagnostic backtest")


if __name__ == "__main__":
    main()
