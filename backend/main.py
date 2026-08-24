from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import threading
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import connect, init_db
from scoring import signal_label
from providers import YahooProvider, NordicRegulatoryProvider

# Render does not always auto-load sitecustomize. Load the backend patch explicitly
# after providers so it patches the exact NordicRegulatoryProvider class in use.
try:
    import sitecustomize as _nordicsignal_runtime_patch
except Exception:
    _nordicsignal_runtime_patch = None

app = FastAPI(title="NordicSignal API", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Golden Ocean completed its merger with CMB.TECH on 20 Aug 2025 and GOGL
# stopped trading on 19 Aug 2025. The live Oslo listing is now CMB.TECH's
# CMBTO ticker, so the universe must not keep a delisted GOGL row.
UNIVERSE = [("LSG", "Lerøy Seafood", "Seafood"), ("MPCC", "MPC Container Ships", "Shipping"), ("ELO", "Elopak", "Packaging"), ("PEXIP", "Pexip", "Technology"), ("XPLRA", "Xplora Technologies", "Technology"), ("EQNR", "Equinor", "Energy"), ("DNB", "DNB", "Financials"), ("NHY", "Norsk Hydro", "Materials"), ("YAR", "Yara International", "Chemicals"), ("MOWI", "Mowi", "Seafood"), ("SALM", "SalMar", "Seafood"), ("GJF", "Gjensidige Forsikring", "Financials"), ("TEL", "Telenor", "Telecom"), ("ORK", "Orkla", "Consumer"), ("TOM", "Tomra Systems", "Industrials"), ("KOG", "Kongsberg Gruppen", "Industrials"), ("NAS", "Norwegian Air Shuttle", "Airlines"), ("AKRBP", "Aker BP", "Energy"), ("AKSO", "Aker Solutions", "Energy"), ("SUBC", "Subsea 7", "Energy"), ("BWLPG", "BW LPG", "Shipping"), ("HAUTO", "Höegh Autoliners", "Shipping"), ("CMBTO", "CMB.TECH", "Shipping"), ("VAR", "Vår Energi", "Energy")]
TICKERS = [x[0] for x in UNIVERSE]
provider = YahooProvider()
regulatory = NordicRegulatoryProvider()


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
    values = timeseries_map(series).get(name, []); candidates = []
    for item in values if isinstance(values, list) else []:
        if not isinstance(item, dict): continue
        value = item.get("reportedValue")
        if isinstance(value, dict): value = value.get("raw")
        if isinstance(value, (int, float)): candidates.append((item.get("asOfDate", ""), float(value)))
    return sorted(candidates, key=lambda x: x[0])[-1][1] if candidates else None


def annual_values(series, name):
    values = timeseries_map(series).get(name, []); out = []
    for item in values if isinstance(values, list) else []:
        if not isinstance(item, dict): continue
        value = item.get("reportedValue")
        if isinstance(value, dict): value = value.get("raw")
        if isinstance(value, (int, float)): out.append((item.get("asOfDate", ""), float(value)))
    return sorted(out, key=lambda x: x[0], reverse=True)


def fundamental_metrics(r):
    f = r.get("fundamentals", {}) or {}; revenue, ebitda, net_income = f.get("revenue"), f.get("ebitda"), f.get("net_income"); fcf, debt, equity = f.get("free_cashflow"), f.get("debt"), f.get("equity")
    revs = annual_values(r.get("_annual_series", {}) or {}, "annualTotalRevenue")
    growth = ((revs[0][1] / revs[1][1]) - 1) if len(revs) >= 2 and revs[1][1] else None
    return {"revenue": revenue, "ebitda": ebitda, "net_income": net_income, "free_cashflow": fcf, "debt": debt, "equity": equity, "revenue_growth": growth, "ebitda_margin": (ebitda / revenue) if ebitda is not None and revenue else None, "roe": (net_income / equity) if net_income is not None and equity else None, "debt_to_equity": (debt / equity * 100) if debt is not None and equity else None, "fcf_margin": (fcf / revenue) if fcf is not None and revenue else None}


def fundamentals_score(m):
    points = 20.0; margin, roe, growth, debt_eq, fcf = m["ebitda_margin"], m["roe"], m["revenue_growth"], m["debt_to_equity"], m["free_cashflow"]
    if margin is not None: points += 6 if margin >= .15 else 4 if margin >= .10 else 2 if margin >= .05 else -2 if margin < 0 else 0
    if roe is not None: points += 5 if roe >= .12 else 3 if roe >= .08 else 1 if roe >= .05 else -2
    if growth is not None: points += 5 if growth >= .10 else 3 if growth >= .03 else 1 if growth >= 0 else -2
    if debt_eq is not None: points += 3 if debt_eq < 60 else 1 if debt_eq < 100 else 0 if debt_eq < 160 else -3
    if fcf is not None and fcf > 0: points += 1
    return clamp_score(points, 0, 40)


def valuation_score(r):
    sd, ks = r.get("summaryDetail", {}) or {}, r.get("defaultKeyStatistics", {}) or {}; pe, pb, ev_ebitda = raw(sd.get("trailingPE"), raw(ks.get("trailingPE"))), raw(ks.get("priceToBook")), raw(ks.get("enterpriseToEbitda")); points = 10.0
    if pe is not None and pe > 0: points += 4 if pe < 15 else 2 if pe < 25 else -2
    if pb is not None and pb > 0: points += 3 if pb < 2 else 1 if pb < 4 else -1
    if ev_ebitda is not None and ev_ebitda > 0: points += 2 if ev_ebitda < 12 else 0 if ev_ebitda < 20 else -1
    return clamp_score(points, 0, 20)


def sentiment_score(history):
    closes = [x["close"] for x in history if x.get("close") is not None]
    if len(closes) < 5: return 7
    start, end = closes[-min(60, len(closes))], closes[-1]; ret = ((end - start) / start) if start else 0
    return clamp_score(7.5 + ret * 30, 0, 15)


def insider_score(data):
    # A successful official Euronext query with no recent disclosures is still
    # verified insider coverage; it gets the neutral baseline rather than
    # incorrectly downgrading the whole stock to partial_live.
    if not data or data.get("status") not in ("live", "no_recent_disclosures"): return None
    buys, sells = int(data.get("buy_count") or 0), int(data.get("sell_count") or 0)
    if buys == 0 and sells == 0: return 12
    return clamp_score(12 + (buys - sells) * 2.5, 0, 25)


def seed_db():
    conn = connect(); now = datetime.now(timezone.utc).isoformat()
    for ticker, name, sector in UNIVERSE:
        conn.execute("INSERT OR IGNORE INTO stocks(ticker,name,sector,exchange,active) VALUES(?,?,?,?,1)", (ticker, name, sector, "Oslo Børs"))
        conn.execute("UPDATE stocks SET name=?,sector=?,exchange=?,active=1 WHERE ticker=?", (name, sector, "Oslo Børs", ticker))
        if not conn.execute("SELECT 1 FROM scores WHERE ticker=? LIMIT 1", (ticker,)).fetchone(): conn.execute("INSERT INTO scores(ticker,fundamentals,insider,valuation,sentiment,total,created_at,source) VALUES(?,?,?,?,?,?,?,?)", (ticker, 20, 12, 10, 8, 50, now, "seed"))
    placeholders=','.join('?' for _ in TICKERS)
    conn.execute(f"UPDATE stocks SET active=0 WHERE ticker NOT IN ({placeholders})", TICKERS)
    conn.commit(); conn.close()


def refresh_one(ticker, include_insider=True):
    ticker = ticker.upper(); row = next((x for x in UNIVERSE if x[0] == ticker), None); company_name = row[1] if row else ticker
    try:
        research, history = provider.research(ticker), provider.historical(ticker, "3m")
        if not research: raise RuntimeError("Yahoo Finance returned no research data")
        if len(history) < 5: raise RuntimeError("Yahoo Finance returned insufficient historical data")
        metrics = fundamental_metrics(research); f, v, s = fundamentals_score(metrics), valuation_score(research), sentiment_score(history)
        if include_insider:
            try: insider = regulatory.insider(ticker, company_name)
            except Exception as exc: insider = {"status": "unavailable", "error": str(exc), "items": []}
        else:
            insider = {"status": "deferred", "items": [], "source": "Euronext Oslo Børs / Oslo Børs Newspoint"}
        i = insider_score(insider); verified_max, verified_sum = 75 + (25 if i is not None else 0), f + v + s + (i or 0); normalized = clamp_score((verified_sum / verified_max) * 100, 0, 100); source, now = ("live" if i is not None else "partial_live"), datetime.now(timezone.utc).isoformat()
        conn = connect(); conn.execute("INSERT INTO scores(ticker,fundamentals,insider,valuation,sentiment,total,created_at,source) VALUES(?,?,?,?,?,?,?,?)", (ticker, f, i or 0, v, s, normalized, now, source)); conn.commit(); conn.close()
        return {"ticker": ticker, "name": company_name, "score": normalized, "source": source, "live_verified": source == "live", "coverage": {"verified_points": verified_max, "total_points": 100, "missing": [] if i is not None else ["insider"]}, "updated_at": now, "components": {"fundamentals": f, "fundamentals_max": 40, "insider": i, "insider_max": 25, "valuation": v, "valuation_max": 20, "sentiment": s, "sentiment_max": 15}, "metrics": metrics, "insider": insider}
    except Exception as exc: return {"ticker": ticker, "source": "stored", "live_verified": False, "error": str(exc)}


def refresh_all(limit=None, include_insider=True):
    tickers = TICKERS[:limit] if limit else TICKERS; results = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(refresh_one, ticker, include_insider): ticker for ticker in tickers}
        for future in as_completed(futures): results.append(future.result())
    return sorted(results, key=lambda x: x.get("ticker", ""))


