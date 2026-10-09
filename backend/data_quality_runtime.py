"""Data-quality checks for NordicSignal's persisted finance state.

This endpoint does not invent a single confidence number. It exposes concrete checks
that can fail independently, including source freshness, so stale data cannot hide
behind a generic green status.
"""
from datetime import datetime, timezone
import json
import math

import extra_api
from database import connect, USING_POSTGRES
from instrument_identifiers import valid_isin

SCORE_MAX_AGE_SECONDS = 30 * 60
QUOTE_MAX_AGE_SECONDS = 4 * 24 * 60 * 60


def _now():
    return datetime.now(timezone.utc).isoformat()


def _age_seconds(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None:
            return None
        delta = (datetime.now(timezone.utc) - dt).total_seconds()
        return int(delta) if delta >= 0 else None
    except Exception:
        return None


def _epoch_iso(value):
    try:
        return datetime.fromtimestamp(float(value), timezone.utc).isoformat()
    except Exception:
        return None


def _check(name, ok, detail, severity="error"):
    return {"name":name,"ok":bool(ok),"severity":severity,"detail":detail}


def _valid_score(value):
    if value is None or isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and 0.0 <= number <= 100.0


def _latest(conn, table, column):
    if not table or not column or not all(ch.isalnum() or ch == "_" for ch in table + column):
        return None
    try:
        row = conn.execute(f'SELECT MAX("{column}") latest FROM "{table}"').fetchone()
        return row["latest"] if row else None
    except Exception:
        conn.rollback()
        return None


def _freshness_entry(value, source, kind="timestamp"):
    latest = _epoch_iso(value) if kind == "epoch" else (str(value) if value not in (None, "") else None)
    return {
        "source": source,
        "latest_at": latest,
        "age_seconds": _age_seconds(latest) if latest else None,
    }


def _feed_cache_entry(conn, key, source):
    try:
        row = conn.execute("SELECT updated_at FROM runtime_feed_cache WHERE cache_key=? LIMIT 1", (key,)).fetchone()
        return _freshness_entry(row["updated_at"] if row else None, source, kind="epoch")
    except Exception:
        conn.rollback()
        return _freshness_entry(None, source)


def data_quality_snapshot():
    checks = []
    metrics = {}
    freshness = {}
    conn = connect()
    try:
        active = conn.execute("SELECT COUNT(*) n FROM stocks WHERE active=1").fetchone()
        active_n = int(active["n"] or 0) if active else 0
        metrics["active_stocks"] = active_n
        checks.append(_check("active_universe", active_n > 0, f"{active_n} active stocks"))

        rows = conn.execute(
            "SELECT s.ticker,sc.total,sc.created_at,COALESCE(sc.source,'stored') source "
            "FROM stocks s JOIN scores sc ON sc.id=(SELECT MAX(id) FROM scores x WHERE x.ticker=s.ticker) "
            "WHERE s.active=1 ORDER BY s.ticker"
        ).fetchall()
        latest = [dict(x) for x in rows]
        metrics["latest_score_rows"] = len(latest)
        invalid_scores = [x["ticker"] for x in latest if not _valid_score(x.get("total"))]
        checks.append(_check("score_range", not invalid_scores, "All latest scores are 0-100" if not invalid_scores else "Invalid scores: "+", ".join(invalid_scores[:8])))
        checks.append(_check("score_coverage", len(latest) == active_n and active_n > 0, f"{len(latest)}/{active_n} active stocks have a latest score"))
        ages = [(x["ticker"], _age_seconds(x.get("created_at"))) for x in latest]
        stale = [ticker for ticker, age in ages if age is None or age > SCORE_MAX_AGE_SECONDS]
        max_age = max((age for _, age in ages if age is not None), default=None)
        metrics["oldest_score_age_seconds"] = max_age
        checks.append(_check("score_freshness", not stale, "Latest score set is fresh" if not stale else f"{len(stale)} stale/undated score rows", severity="warning"))
        seed = [x["ticker"] for x in latest if x.get("source") == "seed"]
        checks.append(_check("no_seed_scores", not seed, "No active stock is using a seed score" if not seed else "Seed score active for: "+", ".join(seed[:8])))

        score_latest = _latest(conn, "scores", "created_at")
        quote_latest = _latest(conn, "quotes", "captured_at")
        # Portfolio/stock views fetch Yahoo quotes on request. Not every successful live
        # quote read is written to `quotes`, so the persisted table must never be used as
        # a proxy for the age of the price currently shown to the user.
        freshness["prices"] = {
            "source": "Yahoo Finance live quote endpoint",
            "latest_at": None,
            "age_seconds": None,
            "mode": "live_on_request",
            "note": "Live quote freshness is evaluated at request time; successful reads are not persisted on every request.",
        }
        freshness["persisted_price_snapshot"] = _freshness_entry(
            quote_latest,
            "Yahoo Finance quote snapshots persisted for diagnostics",
        )
        quote_age = freshness["persisted_price_snapshot"]["age_seconds"]
        checks.append(_check(
            "persisted_quote_snapshot_recency",
            quote_age is not None and quote_age <= QUOTE_MAX_AGE_SECONDS,
            "Latest persisted quote snapshot is within four days" if quote_age is not None and quote_age <= QUOTE_MAX_AGE_SECONDS else "Persisted quote snapshot is missing or older than four days",
            severity="warning",
        ))

        # A recent calculation does not prove a recent report or complete inputs.
        # The score row does not retain source-period/revision timestamps.
        freshness["fundamentals"] = {
            "source": "Yahoo Finance research used by score engine",
            "latest_at": None, "age_seconds": None,
            "mode": "source_time_unverified", "processed_at": score_latest,
            "note": "Score calculation time is not the report publication time or proof of financial completeness.",
        }
        freshness["scores"] = _freshness_entry(score_latest, "NordicSignal score engine")
        freshness["score_signals"] = _freshness_entry(_latest(conn, "signal_events", "created_at"), "NordicSignal score-change events")
        freshness["trend_activity"] = _freshness_entry(_latest(conn, "trend_activity_events", "created_at"), "NordicSignal trend/activity detector")
        freshness["market_news"] = _feed_cache_entry(conn, "market_news:v1", "Persisted market-news feed cache")

        insider_candidates = []
        try:
            rows = conn.execute("SELECT cache_key,updated_at FROM runtime_feed_cache WHERE cache_key LIKE 'insider_market:v1:%' ORDER BY updated_at DESC LIMIT 1").fetchall()
            insider_candidates = [dict(x) for x in rows]
        except Exception:
            conn.rollback()
        freshness["insider_feed"] = _freshness_entry(insider_candidates[0]["updated_at"] if insider_candidates else None, "Persisted Euronext Insider Pulse cache", kind="epoch")

        try:
            row = conn.execute("SELECT COUNT(*) n FROM trend_activity_events WHERE volume_ratio<0 OR recent_volume_ratio<0").fetchone()
            bad = int(row["n"] or 0) if row else 0
            checks.append(_check("trend_volume_sanity", bad == 0, "No negative volume ratios" if bad == 0 else f"{bad} invalid trend volume rows"))
        except Exception:
            conn.rollback()
            checks.append(_check("trend_volume_sanity", False, "Trend volume check unavailable", severity="warning"))

        try:
            row = conn.execute("SELECT COUNT(*) n FROM holding_purchase_lots WHERE shares IS NULL OR price_nok IS NULL OR shares<=0 OR price_nok<=0 OR CAST(shares AS TEXT) IN ('NaN','Infinity','-Infinity','Inf','-Inf') OR CAST(price_nok AS TEXT) IN ('NaN','Infinity','-Infinity','Inf','-Inf')").fetchone()
            bad = int(row["n"] or 0) if row else 0
            checks.append(_check("holding_lot_sanity", bad == 0, "All purchase lots have positive shares and price" if bad == 0 else f"{bad} invalid purchase lots"))
        except Exception:
            conn.rollback()
            checks.append(_check("holding_lot_sanity", False, "Purchase-lot check unavailable", severity="warning"))

        try:
            rows = conn.execute(
                "SELECT s.ticker,q.price,q.captured_at,q.market_time FROM stocks s LEFT JOIN quotes q "
                "ON q.id=(SELECT MAX(id) FROM quotes x WHERE x.ticker=s.ticker) WHERE s.active=1"
            ).fetchall()
            missing, unknown_time, stale_time, invalid_prices = [], [], [], []
            for row in rows:
                ticker = row['ticker']
                if row['captured_at'] is None:
                    missing.append(ticker)
                price = row['price']
                if price is None or not math.isfinite(float(price)) or float(price) <= 0:
                    invalid_prices.append(ticker)
                age = _age_seconds(row['market_time'])
                if age is None:
                    unknown_time.append(ticker)
                elif age > QUOTE_MAX_AGE_SECONDS:
                    stale_time.append(ticker)
            metrics['persisted_quotes'] = {'active_stocks': active_n, 'missing': len(missing),
                'invalid_or_missing_price': len(invalid_prices), 'unknown_or_invalid_market_time': len(unknown_time),
                'market_time_older_than_four_days': len(stale_time)}
            checks.append(_check('persisted_quote_coverage', active_n > 0 and not missing and not invalid_prices,
                f'{active_n-len(missing)}/{active_n} active stocks have a persisted quote; {len(invalid_prices)} missing/invalid prices', 'warning'))
            checks.append(_check('persisted_quote_market_time', active_n > 0 and not unknown_time and not stale_time,
                f'{len(unknown_time)} unknown/invalid and {len(stale_time)} old trade times in persisted snapshots; not a live quote verdict', 'warning'))
        except Exception:
            conn.rollback()
            checks.append(_check('persisted_quote_coverage', False, 'Per-stock persisted quote check unavailable', 'warning'))

        try:
            rows = conn.execute('SELECT ticker,payload FROM company_context_profiles').fetchall()
            descriptions = verified_financials = fresh_financials = unverified_financials = invalid_payloads = 0
            for row in rows:
                try:
                    payload = json.loads(row['payload'])
                    if not isinstance(payload, dict):
                        raise ValueError('profile is not an object')
                    descriptions += bool(payload.get('description'))
                    financials = payload.get('financials')
                    if not isinstance(financials, list):
                        raise ValueError('financials is not an array')
                    if financials:
                        if payload.get('yahoo_identity_verified') is True:
                            verified_financials += 1
                            source = (payload.get('field_sources') or {}).get('financials') or {}
                            age = _age_seconds(source.get('captured_at'))
                            fresh_financials += source.get('status') == 'stored' and age is not None and age <= 2*24*60*60
                        else:
                            unverified_financials += 1
                except (ValueError, TypeError, AttributeError):
                    invalid_payloads += 1
            metrics['company_profiles'] = {'stored': len(rows), 'with_description': descriptions,
                'financials_with_verified_identity': verified_financials,
                'financials_recently_collected': fresh_financials,
                'unverified_financials_hidden': unverified_financials, 'invalid_payloads': invalid_payloads}
            checks.append(_check('company_profile_payloads', not invalid_payloads,
                f'{invalid_payloads} invalid profile payloads'))
            checks.append(_check('company_financial_coverage', bool(rows) and fresh_financials == len(rows),
                f'{fresh_financials}/{len(rows)} automatic profiles have recently collected financials with verified identity; reviewed pilots are separate', 'warning'))
        except Exception:
            conn.rollback()
            checks.append(_check('company_financial_coverage', False, 'Company profile coverage check unavailable', 'warning'))

        try:
            rows = conn.execute('SELECT ticker,isin FROM ipo_listings').fetchall()
            invalid = [r['ticker'] for r in rows if not valid_isin(r['isin'])]
            metrics['listing_identifiers'] = {'stored': len(rows), 'invalid_or_missing': len(invalid)}
            checks.append(_check('listing_identifier_format', bool(rows) and not invalid,
                f'{len(invalid)}/{len(rows)} missing/invalid ISINs in source listing records; format validity is not current identity certification', 'warning'))
        except Exception:
            conn.rollback()
            checks.append(_check('listing_identifier_format', False, 'Listing identifier check unavailable', 'warning'))
    finally:
        conn.close()

    errors = [x for x in checks if not x["ok"] and x["severity"] == "error"]
    warnings = [x for x in checks if not x["ok"] and x["severity"] == "warning"]
    status = "error" if errors else "warning" if warnings else "ok"
    return {
        "status":status,
        "persistent_storage":bool(USING_POSTGRES),
        "checks":checks,
        "metrics":metrics,
        "freshness":freshness,
        "error_count":len(errors),
        "warning_count":len(warnings),
        "source_policy":{
            "prices":"Yahoo Finance",
            "insider":"Euronext Oslo Børs / Oslo Børs Newspoint",
            "short":"Finanstilsynet SSR",
            "calendar":"Euronext financial calendar",
            "signal_evidence":"Yahoo Finance daily price/volume history replayed through NordicSignal rules",
        },
        "freshness_policy":"Live Yahoo prices are fetched on request and are not inferred from the persisted quotes table. Persisted snapshots are checked per active stock. Score time is calculation time; financial report publication time and completeness are not established by it. Profile collection age does not certify report-period freshness. Feed-cache timestamps describe when NordicSignal last persisted a successfully renderable feed.",
        "generated_at":_now(),
    }


def install():
    if getattr(extra_api, "_data_quality_runtime_installed", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)

        @app.get("/api/data-quality")
        def data_quality_route():
            return data_quality_snapshot()

    extra_api.install = patched_install
    extra_api._data_quality_runtime_installed = True


install()
