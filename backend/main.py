from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import connect, init_db
from scoring import calculate_score, signal_label
from providers import YahooProvider

app = FastAPI(title="NordicSignal API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

SEED = [
    ("LSG", "Lerøy Seafood", "Seafood", 34, 24, 16, 12),
    ("MPCC", "MPCC", "Shipping", 36, 15, 17, 12),
    ("ELO", "Elopak", "Packaging", 30, 23, 16, 12),
    ("PEXIP", "Pexip", "Technology", 33, 18, 15, 11),
    ("XPLRA", "Xplora", "Technology", 32, 18, 14, 6),
]
TICKERS = [x[0] for x in SEED]
provider = YahooProvider()


def raw(value, default=None):
    if isinstance(value, dict):
        return value.get("raw", default)
    return value if value is not None else default


def clamp_score(value, low, high):
    return max(low, min(high, int(round(value))))


def seed_db():
    conn = connect()
    now = datetime.now(timezone.utc).isoformat()
    for ticker, name, sector, f, i, v, s in SEED:
        conn.execute("INSERT OR IGNORE INTO stocks(ticker,name,sector,exchange) VALUES(?,?,?,?)", (ticker, name, sector, "Oslo Børs"))
        if not conn.execute("SELECT 1 FROM scores WHERE ticker=? LIMIT 1", (ticker,)).fetchone():
            total = calculate_score(f, i, v, s)
            conn.execute("INSERT INTO scores(ticker,fundamentals,insider,valuation,sentiment,total,created_at) VALUES(?,?,?,?,?,?,?)", (ticker, f, i, v, s, total, now))
    conn.commit(); conn.close()


def fundamentals_score(r):
    fd = r.get("financialData", {})
    ks = r.get("defaultKeyStatistics", {})
    sd = r.get("summaryDetail", {})
    margin = raw(fd.get("profitMargins"), None)
    roe = raw(fd.get("returnOnEquity"), None)
    growth = raw(fd.get("revenueGrowth"), None)
    debt = raw(fd.get("debtToEquity"), None)
    pe = raw(sd.get("trailingPE"), raw(ks.get("trailingPE"), None))
    points = 20.0
    if margin is not None: points += 5 if margin > .10 else 2 if margin > 0 else -4
    if roe is not None: points += 5 if roe > .12 else 2 if roe > 0 else -3
    if growth is not None: points += 5 if growth > .10 else 2 if growth > 0 else -2
    if debt is not None: points += 3 if debt < 80 else 0 if debt < 160 else -3
    if pe is not None and pe > 0: points += 2 if pe < 18 else 0 if pe < 30 else -2
    return clamp_score(points, 0, 40)


def valuation_score(r):
    sd = r.get("summaryDetail", {})
    ks = r.get("defaultKeyStatistics", {})
    pe = raw(sd.get("trailingPE"), raw(ks.get("trailingPE"), None))
    pb = raw(ks.get("priceToBook"), None)
    peg = raw(ks.get("pegRatio"), None)
    ev_ebitda = raw(ks.get("enterpriseToEbitda"), None)
    points = 10.0
    if pe is not None and pe > 0: points += 4 if pe < 15 else 2 if pe < 25 else -2
    if pb is not None and pb > 0: points += 3 if pb < 2 else 1 if pb < 4 else -1
    if peg is not None and peg > 0: points += 2 if peg < 1.5 else 0 if peg < 2.5 else -1
    if ev_ebitda is not None and ev_ebitda > 0: points += 2 if ev_ebitda < 12 else 0 if ev_ebitda < 20 else -1
    return clamp_score(points, 0, 20)


def insider_score(r):
    net = r.get("netSharePurchaseActivity", {})
    buy = raw(net.get("buyInfoShares"), 0) or 0
    sell = raw(net.get("sellInfoShares"), 0) or 0
    if buy or sell:
        ratio = (buy - sell) / max(buy + sell, 1)
        return clamp_score(12.5 + ratio * 12.5, 0, 25)
    tx = r.get("insiderTransactions", {}).get("transactions", [])
    if tx:
        buys = sum(1 for x in tx if str(x.get("transactionText", "")).lower().find("buy") >= 0)
        sells = sum(1 for x in tx if str(x.get("transactionText", "")).lower().find("sell") >= 0)
        return clamp_score(12.5 + (buys - sells) * 2.5, 0, 25)
    return 12


def sentiment_score(history):
    if len(history) < 5: return 7
    closes = [x["close"] for x in history if x.get("close") is not None]
    if len(closes) < 5: return 7
    start = closes[max(0, len(closes) - min(60, len(closes)))]
    end = closes[-1]
    ret = ((end - start) / start) if start else 0
    return clamp_score(7.5 + ret * 30, 0, 15)


def refresh_one(ticker):
    try:
        research = provider.research(ticker)
        history = provider.historical(ticker, "3m")
        f = fundamentals_score(research)
        i = insider_score(research)
        v = valuation_score(research)
        s = sentiment_score(history)
        total = calculate_score(f, i, v, s)
        now = datetime.now(timezone.utc).isoformat()
        conn = connect()
        conn.execute("INSERT INTO scores(ticker,fundamentals,insider,valuation,sentiment,total,created_at) VALUES(?,?,?,?,?,?,?)", (ticker, f, i, v, s, total, now))
        conn.commit(); conn.close()
        return {"ticker": ticker, "score": total, "source": "live"}
    except Exception as exc:
        return {"ticker": ticker, "source": "stored", "error": str(exc)}


def refresh_all():
    return [refresh_one(t) for t in TICKERS]


@app.on_event("startup")
def startup():
    init_db()
    seed_db()
    refresh_all()


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "NordicSignal API", "version": "2.0.0", "provider": "Yahoo Finance"}


