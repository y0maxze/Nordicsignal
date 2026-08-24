from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import connect, init_db
from scoring import calculate_score, signal_label
from providers import YahooProvider

app = FastAPI(title="NordicSignal API", version="2.3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

SEED = [("LSG", "Lerøy Seafood", "Seafood", 34, 24, 16, 12),("MPCC", "MPCC", "Shipping", 36, 15, 17, 12),("ELO", "Elopak", "Packaging", 30, 23, 16, 12),("PEXIP", "Pexip", "Technology", 33, 18, 15, 11),("XPLRA", "Xplora", "Technology", 32, 18, 14, 6)]
TICKERS = [x[0] for x in SEED]
provider = YahooProvider()

def raw(value, default=None):
    if isinstance(value, dict): return value.get("raw", default)
    return value if value is not None else default

def clamp_score(value, low, high): return max(low, min(high, int(round(value))))

def seed_db():
    conn=connect(); now=datetime.now(timezone.utc).isoformat()
    for ticker,name,sector,f,i,v,s in SEED:
        conn.execute("INSERT OR IGNORE INTO stocks(ticker,name,sector,exchange) VALUES(?,?,?,?)",(ticker,name,sector,"Oslo Børs"))
        if not conn.execute("SELECT 1 FROM scores WHERE ticker=? LIMIT 1",(ticker,)).fetchone():
            conn.execute("INSERT INTO scores(ticker,fundamentals,insider,valuation,sentiment,total,created_at,source) VALUES(?,?,?,?,?,?,?,?)",(ticker,f,i,v,s,calculate_score(f,i,v,s),now,"stored"))
    conn.commit(); conn.close()

def fundamentals_score(r):
    fd=r.get("financialData",{}); ks=r.get("defaultKeyStatistics",{}); sd=r.get("summaryDetail",{})
    margin=raw(fd.get("profitMargins")); roe=raw(fd.get("returnOnEquity")); growth=raw(fd.get("revenueGrowth")); debt=raw(fd.get("debtToEquity")); pe=raw(sd.get("trailingPE"),raw(ks.get("trailingPE")))
    points=20.0
    if margin is not None: points += 5 if margin>.10 else 2 if margin>0 else -4
    if roe is not None: points += 5 if roe>.12 else 2 if roe>0 else -3
    if growth is not None: points += 5 if growth>.10 else 2 if growth>0 else -2
    if debt is not None: points += 3 if debt<80 else 0 if debt<160 else -3
    if pe is not None and pe>0: points += 2 if pe<18 else 0 if pe<30 else -2
    return clamp_score(points,0,40)

def valuation_score(r):
    sd=r.get("summaryDetail",{}); ks=r.get("defaultKeyStatistics",{})
    pe=raw(sd.get("trailingPE"),raw(ks.get("trailingPE"))); pb=raw(ks.get("priceToBook")); peg=raw(ks.get("pegRatio")); ev_ebitda=raw(ks.get("enterpriseToEbitda")); points=10.0
    if pe is not None and pe>0: points += 4 if pe<15 else 2 if pe<25 else -2
    if pb is not None and pb>0: points += 3 if pb<2 else 1 if pb<4 else -1
    if peg is not None and peg>0: points += 2 if peg<1.5 else 0 if peg<2.5 else -1
    if ev_ebitda is not None and ev_ebitda>0: points += 2 if ev_ebitda<12 else 0 if ev_ebitda<20 else -1
    return clamp_score(points,0,20)

def insider_score(r):
    # No live insider score is invented when Yahoo's crumb-protected transaction feed is unavailable.
    return 12

def sentiment_score(history):
    if len(history)<5:return 7
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
        f=fundamentals_score(research); i=insider_score(research); v=valuation_score(research); s=sentiment_score(history); total=calculate_score(f,i,v,s); now=datetime.now(timezone.utc).isoformat()
        conn=connect(); conn.execute("INSERT INTO scores(ticker,fundamentals,insider,valuation,sentiment,total,created_at,source) VALUES(?,?,?,?,?,?,?,?)",(ticker,f,i,v,s,total,now,"live")); conn.commit(); conn.close()
        return {"ticker":ticker,"score":total,"source":"live","live_verified":True,"updated_at":now,"components":{"fundamentals":f,"insider":i,"valuation":v,"sentiment":s},"data_quality":{"fundamentals":"live","valuation":"live","sentiment":"live","insider":"unavailable"}}
    except Exception as exc: return {"ticker":ticker,"source":"stored","live_verified":False,"error":str(exc)}

def refresh_all(): return [refresh_one(t) for t in TICKERS]

@app.on_event("startup")
def startup(): init_db(); seed_db(); refresh_all()

@app.get("/api/health")
def health(): return {"status":"ok","service":"NordicSignal API","version":"2.3.0","provider":"Yahoo Finance","score_policy":"live_only_or_explicit_stored"}

@app.get("/api/refresh")
def refresh(): return {"status":"ok","results":refresh_all()}

@app.get("/api/verification")
def verification():
    conn=connect(); rows=conn.execute("SELECT s.ticker,s.name,sc.fundamentals,sc.insider,sc.valuation,sc.sentiment,sc.total,sc.created_at,COALESCE(sc.source,'stored') source FROM stocks s JOIN scores sc ON sc.id=(SELECT MAX(id) FROM scores x WHERE x.ticker=s.ticker) WHERE s.active=1 ORDER BY s.ticker").fetchall(); conn.close(); now=datetime.now(timezone.utc); items=[]
    for r in rows:
        try:
            updated=datetime.fromisoformat(r["created_at"]); updated=updated if updated.tzinfo else updated.replace(tzinfo=timezone.utc); age=max(0,int((now-updated).total_seconds()))
        except Exception: age=None
        items.append({"ticker":r["ticker"],"name":r["name"],"score":r["total"],"source":r["source"],"live_verified":r["source"]=="live","updated_at":r["created_at"],"age_seconds":age,"components":{"fundamentals":r["fundamentals"],"insider":r["insider"],"valuation":r["valuation"],"sentiment":r["sentiment"]}})
    return {"status":"ok","items":items,"all_live_verified":bool(items) and all(x["live_verified"] for x in items)}

@app.get("/api/stocks")
def stocks():
    conn=connect(); rows=conn.execute("SELECT s.ticker,s.name,s.sector,sc.fundamentals,sc.insider,sc.valuation,sc.sentiment,sc.total,sc.created_at,COALESCE(sc.source,'stored') source FROM stocks s JOIN scores sc ON sc.id=(SELECT MAX(id) FROM scores x WHERE x.ticker=s.ticker) WHERE s.active=1 ORDER BY sc.total DESC").fetchall(); conn.close()
    return {"items":[{"ticker":r["ticker"],"name":r["name"],"sector":r["sector"],"score":r["total"],"fundamentals":r["fundamentals"],"insider":r["insider"],"valuation":r["valuation"],"sentiment":r["sentiment"],"signal":signal_label(r["total"]),"score_source":r["source"],"live_verified":r["source"]=="live","score_updated_at":r["created_at"]} for r in rows]}

@app.get("/api/search")
def search(q:str=""):
    q=q.strip()
    if not q:return {"items":[]}
    conn=connect(); rows=conn.execute("SELECT ticker,name,sector,exchange FROM stocks WHERE active=1 AND (ticker LIKE ? OR name LIKE ?) ORDER BY name LIMIT 20",(f"%{q}%",f"%{q}%")).fetchall(); conn.close(); return {"items":[dict(r) for r in rows]}

@app.get("/api/stocks/{ticker}")
def stock(ticker:str):
    conn=connect(); r=conn.execute("SELECT s.ticker,s.name,s.sector,sc.fundamentals,sc.insider,sc.valuation,sc.sentiment,sc.total,sc.created_at,COALESCE(sc.source,'stored') source FROM stocks s JOIN scores sc ON sc.ticker=s.ticker WHERE s.ticker=? ORDER BY sc.id DESC LIMIT 1",(ticker.upper(),)).fetchone(); conn.close()
    if not r:return {"error":"Ticker not found"}
    return {"ticker":r["ticker"],"name":r["name"],"sector":r["sector"],"score":r["total"],"fundamentals":r["fundamentals"],"insider":r["insider"],"valuation":r["valuation"],"sentiment":r["sentiment"],"signal":signal_label(r["total"]),"score_source":r["source"],"live_verified":r["source"]=="live","score_updated_at":r["created_at"]}

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
        r=provider.research(ticker); f=r.get("fundamentals",{}); fd=r.get("financialData",{}); sd=r.get("summaryDetail",{}); ks=r.get("defaultKeyStatistics",{})
        return {"ticker":ticker.upper(),"source":r.get("source"),"captured_at":r.get("captured_at"),"data":{"revenue":f.get("revenue"),"ebitda":f.get("ebitda"),"ebit":f.get("ebit"),"net_income":f.get("net_income"),"eps":f.get("eps"),"operating_cashflow":f.get("operating_cashflow"),"free_cashflow":f.get("free_cashflow"),"debt":f.get("debt"),"equity":f.get("equity"),"gross_profit":f.get("gross_profit"),"operating_income":f.get("operating_income"),"pretax_income":f.get("pretax_income"),"gross_margin":fd.get("grossMargins"),"ebitda_margin":fd.get("ebitdaMargins"),"operating_margin":fd.get("operatingMargins"),"roe":fd.get("returnOnEquity"),"debt_to_equity":fd.get("debtToEquity"),"pe":sd.get("trailingPE"),"forward_pe":None,"price_to_book":ks.get("priceToBook"),"ev_to_ebitda":ks.get("enterpriseToEbitda")}}
    except Exception as exc:return {"ticker":ticker.upper(),"source":"unavailable","data":{},"error":str(exc)}

@app.get("/api/score-explanation/{ticker}")
def score_explanation(ticker:str):
    try:
        r=provider.research(ticker); fd=r.get("financialData",{}); f=r.get("fundamentals",{}); reasons=[]
        growth=fd.get("revenueGrowth"); margin=fd.get("ebitdaMargins"); roe=fd.get("returnOnEquity"); debt=fd.get("debtToEquity"); fcf=f.get("free_cashflow")
        if fcf is not None and fcf>0: reasons.append({"type":"positive","text":"Free cash flow is positive."})
        if margin is not None and margin>=.10: reasons.append({"type":"positive","text":"EBITDA margin is at least 10%."})
        elif margin is not None and margin<0: reasons.append({"type":"negative","text":"Operating profitability is under pressure."})
        if growth is not None and growth<0: reasons.append({"type":"negative","text":"Revenue growth is negative."})
        if roe is not None and roe>=.12: reasons.append({"type":"positive","text":"ROE is strong."})
        elif roe is not None and roe<.05: reasons.append({"type":"negative","text":"ROE is relatively low."})
        if debt is not None and debt>160: reasons.append({"type":"negative","text":"Debt-to-equity is high."})
        return {"ticker":ticker.upper(),"score_source":"live","reasons":reasons,"data_quality":{"fundamentals":"live","valuation":"live","sentiment":"live","insider":"unavailable"}}
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