def _background_live_refresh():
    # Boot quickly with a Yahoo-only snapshot, then replace it with the full
    # coverage-aware live snapshot once Render has finished accepting traffic.
    time.sleep(2)
    try:
        refresh_all(include_insider=True)
    except Exception:
        pass


@app.on_event("startup")
def startup():
    init_db(); seed_db(); refresh_all(include_insider=False)
    threading.Thread(target=_background_live_refresh, daemon=True, name="live-refresh").start()


@app.get("/api/health")
def health(): return {"status": "ok", "service": "NordicSignal API", "version": "3.0.0", "providers": ["Yahoo Finance", "Finanstilsynet SSR", "Euronext Oslo Børs"], "score_policy": "coverage-aware live score"}

@app.get("/api/refresh")
def refresh(all: bool = True): return {"status": "ok", "results": refresh_all(include_insider=True) if all else refresh_all(limit=8, include_insider=True)}

@app.get("/api/verification")
def verification():
    conn = connect(); rows = conn.execute("SELECT s.ticker,s.name,sc.fundamentals,sc.insider,sc.valuation,sc.sentiment,sc.total,sc.created_at,COALESCE(sc.source,'stored') source FROM stocks s JOIN scores sc ON sc.id=(SELECT MAX(id) FROM scores x WHERE x.ticker=s.ticker) WHERE s.active=1 ORDER BY s.ticker").fetchall(); conn.close(); now = datetime.now(timezone.utc); items = []
    for r in rows:
        try: updated = datetime.fromisoformat(r["created_at"]); updated = updated if updated.tzinfo else updated.replace(tzinfo=timezone.utc); age = max(0, int((now - updated).total_seconds()))
        except Exception: age = None
        source = r["source"]; verified_points = 100 if source == "live" else 75 if source == "partial_live" else 0
        items.append({"ticker": r["ticker"], "name": r["name"], "score": r["total"], "source": source, "live_verified": source == "live", "partial_live": source == "partial_live", "updated_at": r["created_at"], "age_seconds": age, "coverage": {"verified_points": verified_points, "total_points": 100}, "components": {"fundamentals": r["fundamentals"], "insider": r["insider"] if source == "live" else None, "valuation": r["valuation"], "sentiment": r["sentiment"]}})
    return {"status": "ok", "items": items, "all_live_verified": bool(items) and all(x["live_verified"] for x in items), "all_scores_live_or_partial": bool(items) and all(x["source"] in ("live", "partial_live") for x in items)}