@app.get("/api/refresh")
def refresh():
    return {"status": "ok", "results": refresh_all()}


@app.get("/api/stocks")
def stocks():
    conn = connect()
    rows = conn.execute("""SELECT s.ticker,s.name,s.sector,sc.fundamentals,sc.insider,sc.valuation,sc.sentiment,sc.total
        FROM stocks s JOIN scores sc ON sc.id=(SELECT MAX(id) FROM scores x WHERE x.ticker=s.ticker)
        WHERE s.active=1 ORDER BY sc.total DESC""").fetchall(); conn.close()
    return {"items": [{"ticker":r["ticker"],"name":r["name"],"sector":r["sector"],"score":r["total"],"fundamentals":r["fundamentals"],"insider":r["insider"],"valuation":r["valuation"],"sentiment":r["sentiment"],"signal":signal_label(r["total"])} for r in rows]}


@app.get("/api/search")
def search(q: str = ""):
    q=q.strip()
    if not q: return {"items":[]}
    conn=connect(); rows=conn.execute("SELECT ticker,name,sector,exchange FROM stocks WHERE active=1 AND (ticker LIKE ? OR name LIKE ?) ORDER BY name LIMIT 20", (f"%{q}%",f"%{q}%")).fetchall(); conn.close()
    return {"items":[dict(r) for r in rows]}


@app.get("/api/stocks/{ticker}")
def stock(ticker: str):
    conn=connect(); r=conn.execute("""SELECT s.ticker,s.name,s.sector,sc.fundamentals,sc.insider,sc.valuation,sc.sentiment,sc.total FROM stocks s JOIN scores sc ON sc.ticker=s.ticker WHERE s.ticker=? ORDER BY sc.id DESC LIMIT 1""",(ticker.upper(),)).fetchone(); conn.close()
    if not r: return {"error":"Ticker not found"}
    return {"ticker":r["ticker"],"name":r["name"],"sector":r["sector"],"score":r["total"],"fundamentals":r["fundamentals"],"insider":r["insider"],"valuation":r["valuation"],"sentiment":r["sentiment"],"signal":signal_label(r["total"])}


