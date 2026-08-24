from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import connect, init_db
from scoring import calculate_score, signal_label
from providers import YahooProvider

app = FastAPI(title="NordicSignal API", version="2.4.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

SEED = [("LSG", "Lerøy Seafood", "Seafood", 34, 24, 16, 12),("MPCC", "MPCC", "Shipping", 36, 15, 17, 12),("ELO", "Elopak", "Packaging", 30, 23, 16, 12),("PEXIP", "Pexip", "Technology", 33, 18, 15, 11),("XPLRA", "Xplora", "Technology", 32, 18, 14, 6)]
TICKERS = [x[0] for x in SEED]
provider = YahooProvider()

def raw(value, default=None):
    if isinstance(value, dict): return value.get("raw", default)
    return value if value is not None else default

def clamp_score(value, low, high): return max(low, min(high, int(round(value))))

def timeseries_map(series):
    if isinstance(series, dict): return series
    if not isinstance(series, list): return {}
    mapped = {}
    for item in series:
        if not isinstance(item, dict): continue
        for key, value in item.items():
            if key not in ("meta", "timestamp") and isinstance(value, list): mapped[key] = value
    return mapped

def latest_timeseries_value(series, name):
    values = timeseries_map(series).get(name, [])
    candidates = []
    for item in values if isinstance(values, list) else []:
        if not isinstance(item, dict): continue
        value = item.get("reportedValue")
        if isinstance(value, dict): value = value.get("raw")
        if isinstance(value, (int, float)): candidates.append((item.get("asOfDate", ""), float(value)))
    return sorted(candidates, key=lambda x: x[0])[-1][1] if candidates else None

def annual_values(series, name):
    values = timeseries_map(series).get(name, [])
    out = []
    for item in values if isinstance(values, list) else []:
        if not isinstance(item, dict): continue
        value = item.get("reportedValue")
        if isinstance(value, dict): value = value.get("raw")
        if isinstance(value, (int, float)): out.append((item.get("asOfDate", ""), float(value)))
    return sorted(out, key=lambda x: x[0], reverse=True)

def seed_db():
    conn=connect(); now=datetime.now(timezone.utc).isoformat()
    for ticker,name,sector,f,i,v,s in SEED:
        conn.execute("INSERT OR IGNORE INTO stocks(ticker,name,sector,exchange) VALUES(?,?,?,?)",(ticker,name,sector,"Oslo Børs"))
        if not conn.execute("SELECT 1 FROM scores WHERE ticker=? LIMIT 1",(ticker,)).fetchone():
            conn.execute("INSERT INTO scores(ticker,fundamentals,insider,valuation,sentiment,total,created_at,source) VALUES(?,?,?,?,?,?,?,?)",(ticker,f,i,v,s,calculate_score(f,i,v,s),now,"stored"))
    conn.commit(); conn.close()

def fundamental_metrics(r):
    f = r.get("fundamentals", {}) or {}
    revenue = f.get("revenue"); ebitda = f.get("ebitda"); net_income = f.get("net_income"); fcf = f.get("free_cashflow"); debt = f.get("debt"); equity = f.get("equity")
    annual = r.get("_annual_series", {}) or {}
    revs = annual_values(annual, "annualTotalRevenue")
    growth = ((revs[0][1] / revs[1][1]) - 1) if len(revs) >= 2 and revs[1][1] else None
    margin = (ebitda / revenue) if ebitda is not None and revenue else None
    roe = (net_income / equity) if net_income is not None and equity else None
    debt_eq = (debt / equity * 100) if debt is not None and equity else None
    fcf_margin = (fcf / revenue) if fcf is not None and revenue else None
    return {"revenue":revenue,"ebitda":ebitda,"net_income":net_income,"free_cashflow":fcf,"debt":debt,"equity":equity,"revenue_growth":growth,"ebitda_margin":margin,"roe":roe,"debt_to_equity":debt_eq,"fcf_margin":fcf_margin}

def fundamentals_score(metrics):
    points = 20.0
    margin, roe, growth, debt_eq, fcf = metrics["ebitda_margin"], metrics["roe"], metrics["revenue_growth"], metrics["debt_to_equity"], metrics["free_cashflow"]
    if margin is not None: points += 6 if margin >= .15 else 4 if margin >= .10 else 2 if margin >= .05 else -2 if margin < 0 else 0
    if roe is not None: points += 5 if roe >= .12 else 3 if roe >= .08 else 1 if roe >= .05 else -2
    if growth is not None: points += 5 if growth >= .10 else 3 if growth >= .03 else 1 if growth >= 0 else -2
    if debt_eq is not None: points += 3 if debt_eq < 60 else 1 if debt_eq < 100 else 0 if debt_eq < 160 else -3
    if fcf is not None and fcf > 0: points += 1
    return clamp_score(points, 0, 40)

def valuation_score(r):
    sd=r.get("summaryDetail",{}) or {}; ks=r.get("defaultKeyStatistics",{}) or {}; fd=r.get("financialData",{}) or {}
    pe=raw(sd.get("trailingPE"),raw(ks.get("trailingPE"))); pb=raw(ks.get("priceToBook")); ev_ebitda=raw(ks.get("enterpriseToEbitda")); points=10.0
    if pe is not None and pe>0: points += 4 if pe<15 else 2 if pe<25 else -2
    if pb is not None and pb>0: points += 3 if pb<2 else 1 if pb<4 else -1
    if ev_ebitda is not None and ev_ebitda>0: points += 2 if ev_ebitda<12 else 0 if ev_ebitda<20 else -1
    return clamp_score(points,0,20)

def sentiment_score(history):
    closes=[x["close"] for x in history if x.get("close") is not None]
    if len(closes)<5:return 7
    start=closes[max(0,len(closes)-min(60,len(closes)))]; end=closes[-1]; ret=((end-start)/start) if start else 0
    return clamp_score(7.5+ret*30,0,15)

def refresh_one(ticker):
    ticker=ticker.upper()
    try:
        research=provider.research(ticker); history=provider.historical(ticker,"3m")
        if not research: raise RuntimeError("Yahoo Finance returned no research data")
        if len(history)<5: raise RuntimeError("Yahoo Finance returned insufficient historical data")
        f=fundamentals_score(fundamental_metrics(research)); v=valuation_score(research); s=sentiment_score(history); i=0
        available_max=40+20+15; verified_sum=f+v+s; normalized=round((verified_sum/available_max)*100)
        total=clamp_score(normalized,0,100); now=datetime.now(timezone.utc).isoformat(); source="partial_live"
        conn=connect(); conn.execute("INSERT INTO scores(ticker,fundamentals,insider,valuation,sentiment,total,created_at,source) VALUES(?,?,?,?,?,?,?,?)",(ticker,f,i,v,s,total,now,source)); conn.commit(); conn.close()
        metrics=fundamental_metrics(research)
        return {"ticker":ticker,"score":total,"source":source,"live_verified":False,"coverage":{"verified_points":available_max,"total_points":100,"missing":["insider"]},"updated_at":now,"components":{"fundamentals":f,"fundamentals_max":40,"insider":None,"insider_max":25,"valuation":v,"valuation_max":20,"sentiment":s,"sentiment_max":15},"metrics":metrics,"data_quality":{"fundamentals":"live","valuation":"live","sentiment":"live","insider":"unavailable"}}
    except Exception as exc: return {"ticker":ticker,"source":"stored","live_verified":False,"error":str(exc)}

def refresh_all(): return [refresh_one(t) for t in TICKERS]

@app.on_event("startup")
def startup(): init_db(); seed_db(); refresh_all()

@app.get("/api/health")
def health(): return {"status":"ok","service":"NordicSignal API","version":"2.4.0","provider":"Yahoo Finance","score_policy":"verified-components-with-coverage"}

@app.get("/api/refresh")
def refresh(): return {"status":"ok","results":refresh_all()}

@app.get("/api/verification")
def verification():
    conn=connect(); rows=conn.execute("SELECT s.ticker,s.name,sc.fundamentals,sc.insider,sc.valuation,sc.sentiment,sc.total,sc.created_at,COALESCE(sc.source,'stored') source FROM stocks s JOIN scores sc ON sc.id=(SELECT MAX(id) FROM scores x WHERE x.ticker=s.ticker) WHERE s.active=1 ORDER BY s.ticker").fetchall(); conn.close(); now=datetime.now(timezone.utc); items=[]
    for r in rows:
        try: updated=datetime.fromisoformat(r["created_at"]); updated=updated if updated.tzinfo else updated.replace(tzinfo=timezone.utc); age=max(0,int((now-updated).total_seconds()))
        except Exception: age=None
        source=r["source"]; items.append({"ticker":r["ticker"],"name":r["name"],"score":r["total"],"source":source,"live_verified":source=="live","partial_live":source=="partial_live","updated_at":r["created_at"],"age_seconds":age,"coverage":{"verified_points":75 if source=="partial_live" else 100 if source=="live" else 0,"total_points":100},"components":{"fundamentals":r["fundamentals"],"insider":None if source=="partial_live" else r["insider"],"valuation":r["valuation"],"sentiment":r["sentiment"]}})
    return {"status":"ok","items":items,"all_live_verified":bool(items) and all(x["live_verified"] for x in items),"all_scores_live_or_partial":bool(items) and all(x["source"] in ("live","partial_live") for x in items)}

@app.get("/api/stocks")
def stocks():
    conn=connect(); rows=conn.execute("SELECT s.ticker,s.name,s.sector,sc.fundamentals,sc.insider,sc.valuation,sc.sentiment,sc.total,sc.created_at,COALESCE(sc.source,'stored') source FROM stocks s JOIN scores sc ON sc.id=(SELECT MAX(id) FROM scores x WHERE x.ticker=s.ticker) WHERE s.active=1 ORDER BY sc.total DESC").fetchall(); conn.close()
    return {"items":[{"ticker":r["ticker"],"name":r["name"],"sector":r["sector"],"score":r["total"],"fundamentals":r["fundamentals"],"insider":r["insider"] if r["source"]=="live" else None,"valuation":r["valuation"],"sentiment":r["sentiment"],"signal":signal_label(r["total"]),"score_source":r["source"],"live_verified":r["source"]=="live","partial_live":r["source"]=="partial_live","score_updated_at":r["created_at"]} for r in rows]}

@app.get("/api/search")
def search(q:str=""):
    q=q.strip()
    if not q:return {"items":[]}
    conn=connect(); rows=conn.execute("SELECT ticker,name,sector,exchange FROM stocks WHERE active=1 AND (ticker LIKE ? OR name LIKE ?) ORDER BY name LIMIT 20",(f"%{q}%",f"%{q}%")).fetchall(); conn.close(); return {"items":[dict(r) for r in rows]}

@app.get("/api/stocks/{ticker}")
def stock(ticker:str):
    conn=connect(); r=conn.execute("SELECT s.ticker,s.name,s.sector,sc.fundamentals,sc.insider,sc.valuation,sc.sentiment,sc.total,sc.created_at,COALESCE(sc.source,'stored') source FROM stocks s JOIN scores sc ON sc.ticker=s.ticker WHERE s.ticker=? ORDER BY sc.id DESC LIMIT 1",(ticker.upper(),)).fetchone(); conn.close()
    if not r:return {"error":"Ticker not found"}
    return {"ticker":r["ticker"],"name":r["name"],"sector":r["sector"],"score":r["total"],"fundamentals":r["fundamentals"],"insider":r["insider"] if r["source"]=="live" else None,"valuation":r["valuation"],"sentiment":r["sentiment"],"signal":signal_label(r["total"]),"score_source":r["source"],"live_verified":r["source"]=="live","partial_live":r["source"]=="partial_live","score_updated_at":r["created_at"]}

@app.get("/api/quote/{ticker}")
def quote(ticker:str):
    try:
        data=provider.quote(ticker); conn=connect(); conn.execute("INSERT INTO quotes(ticker,price,change_pct,volume,captured_at) VALUES(?,?,?,?,?)",(ticker.upper(),data.get("price"),data.get("change_pct"),data.get("volume"),data.get("captured_at") or datetime.now(timezone.utc).isoformat())); conn.commit(); conn.close(); return data
    except Exception as exc:return {"ticker":ticker.upper(),"source":"unavailable","error":str(exc)}

@app.get("/api/history/{ticker}")
def history(ticker:str,period:str="1y"):
    try:return {"ticker":ticker.upper(),"period":period,"items":provider.historical(ticker,period)}
    except Exception as exc:return {"ticker":ticker.upper(),"period":period,"items":[],"error":str(exc)}

@app.get("/api/research/{ticker}")
def research(ticker:str):
    try:r=provider.research(ticker); return {"ticker":ticker.upper(),"data":r,"source":r.get("source","Yahoo Finance")}
    except Exception as exc:return {"ticker":ticker.upper(),"data":{},"source":"unavailable","error":str(exc)}

@app.get("/api/fundamentals/{ticker}")
def fundamentals(ticker:str):
    try:
        r=provider.fundamentals(ticker); series=r.get("series",[]) if isinstance(r,dict) else []
        return {"ticker":ticker.upper(),"source":r.get("source","Yahoo Finance Timeseries"),"captured_at":r.get("captured_at"),"data":{"revenue":latest_timeseries_value(series,"annualTotalRevenue"),"ebitda":latest_timeseries_value(series,"annualEBITDA"),"ebit":latest_timeseries_value(series,"annualEBIT"),"net_income":latest_timeseries_value(series,"annualNetIncome"),"eps":latest_timeseries_value(series,"annualDilutedEPS"),"operating_cashflow":latest_timeseries_value(series,"annualOperatingCashFlow"),"free_cashflow":latest_timeseries_value(series,"annualFreeCashFlow"),"debt":latest_timeseries_value(series,"annualTotalDebt"),"equity":latest_timeseries_value(series,"annualStockholdersEquity"),"gross_profit":latest_timeseries_value(series,"annualGrossProfit"),"operating_income":latest_timeseries_value(series,"annualOperatingIncome"),"pretax_income":latest_timeseries_value(series,"annualPretaxIncome")}}
    except Exception as exc:return {"ticker":ticker.upper(),"source":"unavailable","data":{},"error":str(exc)}

@app.get("/api/score-explanation/{ticker}")
def score_explanation(ticker:str):
    try:
        r=provider.research(ticker); metrics=fundamental_metrics(r); reasons=[]
        if metrics["free_cashflow"] is not None and metrics["free_cashflow"]>0: reasons.append({"type":"positive","metric":"free_cashflow","value":metrics["free_cashflow"],"text":"Free cash flow is positive."})
        if metrics["fcf_margin"] is not None and metrics["fcf_margin"]>=.05: reasons.append({"type":"positive","metric":"fcf_margin","value":metrics["fcf_margin"],"text":"Free cash flow margin is at least 5%."})
        if metrics["ebitda_margin"] is not None and metrics["ebitda_margin"]>=.10: reasons.append({"type":"positive","metric":"ebitda_margin","value":metrics["ebitda_margin"],"text":"EBITDA margin is at least 10%."})
        elif metrics["ebitda_margin"] is not None and metrics["ebitda_margin"]<.05: reasons.append({"type":"negative","metric":"ebitda_margin","value":metrics["ebitda_margin"],"text":"EBITDA margin is below 5%."})
        if metrics["revenue_growth"] is not None and metrics["revenue_growth"]<0: reasons.append({"type":"negative","metric":"revenue_growth","value":metrics["revenue_growth"],"text":"Revenue growth is negative."})
        if metrics["revenue_growth"] is not None and metrics["revenue_growth"]>=.10: reasons.append({"type":"positive","metric":"revenue_growth","value":metrics["revenue_growth"],"text":"Revenue growth is above 10%."})
        if metrics["roe"] is not None and metrics["roe"]>=.12: reasons.append({"type":"positive","metric":"roe","value":metrics["roe"],"text":"ROE is strong."})
        elif metrics["roe"] is not None and metrics["roe"]<.05: reasons.append({"type":"negative","metric":"roe","value":metrics["roe"],"text":"ROE is relatively low."})
        if metrics["debt_to_equity"] is not None and metrics["debt_to_equity"]>160: reasons.append({"type":"negative","metric":"debt_to_equity","value":metrics["debt_to_equity"],"text":"Debt-to-equity is high."})
        return {"ticker":ticker.upper(),"score_source":"partial_live","coverage":{"verified_points":75,"total_points":100,"missing":["insider"]},"metrics":metrics,"reasons":reasons,"data_quality":{"fundamentals":"live","valuation":"live","sentiment":"live","insider":"unavailable"}}
    except Exception as exc:return {"ticker":ticker.upper(),"score_source":"unavailable","reasons":[],"error":str(exc)}

@app.get("/api/insider/{ticker}")
def insider(ticker:str): return {"ticker":ticker.upper(),"items":[],"source":"unavailable","error":"Live insider transactions require a separate reliable insider-data source; no synthetic data is shown."}

@app.get("/api/short/{ticker}")
def short(ticker:str): return {"ticker":ticker.upper(),"source":"unavailable","error":"Live short-interest data requires a separate reliable short-data source; no synthetic data is shown."}

@app.get("/api/radar")
def radar():
    conn=connect(); rows=conn.execute("SELECT ticker,total FROM scores WHERE id IN (SELECT MAX(id) FROM scores GROUP BY ticker) ORDER BY total DESC LIMIT 10").fetchall(); conn.close(); items=[]
    for r in rows:
        score=r["total"]; event="Strong signal" if score>=85 else "Watch signal" if score>=75 else "Neutral signal" if score>=60 else "Risk signal"; strength="strong" if score>=85 else "watch" if score>=75 else "neutral" if score>=60 else "risk"; items.append({"ticker":r["ticker"],"score":score,"event":event,"strength":strength})
    return {"items":items}

@app.get("/api/markets")
def markets():
    conn=connect(); rows=conn.execute("SELECT sector,COUNT(*) count,ROUND(AVG(total),1) avg_score FROM stocks s JOIN scores sc ON sc.id=(SELECT MAX(id) FROM scores x WHERE x.ticker=s.ticker) WHERE s.active=1 GROUP BY sector ORDER BY avg_score DESC").fetchall(); conn.close(); return {"items":[dict(r) for r in rows]}

@app.get("/api/watchlist")
def get_watchlist():
    conn=connect(); rows=conn.execute("SELECT w.ticker,s.name FROM watchlist w JOIN stocks s ON s.ticker=w.ticker ORDER BY w.created_at DESC").fetchall(); conn.close(); return {"items":[dict(r) for r in rows]}

@app.post("/api/watchlist/{ticker}")
def add_watchlist(ticker:str):
    conn=connect(); conn.execute("INSERT OR IGNORE INTO watchlist(ticker,created_at) VALUES(?,?)",(ticker.upper(),datetime.now(timezone.utc).isoformat())); conn.commit(); conn.close(); return {"status":"ok","ticker":ticker.upper()}

@app.delete("/api/watchlist/{ticker}")
def remove_watchlist(ticker:str):
    conn=connect(); conn.execute("DELETE FROM watchlist WHERE ticker=?",(ticker.upper(),)); conn.commit(); conn.close(); return {"status":"ok","ticker":ticker.upper()}