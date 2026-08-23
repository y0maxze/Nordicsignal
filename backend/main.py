from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from scoring import calculate_score, signal_label

app = FastAPI(title="NordicSignal API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

stocks = [
    {"ticker":"LSG","name":"Lerøy Seafood","sector":"Seafood","price":0,"change_pct":0,
     "fundamentals":34,"insider":24,"valuation":16,"sentiment":12,"short_score":4},
    {"ticker":"MPCC","name":"MPCC","sector":"Shipping","price":0,"change_pct":0,
     "fundamentals":36,"insider":15,"valuation":17,"sentiment":12,"short_score":4},
    {"ticker":"ELO","name":"Elopak","sector":"Packaging","price":0,"change_pct":0,
     "fundamentals":30,"insider":23,"valuation":16,"sentiment":12,"short_score":3},
    {"ticker":"PEXIP","name":"Pexip","sector":"Technology","price":0,"change_pct":0,
     "fundamentals":33,"insider":18,"valuation":15,"sentiment":11,"short_score":3},
    {"ticker":"XPLRA","name":"Xplora","sector":"Technology","price":0,"change_pct":0,
     "fundamentals":32,"insider":18,"valuation":14,"sentiment":6,"short_score":2},
]

for s in stocks:
    s["score"] = calculate_score(s["fundamentals"], s["insider"], s["valuation"], s["sentiment"])
    s["signal"] = signal_label(s["score"])

@app.get("/api/health")
def health():
    return {"status":"ok","service":"NordicSignal API"}

@app.get("/api/stocks")
def get_stocks():
    return {"items": sorted(stocks, key=lambda x: x["score"], reverse=True)}

@app.get("/api/stocks/{ticker}")
def get_stock(ticker: str):
    for stock in stocks:
        if stock["ticker"].lower() == ticker.lower():
            return stock
    return {"error":"Ticker not found"}

@app.get("/api/radar")
def radar():
    return {
        "items": [
            {"ticker":"LSG","event":"Insider + institutional activity","strength":"strong"},
            {"ticker":"MPCC","event":"Earnings watch","strength":"strong"},
            {"ticker":"ELO","event":"Insider cluster","strength":"strong"},
            {"ticker":"XPLRA","event":"Short pressure","strength":"risk"},
        ]
    }