@app.get("/api/stocks")
def stocks():
    conn = connect(); rows = conn.execute("SELECT s.ticker,s.name,s.sector,sc.fundamentals,sc.insider,sc.valuation,sc.sentiment,sc.total,sc.created_at,COALESCE(sc.source,'stored') source FROM stocks s JOIN scores sc ON sc.id=(SELECT MAX(id) FROM scores x WHERE x.ticker=s.ticker) WHERE s.active=1 ORDER BY sc.total DESC").fetchall(); conn.close()
    return {"items": [{"ticker": r["ticker"], "name": r["name"], "sector": r["sector"], "score": r["total"], "fundamentals": r["fundamentals"], "insider": r["insider"] if r["source"] == "live" else None, "valuation": r["valuation"], "sentiment": r["sentiment"], "signal": signal_label(r["total"]), "score_source": r["source"], "live_verified": r["source"] == "live", "partial_live": r["source"] == "partial_live", "score_updated_at": r["created_at"]} for r in rows]}

@app.get("/api/search")
def search(q: str = ""):
    q = q.strip()
    if not q: return {"items": []}
    conn = connect(); rows = conn.execute("SELECT ticker,name,sector,exchange FROM stocks WHERE active=1 AND (ticker LIKE ? OR name LIKE ?) ORDER BY name LIMIT 30", (f"%{q}%", f"%{q}%")).fetchall(); conn.close(); return {"items": [dict(r) for r in rows]}

