"""Early Opportunity / Confluence Engine for NordicSignal.

Combines independent evidence from Trend/Reversal Engine v2, bullish volume and
Insider Signal v2. This module is informational only and does not modify the
aggregate 0-100 stock score.
"""
from __future__ import annotations

from datetime import datetime, timezone
import threading
import time

import extra_api
import insider_runtime
import insider_market_v2_runtime
from insider_signal_v2_runtime import analyze as analyze_insider
from providers import YahooProvider, NordicRegulatoryProvider
from trend_reversal_runtime import calculate_reversal

VERSION = "2026-08-30-v1.2"
_TARGET_CACHE_LOCK = threading.RLock()
_TARGET_CACHE = {"at": 0.0, "days": None, "items": []}
_TARGET_CACHE_TTL = 120


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def calculate_opportunity(reversal=None, insider=None):
    reversal = reversal or {}
    insider = insider or {}
    if "insider_signal_v2" in insider:
        insider = insider.get("insider_signal_v2") or {}

    reversal_score = reversal.get("score")
    if reversal_score is None:
        return {
            "score": None,
            "label": "INSUFFICIENT_DATA",
            "confidence": "low",
            "reasons": ["Trend/reversal history is insufficient"],
            "components": {},
            "score_effect": 0,
            "policy": "informational_only_pending_forward_validation",
            "version": VERSION,
        }

    reversal_score = _num(reversal_score)
    metrics = reversal.get("metrics") or {}
    volume_ratio = metrics.get("volume_ratio")
    volume_ratio = _num(volume_ratio) if volume_ratio is not None else None
    insider_label = str(insider.get("label") or "NONE").upper()
    insider_points = _num(insider.get("points"))
    independent_buyers = int(_num(insider.get("independent_buyers")))
    buy_value = _num(insider.get("buy_value_nok"))

    score = 0.0
    reasons = []
    if reversal_score >= 75:
        score += 45
        reasons.append("Reversal score >= 75")
    elif reversal_score >= 70:
        score += 32
        reasons.append("Reversal score >= 70")
    elif reversal_score >= 55:
        score += 15
        reasons.append("Reversal candidate only")

    volume_state = "NONE"
    if volume_ratio is not None and volume_ratio >= 2.0:
        score += 25
        volume_state = "STRONG"
        reasons.append("Bullish volume >= 2.0x normal")
    elif volume_ratio is not None and volume_ratio >= 1.5:
        score += 15
        volume_state = "CONFIRMED"
        reasons.append("Bullish volume >= 1.5x normal")

    if insider_label == "STRONG":
        score += 20
        reasons.append("Strong insider cluster")
    elif insider_label == "POSITIVE":
        score += 12
        reasons.append("Positive insider cluster")
    elif insider_label == "MIXED":
        score += 4

    if independent_buyers >= 3:
        score += 5
        reasons.append("3+ independent insider buyers")
    if buy_value >= 1_000_000:
        score += 5
        reasons.append("Insider purchases >= NOK 1m")

    strong_reversal = reversal_score >= 75
    volume_confirmed = volume_ratio is not None and volume_ratio >= 1.5
    insider_positive = insider_label in {"STRONG", "POSITIVE"}
    evidence_count = sum((strong_reversal, volume_confirmed, insider_positive))

    score = max(0.0, min(100.0, score))
    if evidence_count == 3 and score >= 80:
        label = "EARLY_OPPORTUNITY_HIGH"
        confidence = "high"
    elif strong_reversal and volume_confirmed and score >= 60:
        label = "EARLY_OPPORTUNITY"
        confidence = "medium_high" if insider_positive else "medium"
    elif reversal_score >= 70 and (volume_confirmed or insider_positive):
        label = "WATCH_CONFLUENCE"
        confidence = "medium"
    elif reversal_score >= 55:
        label = "REVERSAL_CANDIDATE"
        confidence = "low_medium"
    else:
        label = "NO_OPPORTUNITY"
        confidence = "low"

    return {
        "score": round(score, 1),
        "label": label,
        "confidence": confidence,
        "reasons": reasons,
        "components": {
            "reversal_score": reversal_score,
            "reversal_regime": reversal.get("regime"),
            "volume_ratio": volume_ratio,
            "volume_state": volume_state,
            "insider_label": insider_label,
            "insider_points": insider_points,
            "independent_buyers": independent_buyers,
            "buy_value_nok": buy_value,
            "evidence_count": evidence_count,
        },
        "score_effect": 0,
        "policy": "informational_only_pending_forward_validation",
        "version": VERSION,
    }


def _company_name(ticker):
    entry = insider_runtime.ISSUERS.get(ticker)
    return entry[0] if entry else ticker


def _cached_announcements(days=14):
    now = time.time()
    with _TARGET_CACHE_LOCK:
        if (
            _TARGET_CACHE.get("items") is not None
            and _TARGET_CACHE.get("days") == days
            and now - float(_TARGET_CACHE.get("at") or 0.0) < _TARGET_CACHE_TTL
        ):
            return [dict(x) for x in (_TARGET_CACHE.get("items") or [])]

    items, _meta = insider_market_v2_runtime._announcements(days)
    with _TARGET_CACHE_LOCK:
        _TARGET_CACHE.update({"at": now, "days": days, "items": [dict(x) for x in (items or [])]})
    return [dict(x) for x in (items or [])]


def _announcement_matches(symbol, announcement):
    ticker = str(announcement.get("ticker") or "").upper().replace(".OL", "")
    if ticker == symbol:
        return True
    company = announcement.get("company")
    try:
        return insider_market_v2_runtime._ticker_for_company(company) == symbol
    except Exception:
        return False


