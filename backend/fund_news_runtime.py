"""Enrich generic fund/ETF news without inventing instrument-specific headlines.

Yahoo's exact fund-name search can be sparse. For funds and ETFs we therefore try the
full product name, symbol and issuer-style name variants, deduplicate the results, and
label each item as direct fund/ETF news or broader relevant market/issuer context.
Every item keeps its original publisher link.
"""
from datetime import datetime, timezone
import re

import extra_api
import instrument_detail_runtime

_STOP = {
    "aksje", "aksjeglobal", "global", "indeks", "index", "fund", "fond", "etf",
    "class", "klasse", "n", "a", "b", "acc", "dist", "ucits", "the", "and",
}


def _tokens(text):
    return [
        x.lower() for x in re.findall(r"[A-Za-zÀ-ÿ0-9]+", str(text or ""))
        if len(x) >= 3 and x.lower() not in _STOP
    ]


def _query_variants(symbol, name):
    name = " ".join(str(name or "").split()).strip()
    symbol = str(symbol or "").strip()
    out = []
    for q in (name, symbol):
        if q and q.lower() not in {x.lower() for x in out}:
            out.append(q)
    words = name.split()
    if len(words) >= 2:
        issuer = " ".join(words[:2])
        if issuer.lower() not in {x.lower() for x in out}:
            out.append(issuer)
    elif words and words[0].lower() not in {x.lower() for x in out}:
        out.append(words[0])
    return out[:3]


def _fetch_news(provider, query, count=20):
    params = {
        "q": query,
        "quotesCount": 0,
        "newsCount": max(8, min(int(count or 20), 40)),
        "enableFuzzyQuery": "true",
    }
    last = None
    for base in tuple(dict.fromkeys(getattr(provider, "BASES", ()) or (provider.BASE,))):
        try:
            data = provider._get(f"{base}/v1/finance/search", params)
            return data.get("news") or []
        except Exception as exc:
            last = exc
    if last:
        raise last
    return []


def _normalize_item(raw, query, name, asset_class):
    title = str(raw.get("title") or "").strip()
    if not title:
        return None
    ts = raw.get("providerPublishTime")
    published = datetime.fromtimestamp(ts, timezone.utc).isoformat() if isinstance(ts, (int, float)) else None
    title_tokens = set(_tokens(title))
    name_tokens = set(_tokens(name))
    overlap = len(title_tokens & name_tokens)
    direct = overlap >= 1
    return {
        "title": title,
        "publisher": raw.get("publisher"),
        "published_at": published,
        "url": raw.get("link"),
        "category": asset_class if direct else "Markedsnyhet",
        "news_scope": "direct" if direct else "context",
        "query_used": query,
        "source": "Yahoo Finance Search",
    }


def enriched_instrument_news(provider, symbol, name=None, limit=20):
    exact = instrument_detail_runtime._search_exact(provider, symbol)
    quote_type = str(exact.get("quoteType") or "").upper()
    asset_class = "Fond" if quote_type in {"MUTUALFUND", "MONEYMARKET", "CLOSEDEND_FUND"} else "ETF" if quote_type == "ETF" else None
    if asset_class is None:
        return _ORIGINAL(provider, symbol, name, limit)

    display_name = name or exact.get("longname") or exact.get("shortname") or symbol
    items, seen = [], set()
    errors = []
    for query in _query_variants(symbol, display_name):
        try:
            rows = _fetch_news(provider, query, max(limit, 16))
        except Exception as exc:
            errors.append(str(exc))
            continue
        for raw in rows:
            item = _normalize_item(raw, query, display_name, asset_class)
            if not item:
                continue
            key = (str(item.get("url") or "").strip().lower(), re.sub(r"\W+", "", item["title"].lower()))
            if key in seen:
                continue
            seen.add(key)
            items.append(item)

    # Direct product/issuer news first, then context; newest first within each group.
    items.sort(key=lambda x: (0 if x.get("news_scope") == "direct" else 1, -(datetime.fromisoformat(x["published_at"]).timestamp() if x.get("published_at") else 0)))
    return {
        "symbol": symbol,
        "query": display_name,
        "asset_class": asset_class,
        "items": items[: max(1, min(int(limit or 20), 40))],
        "status": "ok" if items else "no_relevant_news",
        "source": "Yahoo Finance Search",
        "sources": ["Yahoo Finance Search"],
        "detail": None if items else (errors[-1] if errors else "No relevant public fund/ETF news found"),
        "news_policy": "Direct fund/ETF or issuer matches are shown first; broader context is labelled Markedsnyhet.",
    }


_ORIGINAL = instrument_detail_runtime.instrument_news


def install():
    if getattr(extra_api, "_fund_news_runtime_installed", False):
        return
    instrument_detail_runtime.instrument_news = enriched_instrument_news
    extra_api._fund_news_runtime_installed = True