@app.get("/api/stocks/{ticker}")
def stock(ticker: str):
    conn = connect(); r = conn.execute("SELECT s.ticker,s.name,s.sector,sc.fundamentals,sc.insider,sc.valuation,sc.sentiment,sc.total,sc.created_at,COALESCE(sc.source,'stored') source FROM stocks s JOIN scores sc ON sc.ticker=s.ticker WHERE s.ticker=? ORDER BY sc.id DESC LIMIT 1", (ticker.upper(),)).fetchone(); conn.close()
    if not r: return {"error": "Ticker not found"}
    return {"ticker": r["ticker"], "name": r["name"], "sector": r["sector"], "score": r["total"], "fundamentals": r["fundamentals"], "insider": r["insider"] if r["source"] == "live" else None, "valuation": r["valuation"], "sentiment": r["sentiment"], "signal": signal_label(r["total"]), "score_source": r["source"], "live_verified": r["source"] == "live", "partial_live": r["source"] == "partial_live", "score_updated_at": r["created_at"]}

@app.get("/api/quote/{ticker}")
def quote(ticker: str):
    try:
        data = provider.quote(ticker); conn = connect(); conn.execute("INSERT INTO quotes(ticker,price,change_pct,volume,captured_at) VALUES(?,?,?,?,?)", (ticker.upper(), data.get("price"), data.get("change_pct"), data.get("volume"), data.get("captured_at") or datetime.now(timezone.utc).isoformat())); conn.commit(); conn.close(); return data
    except Exception as exc: return {"ticker": ticker.upper(), "source": "unavailable", "error": str(exc)}