def _row_key(row):
    actor = (
        row.get("person")
        or row.get("related_primary_insider")
        or row.get("entity")
        or row.get("insider")
        or ""
    )
    return (
        str(row.get("node_id") or row.get("url") or ""),
        str(actor).strip().lower(),
        str(row.get("trade_date") or row.get("date") or "")[:10],
        str(row.get("direction") or row.get("transaction_type") or "").lower(),
        row.get("shares"),
        row.get("price"),
    )


def _targeted_market_rows(symbol, days=14):
    """Enrich only disclosures for one symbol across the complete recent topic archive."""
    rows = []
    seen = set()
    announcements = [x for x in _cached_announcements(days) if _announcement_matches(symbol, x)]
    for announcement in announcements[:30]:
        try:
            detail_rows, _network = insider_market_v2_runtime._euronext_ajax_rows(announcement, allow_network=True)
        except Exception:
            detail_rows = []
        for raw in detail_rows or []:
            row = dict(raw)
            ticker = str(row.get("ticker") or "").upper().replace(".OL", "")
            if ticker and ticker != symbol:
                continue
            if row.get("details_pending"):
                continue
            key = _row_key(row)
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def _persist_targeted_rows(rows):
    if not rows:
        return
    try:
        import insider_history_runtime
        insider_history_runtime.persist_items(rows)
    except Exception:
        pass


def _live_insider_evidence(symbol):
    """Build complete 14-day verified insider evidence for one ticker.

    The normal market feed is fast but capped at 100 returned rows. We merge it with
    ticker-targeted enrichment from the complete recent Euronext topic archive so a
    busy disclosure period cannot silently remove older-but-still-relevant trades.
    """
    market_error = None
    merged = []
    seen = set()
    source_parts = []

    try:
        market_feed = insider_market_v2_runtime.market_insider_feed(limit=100, days=14, refresh=False) or {}
        for raw in market_feed.get("items") or []:
            row = dict(raw)
            if str(row.get("ticker") or "").upper().replace(".OL", "") != symbol or row.get("details_pending"):
                continue
            key = _row_key(row)
            if key in seen:
                continue
            seen.add(key)
            merged.append(row)
        if merged:
            source_parts.append("market_feed")
    except Exception as exc:
        market_error = str(exc)

    try:
        targeted = _targeted_market_rows(symbol, 14)
        for row in targeted:
            key = _row_key(row)
            if key in seen:
                continue
            seen.add(key)
            merged.append(row)
        if targeted:
            source_parts.append("targeted_topic_archive")
    except Exception as exc:
        market_error = market_error or str(exc)

    if merged:
        _persist_targeted_rows(merged)
        enriched = analyze_insider({
            "status": "live",
            "source": "Euronext Oslo Børs Newspoint",
            "items": merged,
            "verified_detail_count": len(merged),
        })
        signal = enriched.get("insider_signal_v2") or {}
        signal["evidence_source"] = "+".join(source_parts) or "euronext_verified"
        signal["evidence_item_count"] = len(merged)
        signal["evidence_coverage"] = "verified_detail"
        if market_error:
            signal["partial_error"] = market_error
        return signal

    try:
        regulatory = NordicRegulatoryProvider()
        issuer_feed = regulatory.insider(symbol, _company_name(symbol)) or {}
        enriched = analyze_insider(issuer_feed)
        signal = enriched.get("insider_signal_v2") or {}
        item_count = len(issuer_feed.get("items") or [])
        signal["evidence_source"] = "issuer_provider_fallback"
        signal["evidence_item_count"] = item_count
        signal["evidence_coverage"] = "verified_detail" if item_count else "no_recent_detail"
        if market_error:
            signal["market_feed_error"] = market_error
        return signal
    except Exception as exc:
        return {
            "label": "NONE",
            "points": 0,
            "evidence_source": "unavailable",
            "evidence_item_count": 0,
            "evidence_coverage": "unavailable",
            "error": str(exc),
            "market_feed_error": market_error,
        }


def live_opportunity(ticker):
    symbol = str(ticker or "").strip().upper().replace(".OL", "")
    if not symbol or len(symbol) > 16 or not all(ch.isalnum() or ch in ".-" for ch in symbol):
        return {"ticker": symbol, "status": "invalid_ticker"}

    history = YahooProvider().historical(symbol, "6m")
    reversal = calculate_reversal(history)
    insider_signal = _live_insider_evidence(symbol)
    opportunity = calculate_opportunity(reversal, insider_signal)
    return {
        "ticker": symbol,
        "status": "ok",
        "opportunity": opportunity,
        "reversal": reversal,
        "insider_signal_v2": insider_signal,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _replace_route(app, path, handler):
    for route in getattr(app, "routes", []):
        if getattr(route, "path", None) == path and "GET" in (getattr(route, "methods", None) or set()):
            route.endpoint = handler
            dependant = getattr(route, "dependant", None)
            if dependant is not None:
                dependant.call = handler
            return True
    return False


def install():
    if getattr(extra_api, "_opportunity_confluence_runtime", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)

        def opportunity_route(ticker: str):
            return live_opportunity(ticker)

        if not _replace_route(app, "/api/opportunity/{ticker}", opportunity_route):
            app.get("/api/opportunity/{ticker}")(opportunity_route)

    extra_api.install = patched_install
    extra_api._opportunity_confluence_runtime = True


install()
