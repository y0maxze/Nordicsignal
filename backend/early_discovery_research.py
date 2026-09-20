"""Point-in-time Early Discovery research layer.

Detects quiet state changes before the existing Opportunity engine confirms them.
Research/watchlist only: it MUST NOT alter aggregate score, Opportunity, High
Conviction, alerts, thresholds, or position sizing.
"""
from __future__ import annotations
from statistics import mean, median, pstdev

VERSION = "2026-09-21-v1"
MIN_BARS = 80

def _rows(history):
    out=[]
    for row in history or []:
        try:
            c=float(row.get("close")); v=float(row.get("volume"))
        except (TypeError,ValueError):
            continue
        if c>0 and v>=0: out.append({"date":str(row.get("date") or row.get("timestamp") or "")[:10],"close":c,"volume":v})
    return out

def _ret(values, days):
    return (values[-1]/values[-1-days]-1.0)*100.0 if len(values)>days and values[-1-days] else None

def _daily_returns(values, window):
    sample=values[-(window+1):]
    return [(b/a)-1.0 for a,b in zip(sample[:-1],sample[1:]) if a]

def analyze(history, benchmark_history=None):
    rows=_rows(history)
    if len(rows)<MIN_BARS:
        return {"status":"insufficient_data","label":"NO_STATE","score":None,"components":{},"policy":"research_watchlist_only","version":VERSION}
    closes=[x["close"] for x in rows]; volumes=[x["volume"] for x in rows]
    recent5=[v for v in volumes[-5:] if v>0]; prior20=[v for v in volumes[-25:-5] if v>0]
    volume_accel=(median(recent5)/median(prior20)) if recent5 and prior20 and median(prior20)>0 else None
    r5,r20,r60=_ret(closes,5),_ret(closes,20),_ret(closes,60)
    vol10=pstdev(_daily_returns(closes,10))*100 if len(_daily_returns(closes,10))>=8 else None
    vol60=pstdev(_daily_returns(closes,60))*100 if len(_daily_returns(closes,60))>=40 else None
    compression=(vol10/vol60) if vol10 is not None and vol60 and vol60>0 else None
    low60=min(closes[-60:]); high60=max(closes[-60:])
    range_pos=(closes[-1]-low60)/(high60-low60) if high60>low60 else .5
    ma5=mean(closes[-5:]); ma20=mean(closes[-20:]); prev20=mean(closes[-25:-5])
    slope20=(ma20/prev20-1.0)*100 if prev20 else None
    benchmark_excess20=None
    br=_rows(benchmark_history)
    if len(br)>=21:
        b20=_ret([x["close"] for x in br],20)
        if b20 is not None and r20 is not None: benchmark_excess20=r20-b20

    score=0; reasons=[]
    # Deliberately broad research features; thresholds are not production signal thresholds.
    if volume_accel is not None and volume_accel>=1.20: score+=20; reasons.append("5-day median volume rising versus prior 20 days")
    if slope20 is not None and slope20>0: score+=20; reasons.append("20-day price baseline turning upward")
    if r5 is not None and r20 is not None and r5>0 and r5>r20/4: score+=15; reasons.append("short-term momentum improving")
    if compression is not None and compression<=0.75: score+=15; reasons.append("10-day volatility compressed versus 60-day")
    if 0.25<=range_pos<=0.75: score+=10; reasons.append("price remains inside 60-day base rather than extended")
    if benchmark_excess20 is not None and benchmark_excess20>0: score+=20; reasons.append("20-day relative strength above benchmark")
    score=min(100,score)
    label="EARLY_BUILDUP" if score>=65 else "WATCH" if score>=45 else "NORMAL"
    return {
        "status":"ok","label":label,"score":float(score),"as_of":rows[-1]["date"],
        "reasons":reasons,
        "components":{
            "return_5d_pct":round(r5,2) if r5 is not None else None,
            "return_20d_pct":round(r20,2) if r20 is not None else None,
            "return_60d_pct":round(r60,2) if r60 is not None else None,
            "volume_acceleration_5v20":round(volume_accel,2) if volume_accel is not None else None,
            "volatility_compression_10v60":round(compression,2) if compression is not None else None,
            "range_position_60d":round(range_pos,3),
            "baseline_slope_20d_pct":round(slope20,2) if slope20 is not None else None,
            "excess_return_20d_pct":round(benchmark_excess20,2) if benchmark_excess20 is not None else None,
        },
        "score_effect":0,
        "policy":"research_watchlist_only_no_production_signal_effect",
        "version":VERSION,
    }