@app.get("/api/history/{ticker}")
def history(ticker: str, period: str = "1y"):
    try: return {"ticker": ticker.upper(), "period": period, "items": provider.historical(ticker, period)}
    except Exception as exc: return {"ticker": ticker.upper(), "period": period, "items": [], "error": str(exc)}

@app.get("/api/research/{ticker}")
def research(ticker: str):
    try: r = provider.research(ticker); return {"ticker": ticker.upper(), "data": r, "source": r.get("source", "Yahoo Finance")}
    except Exception as exc: return {"ticker": ticker.upper(), "data": {}, "source": "unavailable", "error": str(exc)}

@app.get("/api/fundamentals/{ticker}")
def fundamentals(ticker: str):
    try:
        r = provider.fundamentals(ticker); series = r.get("series", []) if isinstance(r, dict) else []
        return {"ticker": ticker.upper(), "source": r.get("source", "Yahoo Finance Timeseries"), "captured_at": r.get("captured_at"), "data": {"revenue": latest_timeseries_value(series, "annualTotalRevenue"), "ebitda": latest_timeseries_value(series, "annualEBITDA"), "ebit": latest_timeseries_value(series, "annualEBIT"), "net_income": latest_timeseries_value(series, "annualNetIncome"), "eps": latest_timeseries_value(series, "annualDilutedEPS"), "operating_cashflow": latest_timeseries_value(series, "annualOperatingCashFlow"), "free_cashflow": latest_timeseries_value(series, "annualFreeCashFlow"), "debt": latest_timeseries_value(series, "annualTotalDebt"), "equity": latest_timeseries_value(series, "annualStockholdersEquity"), "gross_profit": latest_timeseries_value(series, "annualGrossProfit"), "operating_income": latest_timeseries_value(series, "annualOperatingIncome"), "pretax_income": latest_timeseries_value(series, "annualPretaxIncome")}}
    except Exception as exc: return {"ticker": ticker.upper(), "source": "unavailable", "data": {}, "error": str(exc)}

@app.get("/api/score-explanation/{ticker}")
def score_explanation(ticker: str):
    try:
        r = provider.research(ticker); metrics = fundamental_metrics(r); reasons = []
        if metrics["free_cashflow"] is not None and metrics["free_cashflow"] > 0: reasons.append({"type": "positive", "metric": "free_cashflow", "value": metrics["free_cashflow"], "text": "Free cash flow is positive."})
        if metrics["fcf_margin"] is not None and metrics["fcf_margin"] >= .05: reasons.append({"type": "positive", "metric": "fcf_margin", "value": metrics["fcf_margin"], "text": "Free cash flow margin is at least 5%."})
        if metrics["ebitda_margin"] is not None and metrics["ebitda_margin"] >= .10: reasons.append({"type": "positive", "metric": "ebitda_margin", "value": metrics["ebitda_margin"], "text": "EBITDA margin is at least 10%."})
        elif metrics["ebitda_margin"] is not None and metrics["ebitda_margin"] < .05: reasons.append({"type": "negative", "metric": "ebitda_margin", "value": metrics["ebitda_margin"], "text": "EBITDA margin is below 5%."})
        if metrics["revenue_growth"] is not None and metrics["revenue_growth"] < 0: reasons.append({"type": "negative", "metric": "revenue_growth", "value": metrics["revenue_growth"], "text": "Revenue growth is negative."})
        if metrics["revenue_growth"] is not None and metrics["revenue_growth"] >= .10: reasons.append({"type": "positive", "metric": "revenue_growth", "value": metrics["revenue_growth"], "text": "Revenue growth is above 10%."})
        if metrics["roe"] is not None and metrics["roe"] >= .12: reasons.append({"type": "positive", "metric": "roe", "value": metrics["roe"], "text": "ROE is strong."})
        elif metrics["roe"] is not None and metrics["roe"] < .05: reasons.append({"type": "negative", "metric": "roe", "value": metrics["roe"], "text": "ROE is relatively low."})
        if metrics["debt_to_equity"] is not None and metrics["debt_to_equity"] > 160: reasons.append({"type": "negative", "metric": "debt_to_equity", "value": metrics["debt_to_equity"], "text": "Debt-to-equity is high."})
        try: insider = regulatory.insider(ticker)
        except Exception: insider = {"status": "unavailable", "items": []}
        i_score = insider_score(insider)
        return {"ticker": ticker.upper(), "score_source": "live" if i_score is not None else "partial_live", "coverage": {"verified_points": 100 if i_score is not None else 75, "total_points": 100, "missing": [] if i_score is not None else ["insider"]}, "metrics": metrics, "insider": insider, "reasons": reasons, "data_quality": {"fundamentals": "live", "valuation": "live", "sentiment": "live", "insider": "live" if i_score is not None else "unavailable"}}
    except Exception as exc: return {"ticker": ticker.upper(), "score_source": "unavailable", "reasons": [], "error": str(exc)}

