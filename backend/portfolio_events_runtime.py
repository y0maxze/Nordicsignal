"""Portfolio-scoped event feed for the NordicSignal home dashboard.

The dashboard surfaces only events that matter to positions the user has entered in
Holdings. Events are enriched with a small amount of real market context so the home
brief can explain what happened instead of merely repeating a headline.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import re
import threading
import time

import extra_api
from database import connect
from providers import YahooProvider

_CACHE_LOCK = threading.Lock()
_CACHE = {"key": None, "at": 0.0, "value": None}
_CACHE_TTL = 60
_MAX_WORKERS = 2


def _route_handler(app, path):
    for route in getattr(app, "routes", []):
        if getattr(route, "path", None) == path and "GET" in (getattr(route, "methods", None) or set()):
            return getattr(getattr(route, "dependant", None), "call", None) or getattr(route, "endpoint", None)
    return None


def _canonical_event_ticker(value):
    """Map Yahoo-style Oslo symbols back to NordicSignal's canonical ticker."""
    ticker = str(value or "").strip().upper()
    if ticker.endswith(".OL"):
        return ticker[:-3]
    return ticker


def _holding_rows():
    """Return unique holdings using the canonical Oslo ticker where available.

    Holdings may contain either MPCC or MPCC.OL depending on how the instrument was
    added. News/report/insider routes use MPCC, so normalize before calling them.
    """
    conn = connect()
    try:
        holdings = conn.execute("SELECT DISTINCT ticker FROM holdings ORDER BY ticker").fetchall()
        stocks = conn.execute("SELECT ticker,name FROM stocks").fetchall()
        names = {str(row["ticker"]).upper(): row["name"] for row in stocks}
    except Exception:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass

    out = []
    seen = set()
    for row in holdings:
        raw = str(row["ticker"] or "").strip().upper()
        ticker = _canonical_event_ticker(raw)
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        out.append({
            "ticker": ticker,
            "holding_ticker": raw,
            "company_name": names.get(ticker) or raw,
            "tracked": ticker in names,
        })
    return out


def _iso(value):
    if not value:
        return None
    text = str(value).strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        if len(text) == 10 and text[4:5] == "-" and text[7:8] == "-":
            return text + "T00:00:00+00:00"
        return None


def _compact_number(value):
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if abs(n - round(n)) < 1e-9:
        return f"{int(round(n)):,}".replace(",", " ")
    return f"{n:,.2f}".replace(",", " ")


