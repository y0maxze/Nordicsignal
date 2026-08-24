from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import connect, init_db
from scoring import signal_label
from providers import YahooProvider, NordicRegulatoryProvider

# Render may not auto-load Python sitecustomize depending on the working directory.
# Load the backend insider patch explicitly after providers is imported so the
# exact NordicRegulatoryProvider class used by this API is patched.
try:
    import sitecustomize as _nordicsignal_runtime_patch
except Exception:
    _nordicsignal_runtime_patch = None

app = FastAPI(title="NordicSignal API", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

UNIVERSE = [("LSG", "Lerøy Seafood", "Seafood"), ("MPCC", "MPC Container Ships", "Shipping"), ("ELO", "Elopak", "Packaging"), ("PEXIP", "Pexip", "Technology"), ("XPLRA", "Xplora Technologies", "Technology"), ("EQNR", "Equinor", "Energy"), ("DNB", "DNB", "Financials"), ("NHY", "Norsk Hydro", "Materials"), ("YAR", "Yara International", "Chemicals"), ("MOWI", "Mowi", "Seafood"), ("SALM", "SalMar", "Seafood"), ("GJF", "Gjensidige Forsikring", "Financials"), ("TEL", "Telenor", "Telecom"), ("ORK", "Orkla", "Consumer"), ("TOM", "Tomra Systems", "Industrials"), ("KOG", "Kongsberg Gruppen", "Industrials"), ("NAS", "Norwegian Air Shuttle", "Airlines"), ("AKRBP", "Aker BP", "Energy"), ("AKSO", "Aker Solutions", "Energy"), ("SUBC", "Subsea 7", "Energy"), ("BWLPG", "BW LPG", "Shipping"), ("HAUTO", "Höegh Autoliners", "Shipping"), ("GOGL", "Golden Ocean", "Shipping"), ("VAR", "Vår Energi", "Energy")]
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


def sentiment_score(r):
    q = r.get("price", {}) or {}; change = raw(q.get("change_pct")); points = 8.0
    if change is not None: points += 4 if change >= 2 else 2 if change >= 0 else -2 if change <= -2 else 0
    return clamp_score(points, 0, 15)


def score_result(ticker, name, sector, research, insider, short_data=None):
    m = fundamental_metrics(research); f = fundamentals_score(m); v = valuation_score(research); s = sentiment_score(research)
    i = None
    if insider and insider.get("status") == "live":
        buys, sells = insider.get("buy_count", 0), insider.get("sell_count", 0); i = 25 if buys > sells else 15 if buys == sells and buys else 5 if sells > buys else 0
    verified = 75 + (25 if i is not None else 0)
    total = f + v + s + (i or 0)
    return {"ticker": ticker, "name": name, "sector": sector, "score": total, "fundamentals": f, "insider": i, "valuation": v, "sentiment": s, "signal": signal_label(total), "score_source": "live" if verified == 100 else "partial_live", "live_verified": verified == 100, "partial_live": verified < 100, "score_updated_at": datetime.now(timezone.utc).isoformat(), "coverage": {"verified_points": verified, "total_points": 100, "missing": [] if verified == 100 else ["insider"]}}