@app.get("/api/insider/{ticker}")
def insider(ticker: str):
    try: return regulatory.insider(ticker)
    except Exception as exc: return {"ticker": ticker.upper(), "items": [], "source": "unavailable", "status": "unavailable", "error": str(exc)}

@app.get("/api/short/{ticker}")
def short(ticker: str):
    try:
        conn = connect(); row = conn.execute("SELECT name FROM stocks WHERE ticker=?", (ticker.upper(),)).fetchone(); conn.close(); return regulatory.short(ticker, row["name"] if row else "")
    except Exception as exc: return {"ticker": ticker.upper(), "items": [], "source": "unavailable", "status": "unavailable", "error": str(exc)}

@app.get("/api/radar")
def radar():
    conn = connect(); rows = conn.execute("SELECT ticker,total FROM scores WHERE id IN (SELECT MAX(id) FROM scores GROUP BY ticker) ORDER BY total DESC LIMIT 20").fetchall(); conn.close(); items = []
    for r in rows:
        score = r["total"]; event = "Strong signal" if score >= 85 else "Watch signal" if score >= 75 else "Neutral signal" if score >= 60 else "Risk signal"; strength = "strong" if score >= 85 else "watch" if score >= 75 else "neutral" if score >= 60 else "risk"; items.append({"ticker": r["ticker"], "score": score, "event": event, "strength": strength})
    return {"items": items}

@app.get("/api/markets")
def markets():
    conn = connect(); rows = conn.execute("SELECT sector,COUNT(*) count,ROUND(AVG(total),1) avg_score FROM stocks s JOIN scores sc ON sc.id=(SELECT MAX(id) FROM scores x WHERE x.ticker=s.ticker) WHERE s.active=1 GROUP BY sector ORDER BY avg_score DESC").fetchall(); conn.close(); return {"items": [dict(r) for r in rows]}

@app.get("/api/watchlist")
def get_watchlist():
    conn = connect(); rows = conn.execute("SELECT w.ticker,s.name FROM watchlist w JOIN stocks s ON s.ticker=w.ticker ORDER BY w.created_at DESC").fetchall(); conn.close(); return {"items": [dict(r) for r in rows]}

@app.post("/api/watchlist/{ticker}")
def add_watchlist(ticker: str):
    conn = connect(); conn.execute("INSERT OR IGNORE INTO watchlist(ticker,created_at) VALUES(?,?)", (ticker.upper(), datetime.now(timezone.utc).isoformat())); conn.commit(); conn.close(); return {"status": "ok", "ticker": ticker.upper()}

@app.delete("/api/watchlist/{ticker}")
def remove_watchlist(ticker: str):
    conn = connect(); conn.execute("DELETE FROM watchlist WHERE ticker=?", (ticker.upper(),)); conn.commit(); conn.close(); return {"status": "ok", "ticker": ticker.upper()}