def _pct_text(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return f"{abs(value):.2f}".replace(".", ",") + " %"


def _price_text(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return f"{value:.2f}".replace(".", ",") + " kr"


def _report_name(title):
    match = re.search(r"\b(Q[1-4])\b", str(title or ""), re.I)
    if match:
        return match.group(1).upper() + "-rapporten"
    low = str(title or "").lower()
    if "annual" in low or "årsrapport" in low or "arsrapport" in low:
        return "Årsrapporten"
    if "half" in low:
        return "Halvårsrapporten"
    return "Rapporten"


def _reaction_words(change_pct):
    try:
        change = float(change_pct)
    except (TypeError, ValueError):
        return ("var omtrent uendret", "avventende", "watch")
    if change >= 0.5:
        return ("steg", "positiv", "positive")
    if change <= -0.5:
        return ("falt", "negativ", "negative")
    return ("var omtrent uendret", "avventende", "watch")


def _brief_for_event(row):
    kind = row.get("kind")
    title = str(row.get("title") or "")
    low = title.lower()
    reaction = row.get("market_reaction") or {}

    if kind == "report":
        report = _report_name(title)
        if reaction.get("change_pct") is not None:
            verb, assessment, tone = _reaction_words(reaction.get("change_pct"))
            move = _pct_text(reaction.get("change_pct"))
            close = _price_text(reaction.get("close"))
            ticker = row.get("ticker") or "Aksjen"
            if reaction.get("basis") == "event_day":
                text = f"{report} er publisert. På rapportdagen {verb} {ticker} {move}"
                if close:
                    text += f" og endte rundt {close}"
                text += f". Markedsreaksjonen var dermed {assessment}. Følg spesielt guiding, kontantstrøm, gjeld og utbytte mot forrige periode."
                return {"brief": text, "brief_tone": tone}
            text = f"{report} er publisert. Siste handelsdag {verb} {ticker} {move}"
            if close:
                text += f" til rundt {close}"
            text += ". Kilden mangler en presis rapportdato/-tid i feeden, så hele kursbevegelsen kan ikke sikkert tilskrives rapporten."
            return {"brief": text, "brief_tone": tone}
        return {
            "brief": f"{report} er publisert. Se spesielt etter resultat, guiding, kontantstrøm, gjeld og eventuelt utbytte mot forrige periode.",
            "brief_tone": "watch",
        }

    if kind == "insider":
        actor = row.get("actor") or "En primærinnsider"
        role = row.get("role")
        shares = _compact_number(row.get("shares"))
        price = _compact_number(row.get("price"))
        detail = actor + (f" ({role})" if role else "")
        if shares:
            detail += f" handlet {shares} aksjer"
        if price:
            detail += f" rundt {price} kr"
        direction = row.get("direction")
        if direction == "buy":
            base = detail + ". Insiderkjøp kan være et positivt interesse-signal, men bør vurderes sammen med verdsettelse, rapporter og øvrige signaler."
            tone = "positive"
        elif direction == "sell":
            base = detail + ". Insidersalg er verdt å følge, men kan skyldes mange forhold og er ikke alene et salgssignal."
            tone = "negative"
        else:
            base = detail + ". Åpne insiderfanen for verifiserte detaljer om handelen."
            tone = "watch"
        if reaction.get("basis") == "event_day" and reaction.get("change_pct") is not None:
            verb, _, _ = _reaction_words(reaction.get("change_pct"))
            base += f" Aksjen {verb} {_pct_text(reaction.get('change_pct'))} på hendelsesdagen."
        return {"brief": base, "brief_tone": tone}

    if kind == "dividend":
        base = "Utbytterelatert melding for en aksje du eier. Sjekk beløp, ex-dato, betalingsdato og om utbyttet endrer forventet direkteavkastning."
        if reaction.get("basis") == "event_day" and reaction.get("change_pct") is not None:
            verb, _, _ = _reaction_words(reaction.get("change_pct"))
            base += f" Aksjen {verb} {_pct_text(reaction.get('change_pct'))} på hendelsesdagen."
        return {"brief": base, "brief_tone": "watch"}

    if re.search(r"\b(contract|kontrakt|order|ordre|award)\b", low):
        base = "Ny kontrakt eller ordre. Se på kontraktsverdi, varighet, marginpotensial og hvor stor den er relativt til selskapets eksisterende omsetning."
        tone = "watch"
    elif re.search(r"\b(acquisition|acquire|oppkjøp|merger|fusjon)\b", low):
        base = "Oppkjøps- eller transaksjonsmelding. Viktigste punkter er pris, finansiering, forventede synergier og effekt på gjeld og inntjening."
        tone = "watch"
    elif re.search(r"\b(guidance|outlook|profit warning|resultatvarsel|nedjuster|oppjuster)\b", low):
        base = "Meldingen kan påvirke markedets forventninger til resultatene fremover. Sammenlign ny guiding med tidligere guiding og konsensus der det finnes."
        tone = "important"
    elif re.search(r"\b(bond|obligasjon|financing|finansiering|rights issue|emisjon|share issue)\b", low):
        base = "Finansieringsmelding. Følg med på rente/kostnad, eventuell utvanning og hvordan kapitalen påvirker balanse og vekstplaner."
        tone = "important"
    else:
        base = "Ny offisiell selskapsmelding for en aksje i beholdningen. Åpne meldingen for detaljene og vurder om den endrer inntjening, risiko eller kapitalallokering."
        tone = "neutral"
    if reaction.get("basis") == "event_day" and reaction.get("change_pct") is not None:
        verb, assessment, reaction_tone = _reaction_words(reaction.get("change_pct"))
        base += f" På hendelsesdagen {verb} aksjen {_pct_text(reaction.get('change_pct'))}, en {assessment} markedsreaksjon."
        if tone in ("watch", "neutral"):
            tone = reaction_tone
    return {"brief": base, "brief_tone": tone}


def _event(ticker, company, kind, title, url=None, occurred_at=None, importance="normal", **extra):
    row = {
        "ticker": ticker,
        "company": company,
        "kind": kind,
        "title": title,
        "url": url,
        "occurred_at": _iso(occurred_at),
        "importance": importance,
    }
    row.update({k: v for k, v in extra.items() if v is not None})
    row.update(_brief_for_event(row))
    return row


def _market_rows(provider, ticker):
    symbol = provider.symbol(_canonical_event_ticker(ticker))
    data = provider._get(
        f"{provider.BASE}/v8/finance/chart/{symbol}",
        {"range": "1mo", "interval": "1d", "events": "div,splits"},
    )
    result = ((data.get("chart") or {}).get("result") or [])
    if not result:
        return []
    result = result[0]
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    rows = []
    for i, ts in enumerate(timestamps):
        if i >= len(closes) or closes[i] is None:
            continue
        rows.append({
            "date": datetime.fromtimestamp(int(ts), timezone.utc).date().isoformat(),
            "close": float(closes[i]),
        })
    return rows


def _reaction_for_event(rows, event):
    if len(rows) < 2:
        return None
    occurred = event.get("occurred_at")
    event_date = occurred[:10] if occurred else None
    if event_date:
        idx = next((i for i, row in enumerate(rows) if row["date"] >= event_date), None)
        if idx is not None and idx > 0:
            before = float(rows[idx - 1]["close"])
            close = float(rows[idx]["close"])
            if before > 0:
                return {
                    "basis": "event_day",
                    "date": rows[idx]["date"],
                    "previous_close": before,
                    "close": close,
                    "change_pct": (close / before - 1.0) * 100.0,
                }
    # Fresh issuer fallbacks can temporarily lack a parsed publication date. For
    # reports only, expose the latest session move but label the weaker basis.
    if event.get("kind") == "report":
        before = float(rows[-2]["close"])
        close = float(rows[-1]["close"])
        if before > 0:
            return {
                "basis": "latest_session",
                "date": rows[-1]["date"],
                "previous_close": before,
                "close": close,
                "change_pct": (close / before - 1.0) * 100.0,
            }
    return None


def _enrich_market_reaction(events, provider, ticker):
    if not events or provider is None:
        return events
    try:
        rows = _market_rows(provider, ticker)
    except Exception:
        return events
    for event in events:
        reaction = _reaction_for_event(rows, event)
        if reaction:
            event["market_reaction"] = reaction
            event.update(_brief_for_event(event))
    return events


def _events_for_one(row, news_handler, reports_handler, insider_handler, provider=None):
    ticker = _canonical_event_ticker(row.get("ticker"))
    company = row.get("company_name") or ticker
    events = []

    if reports_handler:
        try:
            data = reports_handler(ticker, 4) or {}
            for item in (data.get("items") or [])[:4]:
                events.append(_event(
                    ticker, company, "report", item.get("title") or "Finansiell rapport",
                    item.get("url"), item.get("published_at"), "high",
                    category="Rapport", source=item.get("publisher") or item.get("source_type"),
                ))
        except Exception:
            pass

    if insider_handler:
        try:
            data = insider_handler(ticker) or {}
            for item in (data.get("items") or [])[:3]:
                direction = item.get("transaction_type") or item.get("direction") or "other"
                actor = item.get("person") or item.get("entity") or item.get("insider")
                role = item.get("role")
                label = "Insiderkjøp" if direction == "buy" else "Insidersalg" if direction == "sell" else "Insiderhendelse"
                title = f"{label}: {actor}" if actor else (item.get("title") or label)
                events.append(_event(
                    ticker, company, "insider", title, item.get("url"),
                    item.get("trade_date") or item.get("date"), "high",
                    direction=direction, actor=actor, role=role,
                    shares=item.get("shares"), price=item.get("price"),
                ))
        except Exception:
            pass

    if news_handler:
        try:
            data = news_handler(ticker, 8) or {}
            for item in data.get("items") or []:
                category = item.get("category") or "Nyhet"
                official = bool(item.get("official"))
                if category in ("Rapport", "Insider"):
                    continue
                if category not in ("Børsmelding", "Selskap", "Utbytte") and not official:
                    continue
                kind = "dividend" if category == "Utbytte" else "announcement"
                importance = "high" if category == "Børsmelding" else "normal"
                events.append(_event(
                    ticker, company, kind, item.get("title") or category,
                    item.get("url"), item.get("published_at"), importance,
                    category=category, source=item.get("publisher") or item.get("source_type"),
                ))
        except Exception:
            pass

    return _enrich_market_reaction(events, provider, ticker)


def _dedupe_and_sort(events, limit):
    out = []
    seen = set()
    for item in events:
        key = (
            str(item.get("ticker") or "").upper(),
            str(item.get("url") or "").split("?", 1)[0].rstrip("/").lower(),
            " ".join(str(item.get("title") or "").lower().split()),
        )
        compact = (key[0], key[1] or key[2])
        if compact in seen:
            continue
        seen.add(compact)
        out.append(item)

    priority = {"high": 0, "normal": 1}
    out.sort(key=lambda x: (x.get("occurred_at") is None, -(datetime.fromisoformat(x["occurred_at"]).timestamp()) if x.get("occurred_at") else 0, priority.get(x.get("importance"), 9)))
    return out[:limit]


def install():
    if getattr(extra_api, "_portfolio_events_runtime_v3", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)
        news_handler = _route_handler(app, "/api/news/{ticker}")
        reports_handler = _route_handler(app, "/api/reports/{ticker}")
        insider_handler = _route_handler(app, "/api/insider/{ticker}")
        provider = YahooProvider()

        @app.get("/api/holdings/events")
        def holdings_events(limit: int = 16):
            limit = max(1, min(int(limit or 16), 40))
            holdings = _holding_rows()
            key = tuple((str(x.get("ticker") or "").upper(), str(x.get("company_name") or "")) for x in holdings)
            now = time.time()
            with _CACHE_LOCK:
                if _CACHE["key"] == key and _CACHE["value"] is not None and now - _CACHE["at"] < _CACHE_TTL:
                    cached = dict(_CACHE["value"])
                    cached["items"] = list(cached.get("items") or [])[:limit]
                    return cached

            events = []
            with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
                futures = [pool.submit(_events_for_one, row, news_handler, reports_handler, insider_handler, provider) for row in holdings if row.get("tracked")]
                for future in as_completed(futures):
                    try:
                        events.extend(future.result())
                    except Exception:
                        pass

            items = _dedupe_and_sort(events, 40)
            value = {
                "status": "ok",
                "holding_count": len(holdings),
                "tracked_holding_count": sum(1 for x in holdings if x.get("tracked")),
                "event_count": len(items),
                "high_priority_count": sum(1 for x in items if x.get("importance") == "high"),
                "brief_method": "official_events_plus_market_reaction",
                "items": items,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            with _CACHE_LOCK:
                _CACHE.update({"key": key, "at": now, "value": value})
            result = dict(value)
            result["items"] = items[:limit]
            return result

    extra_api.install = patched_install
    extra_api._portfolio_events_runtime_v3 = True


install()