@app.get("/api/quote/{ticker}")
def quote(ticker: str):
    try: return provider.quote(ticker)
    except Exception as exc: return {"ticker":ticker.upper(),"source":"unavailable","error":str(exc)}


@app.get("/api/history/{ticker}")
def history(ticker: str, period: str = "1y"):
    try: return {"ticker":ticker.upper(),"period":period,"items":provider.historical(ticker, period)}
    except Exception as exc: return {"ticker":ticker.upper(),"period":period,"items":[],"error":str(exc)}


@app.get("/api/research/{ticker}")
def research(ticker: str):
    try:
        r=provider.research(ticker)
        return {"ticker":ticker.upper(),"data":r,"source":"Yahoo Finance"}
    except Exception as exc:
        return {"ticker":ticker.upper(),"data":{},"source":"unavailable","error":str(exc)}


@app.get("/api/insider/{ticker}")
def insider(ticker: str):
    try:
        r=provider.research(ticker)
        tx=r.get("insiderTransactions",{}).get("transactions",[])
        return {"ticker":ticker.upper(),"items":tx[:25],"source":"Yahoo Finance"}
    except Exception as exc: return {"ticker":ticker.upper(),"items":[],"error":str(exc)}


@app.get("/api/short/{ticker}")
def short(ticker: str):
    try:
        r=provider.research(ticker); ks=r.get("defaultKeyStatistics",{}); sd=r.get("summaryDetail",{})
        return {"ticker":ticker.upper(),"shares_short":raw(ks.get("sharesShort")),"short_percent_float":raw(ks.get("shortPercentOfFloat")),"short_ratio":raw(ks.get("shortRatio")),"shares_outstanding":raw(ks.get("sharesOutstanding")),"source":"Yahoo Finance"}
    except Exception as exc: return {"ticker":ticker.upper(),"source":"unavailable","error":str(exc)}


@app.get("/api/radar")
def radar():
    conn=connect(); rows=conn.execute("SELECT ticker,total FROM scores WHERE id IN (SELECT MAX(id) FROM scores GROUP BY ticker) ORDER BY total DESC LIMIT 10").fetchall(); conn.close()
    items=[]
    for r in rows:
        score=r["total"]
        event="Strong signal" if score>=85 else "Watch signal" if score>=75 else "Neutral signal" if score>=60 else "Risk signal"
        strength="strong" if score>=85 else "watch" if score>=75 else "neutral" if score>=60 else "risk"
        items.append({"ticker":r["ticker"],"score":score,"event":event,"strength":strength})
    return {"items":items}


@app.get("/api/markets")
def markets():
    conn=connect(); rows=conn.execute("SELECT sector,COUNT(*) count,ROUND(AVG(total),1) avg_score FROM stocks s JOIN scores sc ON sc.id=(SELECT MAX(id) FROM scores x WHERE x.ticker=s.ticker) WHERE s.active=1 GROUP BY sector ORDER BY avg_score DESC").fetchall(); conn.close()
    return {"items":[dict(r) for r in rows]}


@app.get("/api/watchlist")
def get_watchlist():
    conn=connect(); rows=conn.execute("SELECT w.ticker,s.name FROM watchlist w JOIN stocks s ON s.ticker=w.ticker ORDER BY w.created_at DESC").fetchall(); conn.close(); return {"items":[dict(r) for r in rows]}


@app.post("/api/watchlist/{ticker}")
def add_watchlist(ticker: str):
    conn=connect(); conn.execute("INSERT OR IGNORE INTO watchlist(ticker,created_at) VALUES(?,?)",(ticker.upper(),datetime.now(timezone.utc).isoformat())); conn.commit(); conn.close(); return {"status":"ok","ticker":ticker.upper()}


@app.delete("/api/watchlist/{ticker}")
def remove_watchlist(ticker: str):
    conn=connect(); conn.execute("DELETE FROM watchlist WHERE ticker=?",(ticker.upper(),)); conn.commit(); conn.close(); return {"status":"ok","ticker":ticker.upper()}
