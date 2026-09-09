"""Conservative pre-listing profile for verified NordicSignal IPO candidates."""
from datetime import datetime, timezone

import extra_api
from database import connect
from providers import YahooProvider
import ipo_document_facts_runtime as document_facts_runtime

PROFILE_VERSION = "ipo_prelisting_profile_v2"
_REQUIRED_FIELDS = ("listing_terms", "valuation", "profitability", "balance_sheet", "ownership", "capital_use")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _num(value):
    return float(value) if isinstance(value, (int, float)) else None


def _candidate(candidate_id):
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM ipo_candidates WHERE candidate_id=?", (str(candidate_id),)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _research_for(candidate, provider=None):
    ticker = str((candidate or {}).get("ticker") or "").strip().upper()
    if not ticker:
        return None, "ticker_unavailable"
    try:
        return (provider or YahooProvider()).research(ticker), "available"
    except Exception:
        return None, "not_yet_available"


def _financial_profile(research):
    financial = (research or {}).get("financialData") or {}
    stats = (research or {}).get("defaultKeyStatistics") or {}
    detail = (research or {}).get("summaryDetail") or {}
    revenue = _num(financial.get("totalRevenue")); ebitda = _num(financial.get("ebitda"))
    net_income = _num(financial.get("netIncomeToCommon")); debt = _num(financial.get("totalDebt"))
    fcf = _num(financial.get("freeCashflow")); shares = _num(stats.get("sharesOutstanding"))
    market_cap = _num(detail.get("marketCap"))
    return {
        "revenue_nok": revenue, "ebitda_nok": ebitda, "net_income_nok": net_income,
        "free_cashflow_nok": fcf, "total_debt_nok": debt, "shares_outstanding": shares,
        "market_cap_nok": market_cap, "profitable": (net_income > 0) if net_income is not None else None,
        "ebitda_margin_pct": round(ebitda / revenue * 100.0, 2) if revenue and ebitda is not None else None,
    }


def build_profile(candidate, provider=None, research=None, document_facts=None):
    candidate = dict(candidate or {})
    if research is None:
        research, market_data_status = _research_for(candidate, provider=provider)
    else:
        market_data_status = "provided"
    if document_facts is None:
        try:
            document_facts = document_facts_runtime.collect(candidate)
        except Exception:
            document_facts = {"status": "unavailable", "facts": {}, "documents": []}
    doc = (document_facts or {}).get("facts") or {}
    financial = _financial_profile(research)
    offer_price = _num(candidate.get("offer_price_nok"))
    shares = financial.get("shares_outstanding")
    implied_market_cap = offer_price * shares if offer_price is not None and shares else None
    revenue = financial.get("revenue_nok"); ebitda = financial.get("ebitda_nok")

    ownership_known = doc.get("founder_retention_pct") is not None or doc.get("lockup_months") is not None
    capital_known = any(doc.get(k) not in (None, "") for k in ("new_capital_nok", "secondary_sale_nok", "total_offer_size_nok", "use_of_proceeds"))
    evidence = {
        "listing_terms": bool(candidate.get("market") and (candidate.get("expected_listing_date_text") or offer_price is not None)),
        "valuation": implied_market_cap is not None,
        "profitability": financial.get("net_income_nok") is not None or ebitda is not None,
        "balance_sheet": financial.get("total_debt_nok") is not None,
        "ownership": ownership_known,
        "capital_use": capital_known,
    }
    known = sum(1 for key in _REQUIRED_FIELDS if evidence.get(key)); coverage_pct = round(known / len(_REQUIRED_FIELDS) * 100.0, 1)
    if coverage_pct < 50:
        assessment, status = "Utilstrekkelig data for investeringsvurdering", "insufficient"
    elif coverage_pct < 80:
        assessment, status = "Delvis profil – krever mer dokumentasjon", "partial"
    else:
        assessment, status = "Datagrunnlag klart for separat IPO-vurdering", "profile_ready"

    valuation = {
        "offer_price_nok": offer_price,
        "implied_market_cap_nok": implied_market_cap,
        "price_to_sales_at_offer": round(implied_market_cap / revenue, 3) if implied_market_cap is not None and revenue else None,
        "ev_to_ebitda_at_offer": None,
        "note": "Offer-price valuation is reported only when shares and fundamentals are independently available.",
    }
    if implied_market_cap is not None and financial.get("total_debt_nok") is not None and ebitda and ebitda > 0:
        valuation["ev_to_ebitda_at_offer"] = round((implied_market_cap + financial["total_debt_nok"]) / ebitda, 3)

    ownership = {
        "founder_retention_pct": doc.get("founder_retention_pct"),
        "lockup_months": doc.get("lockup_months"),
        "status": "verified_partial" if ownership_known else "unknown",
    }
    offering = {
        "new_capital_nok": doc.get("new_capital_nok"),
        "secondary_sale_nok": doc.get("secondary_sale_nok"),
        "total_offer_size_nok": doc.get("total_offer_size_nok"),
        "new_shares": doc.get("new_shares"),
        "existing_shares_offered": doc.get("existing_shares_offered"),
        "use_of_proceeds": doc.get("use_of_proceeds"),
        "status": "verified_partial" if capital_known else "unknown",
    }
    return {
        "version": PROFILE_VERSION, "candidate_id": candidate.get("candidate_id"), "company": candidate.get("company"),
        "ticker": candidate.get("ticker"), "market": candidate.get("market"), "listing_type": candidate.get("listing_type"),
        "expected_listing_date_text": candidate.get("expected_listing_date_text"), "source_url": candidate.get("source_url"),
        "market_data_status": market_data_status, "financials": financial, "valuation": valuation,
        "ownership": ownership, "offering": offering,
        "documents": (document_facts or {}).get("documents") or [],
        "document_status": (document_facts or {}).get("status"),
        "coverage": {"known": known, "total": len(_REQUIRED_FIELDS), "pct": coverage_pct, "fields": evidence},
        "status": status, "assessment": assessment,
        "policy": "Pre-listing context only. No stock-score change, no threshold tuning and no investment recommendation; verified document facts remain separate from the stock score.",
        "generated_at": _now(),
    }


def profile(candidate_id, provider=None):
    row = _candidate(candidate_id)
    if not row:
        return {"status": "not_found", "candidate_id": str(candidate_id), "policy": "No score changes."}
    return build_profile(row, provider=provider)


def install():
    if getattr(extra_api, "_ipo_prelisting_profile_runtime_v2", False):
        return
    original_install = extra_api.install; provider = YahooProvider()
    def patched_install(app):
        original_install(app)
        @app.get("/api/ipo-radar/profile/{candidate_id}")
        def ipo_prelisting_profile(candidate_id: str):
            return profile(candidate_id, provider=provider)
    extra_api.install = patched_install; extra_api._ipo_prelisting_profile_runtime_v2 = True

install()
