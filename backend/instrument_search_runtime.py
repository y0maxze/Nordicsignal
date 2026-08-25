"""Resilient instrument search for Holdings.

Yahoo's search host can intermittently reject one edge/host.  The portfolio runtime
owns the API route; this module replaces only its search implementation so the
existing route, metadata and allocation code stay canonical.
"""
import logging

import portfolio_instruments_runtime as portfolio

log = logging.getLogger("nordicsignal.instrument_search")


def _normalize_rows(data, limit):
    out, seen = [], set()
    for row in (data or {}).get("quotes") or []:
        quote_type = str(row.get("quoteType") or "").upper().strip()
        symbol = str(row.get("symbol") or "").strip()
        if quote_type not in portfolio._ALLOWED_QUOTE_TYPES or not symbol or symbol in seen:
            continue
        seen.add(symbol)
        out.append({
            "symbol": symbol,
            "ticker": symbol,
            "name": row.get("longname") or row.get("shortname") or symbol,
            "quote_type": quote_type,
            "asset_class": portfolio.asset_class_for(quote_type),
            "exchange": row.get("exchDisp") or row.get("exchange"),
            "currency": row.get("currency"),
            "market": row.get("market"),
            "score": row.get("score"),
            "source": "Yahoo Finance Search",
        })
        if len(out) >= limit:
            break
    return out


def resilient_search_instruments(provider, query, limit=12):
    query = portfolio._clean(query)
    if not query:
        return []
    limit = max(1, min(int(limit or 12), 25))
    params = {
        "q": query,
        "quotesCount": max(limit * 4, 30),
        "newsCount": 0,
        "enableFuzzyQuery": "true",
        "quotesQueryId": "tss_match_phrase_query",
        "region": "NO",
        "lang": "en-US",
    }
    errors = []
    bases = tuple(dict.fromkeys(getattr(provider, "BASES", ()) or (provider.BASE,)))
    for base in bases:
        url = f"{base}/v1/finance/search"
        try:
            # Use the provider's hardened request path so headers, impersonation,
            # status handling and future transport fixes are shared with quotes.
            data = provider._get(url, params)
            rows = _normalize_rows(data, limit)
            if rows:
                return rows
        except Exception as exc:
            errors.append(f"{base}: {exc}")
            log.warning("Instrument search host failed for %r via %s: %s", query, base, exc)

    # A zero-result query is legitimate.  Only raise when every host actually
    # failed; this lets the UI distinguish 'no matches' from provider downtime.
    if errors and len(errors) == len(bases):
        raise RuntimeError("; ".join(errors))
    return []


def install():
    portfolio.search_instruments = resilient_search_instruments
