"""Historical insider-cluster + reversal confluence backtest.

Diagnostic only. Uses Euronext primary-insider disclosures and Yahoo daily prices.
No production score changes are made here.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import insider_market_v2_runtime as market
from insider_signal_v2_runtime import analyze as analyze_insider
from providers import YahooProvider
from trend_reversal_runtime import calculate_reversal

TICKERS = {
    "LSG","MPCC","ELO","PEXIP","XPLRA","EQNR","DNB","NHY","YAR","MOWI","SALM","GJF",
    "TEL","ORK","TOM","KOG","NAS","AKRBP","AKSO","SUBC","BWLPG","HAUTO","CMBTO","VAR"
}
HORIZONS = (5, 10, 20, 60)
DAYS = 730
CLUSTER_WINDOW_DAYS = 14
MAX_DETAIL_RELEASES = 320


def _day(value):
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except Exception:
        return None


def _actor(row):
    return str(row.get("person") or row.get("insider") or row.get("entity") or row.get("actor") or "").strip().lower()


def _is_buy(row):
    return str(row.get("direction") or row.get("transaction_type") or row.get("activity_type") or "").lower() in {"buy","purchase","acquisition","acquire"}


def fetch_prices(provider, ticker):
    symbol = provider.symbol(ticker)
    data = provider._get(f"{provider.BASE}/v8/finance/chart/{symbol}", {"range":"5y","interval":"1d","events":"div,splits"})
    result = data["chart"]["result"][0]
    ts = result.get("timestamp") or []
    quote = (result.get("indicators",{}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    rows=[]
    for i,t in enumerate(ts):
        if i >= len(closes) or closes[i] is None:
            continue
        rows.append({"date":datetime.fromtimestamp(t, timezone.utc).date().isoformat(),"close":float(closes[i]),"volume":volumes[i] if i < len(volumes) else None})
    return rows


def nearest_index(rows, target):
    eligible=[(i,_day(r["date"])) for i,r in enumerate(rows) if _day(r["date"]) and _day(r["date"]) <= target]
    return eligible[-1][0] if eligible else None


def pct(a,b):
    return ((b/a)-1.0)*100.0 if a else None


def summarize(values):
    vals=[float(v) for v in values if v is not None]
    if not vals:
        return {"n":0,"mean_pct":None,"median_pct":None,"positive_rate_pct":None}
    return {"n":len(vals),"mean_pct":round(statistics.fmean(vals),3),"median_pct":round(statistics.median(vals),3),"positive_rate_pct":round(sum(v>0 for v in vals)/len(vals)*100,2)}


def build_cluster_events(trades):
    grouped=defaultdict(list)
    for row in trades:
        ticker=str(row.get("ticker") or "").upper()
        day=_day(row.get("trade_date") or row.get("date") or row.get("published_at"))
        if ticker in TICKERS and day and _is_buy(row):
            grouped[ticker].append((day,row))
    events=[]
    for ticker, items in grouped.items():
        items.sort(key=lambda x:x[0])
        last_event=None
        for i,(anchor,_) in enumerate(items):
            window=[dict(r) for d,r in items if timedelta(0) <= anchor-d <= timedelta(days=CLUSTER_WINDOW_DAYS)]
            actors={_actor(r) for r in window if _actor(r)}
            if len(actors) < 2:
                continue
            enriched=analyze_insider({"items":window}, window_days=CLUSTER_WINDOW_DAYS)["insider_signal_v2"]
            if last_event and (anchor-last_event).days < CLUSTER_WINDOW_DAYS:
                continue
            events.append({"ticker":ticker,"date":anchor.isoformat(),"actors":len(actors),"insider":enriched})
            last_event=anchor
    return events


def main():
    market.MAX_EURONEXT_PAGES = 40
    announcements, meta = market._announcements(DAYS)
    relevant=[a for a in announcements if str(a.get("ticker") or "").upper() in TICKERS]
    trades=[]; detail_errors=[]
    for ann in relevant[:MAX_DETAIL_RELEASES]:
        try:
            rows,_=market._euronext_ajax_rows(ann, allow_network=True)
            trades.extend(rows or [])
        except Exception as exc:
            detail_errors.append({"node_id":ann.get("node_id"),"error":str(exc)})

    clusters=build_cluster_events(trades)
    provider=YahooProvider()
    price_cache={}
    evaluated=[]
    for event in clusters:
        ticker=event["ticker"]
        if ticker not in price_cache:
            try: price_cache[ticker]=fetch_prices(provider,ticker)
            except Exception: price_cache[ticker]=[]
        rows=price_cache[ticker]
        idx=nearest_index(rows,_day(event["date"]))
        if idx is None or idx < 35:
            continue
        reversal=calculate_reversal(rows[max(0,idx-179):idx+1])
        fwd={}
        for h in HORIZONS:
            fwd[str(h)]=pct(rows[idx]["close"],rows[idx+h]["close"]) if idx+h < len(rows) else None
        vr=(reversal.get("metrics") or {}).get("volume_ratio")
        evaluated.append({**event,"reversal":reversal,"forward_return_pct":fwd,"confluence_70":bool((reversal.get("score") or 0)>=70),"confluence_75":bool((reversal.get("score") or 0)>=75),"confluence_75_vol15":bool((reversal.get("score") or 0)>=75 and (vr or 0)>=1.5)})

    cohorts={
        "cluster_all": evaluated,
        "cluster_strong": [e for e in evaluated if (e["insider"] or {}).get("label")=="STRONG"],
        "cluster_plus_reversal70": [e for e in evaluated if e["confluence_70"]],
        "cluster_plus_reversal75": [e for e in evaluated if e["confluence_75"]],
        "cluster_plus_reversal75_vol15": [e for e in evaluated if e["confluence_75_vol15"]],
    }
    results={}
    for name, events in cohorts.items():
        results[name]={"events":len(events),"horizons":{str(h):summarize([e["forward_return_pct"][str(h)] for e in events]) for h in HORIZONS}}

    report={"generated_at":datetime.now(timezone.utc).isoformat(),"source":"Euronext topic 1081 + Yahoo daily","days":DAYS,"announcement_meta":meta,"announcements":len(announcements),"relevant_announcements":len(relevant),"detail_releases_processed":min(len(relevant),MAX_DETAIL_RELEASES),"parsed_trades":len(trades),"cluster_events":len(clusters),"evaluated_events":len(evaluated),"detail_errors":detail_errors[:30],"results":results,"events":evaluated,"limitations":["Euronext pagination/detail availability can limit historical coverage","current-universe survivorship bias","no transaction costs/slippage","cluster actor parsing depends on public disclosure detail quality"]}
    with open("insider_confluence_backtest.json","w",encoding="utf-8") as f: json.dump(report,f,ensure_ascii=False,indent=2)
    print("=== INSIDER CONFLUENCE BACKTEST ===")
    print(f"announcements={len(announcements)} relevant={len(relevant)} trades={len(trades)} clusters={len(clusters)} evaluated={len(evaluated)}")
    for name, block in results.items():
        print(f"{name}: {block['events']} events")
        for h in HORIZONS:
            s=block['horizons'][str(h)]
            print(f"  {h}d n={s['n']} mean={s['mean_pct']}% median={s['median_pct']}% positive={s['positive_rate_pct']}%")
    if len(evaluated) < 5:
        raise SystemExit("Historical insider coverage too low for a meaningful confluence check")


if __name__ == "__main__":
    main()
