from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import connect, init_db
from scoring import calculate_score, signal_label

app = FastAPI(title="NordicSignal API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SEED = [
    ("LSG", "Lerøy Seafood", "Seafood", 34, 24, 16, 12),
    ("MPCC", "MPCC", "Shipping", 36, 15, 17, 12),
    ("ELO", "Elopak", "Packaging", 30, 23, 16, 12),
    ("PEXIP", "Pexip", "Technology", 33, 18, 15, 11),
    ("XPLRA", "Xplora", "Technology", 32, 18, 14, 6),
]

def seed_db():
    conn = connect()
    now = datetime.now(timezone.utc).isoformat()
    for ticker, name, sector, f, i, v, s in SEED:
        conn.execute(
            "INSERT OR IGNORE INTO stocks(ticker,name,sector) VALUES(?,?,?)",
            (ticker, name, sector),
        )
        total = calculate_score(f, i, v, s)
        conn.execute(
            """INSERT INTO scores(ticker,fundamentals,insider,valuation,sentiment,total,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (ticker, f, i, v, s, total, now),
        )
    conn.commit()
    conn.close()

@app.on_event("startup")
def startup():
    init_db()
    seed_db()

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "NordicSignal API", "version": "1.1.0"}

@app.get("/api/stocks")
def stocks():
    conn = connect()
    rows = conn.execute("""
        SELECT s.ticker, s.name, s.sector,
               sc.fundamentals, sc.insider, sc.valuation, sc.sentiment, sc.total
        FROM stocks s
        JOIN scores sc ON sc.id = (
            SELECT MAX(id) FROM scores x WHERE x.ticker = s.ticker
        )
        WHERE s.active = 1
        ORDER BY sc.total DESC
    """).fetchall()
    conn.close()

    items = []
    for r in rows:
        items.append({
            "ticker": r["ticker"], "name": r["name"], "sector": r["sector"],
            "score": r["total"], "fundamentals": r["fundamentals"],
            "insider": r["insider"], "valuation": r["valuation"],
            "sentiment": r["sentiment"], "signal": signal_label(r["total"])
        })
    return {"items": items}

@app.get("/api/search")
def search(q: str = ""):
    q = q.strip()

    if not q:
        return {"items": []}

    conn = connect()

    rows = conn.execute("""
        SELECT ticker, name, sector, exchange
        FROM stocks
        WHERE active = 1
          AND (
              ticker LIKE ?
              OR name LIKE ?
          )
        ORDER BY name ASC
        LIMIT 20
    """, (
        f"%{q}%",
        f"%{q}%"
    )).fetchall()

    conn.close()

    return {
        "items": [
            {
                "ticker": r["ticker"],
                "name": r["name"],
                "sector": r["sector"],
                "exchange": r["exchange"]
            }
            for r in rows
        ]
    }

@app.get("/api/stocks/{ticker}")
def stock(ticker: str):
    conn = connect()
    r = conn.execute("""
        SELECT s.ticker,s.name,s.sector,
               sc.fundamentals,sc.insider,sc.valuation,sc.sentiment,sc.total
        FROM stocks s JOIN scores sc ON sc.ticker=s.ticker
        WHERE s.ticker=? ORDER BY sc.id DESC LIMIT 1
    """, (ticker.upper(),)).fetchone()
    conn.close()
    if not r:
        return {"error": "Ticker not found"}
    return {
        "ticker": r["ticker"], "name": r["name"], "sector": r["sector"],
        "score": r["total"], "fundamentals": r["fundamentals"],
        "insider": r["insider"], "valuation": r["valuation"],
        "sentiment": r["sentiment"], "signal": signal_label(r["total"])
    }

@app.get("/api/radar")
def radar():
    conn = connect()
    rows = conn.execute("""
        SELECT ticker, total FROM scores
        WHERE id IN (SELECT MAX(id) FROM scores GROUP BY ticker)
        ORDER BY total DESC LIMIT 10
    """).fetchall()
    conn.close()

    items = []
    for r in rows:
        score = r["total"]
        if score >= 85:
            event = "Strong signal"
            strength = "strong"
        elif score >= 75:
            event = "Watch signal"
            strength = "watch"
        elif score >= 60:
            event = "Neutral signal"
            strength = "neutral"
        else:
            event = "Risk signal"
            strength = "risk"

        items.append({
            "ticker": r["ticker"],
            "score": score,
            "event": event,
            "strength": strength,
        })

    return {"items": items}

@app.get("/api/watchlist")
def get_watchlist():
    conn = connect()
    rows = conn.execute("""
        SELECT w.ticker, s.name FROM watchlist w
        JOIN stocks s ON s.ticker=w.ticker
        ORDER BY w.created_at DESC
    """).fetchall()
    conn.close()
    return {"items": [dict(r) for r in rows]}

@app.post("/api/watchlist/{ticker}")
def add_watchlist(ticker: str):
    conn = connect()
    conn.execute(
        "INSERT OR IGNORE INTO watchlist(ticker,created_at) VALUES(?,?)",
        (ticker.upper(), datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()
    return {"status": "ok", "ticker": ticker.upper()}
    
@app.delete("/api/watchlist/{ticker}")
def remove_watchlist(ticker: str):
    conn = connect()

    conn.execute(
        "DELETE FROM watchlist WHERE ticker=?",
        (ticker.upper(),)
    )

    conn.commit()
    conn.close()

    return {
        "status": "ok",
        "ticker": ticker.upper()
    }
