"""Read-only IPO discovery projection. No model, price inference or external I/O.

The registry proves admission on a market, not an issuer's first ever listing.
Archived announcements prove a plan, never completion. Observed-at timestamps
are retained; this current-state projection must not be used for PIT backtests.
"""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit
import json
import logging
import re

from database import connect
from ipo_reviewed_profiles import enrich

log = logging.getLogger(__name__)


def _date(value):
    try:
        return date.fromisoformat(str(value or '')[:10])
    except ValueError:
        return None


def _expected(value):
    for fmt in ('%Y-%m-%d', '%d %B %Y'):
        try:
            return datetime.strptime(str(value or ''), fmt).date()
        except ValueError:
            pass
    return None


def _source(value):
    try:
        u = urlsplit(str(value or ''))
        return u.scheme == 'https' and u.hostname in ('live.euronext.com', 'www.euronext.com') and not u.username
    except ValueError:
        return False


def _ticker(value):
    v = str(value or '').upper().removesuffix('.OL')
    return v if re.fullmatch(r'[A-Z0-9][A-Z0-9.-]{0,19}', v) else None


def _base(row, tracked):
    ticker = _ticker(row.get('ticker'))
    return {
        'id': row.get('listing_id') or row.get('candidate_id'),
        'company': row.get('company') or 'Navn ikke dokumentert',
        'ticker': ticker, 'market': row.get('market'),
        'source_url': row.get('source_url'), 'source': 'Euronext / Oslo Børs',
        'first_seen_at': row.get('first_seen_at'), 'last_seen_at': row.get('last_seen_at'),
        'published_at': row.get('published_at'), 'score_effect': 0,
        'analysis_available': ticker in tracked,
        'assessment': 'Forskning – ingen kjøpsvurdering',
        'business_description': None, 'sector': None,
        'unknowns': ['Virksomhetsbeskrivelse og sektor', 'Verdsettelse, lønnsomhet og gjeld',
                     'Kapitalbruk og aksjesalg fra eksisterende eiere', 'Neste rapport og dokumentert lock-up-utløp'],
        'monitoring': {'5': None, '20': None, '60': None},
        'monitoring_note': '5/20/60 børsdager: avkastning ikke kvalitetssikret. Ingen excess-avkastning beregnet her.',
    }


def project(listings, candidates, tracked=(), now=None, source_status=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo('Europe/Oslo')).date()
    items, completed, seen = [], set(), set()
    for row in sorted(listings, key=lambda x: str(x.get('listing_date') or ''), reverse=True):
        day = _date(row.get('listing_date'))
        if not day or day > today or not _source(row.get('source_url')):
            continue
        identity = (row.get('isin') or _ticker(row.get('ticker')) or row.get('company'), row.get('market'), day)
        if identity in seen:
            continue
        seen.add(identity)
        completed.add((_ticker(row.get('ticker')), str(row.get('market') or '').replace(' Oslo', '').lower()))
        if day.year != today.year and (today - day).days > 90:
            continue
        item = _base(row, tracked)
        item.update(listing_date=day.isoformat(), days_since_listing=(today-day).days,
                    display_status='NEW' if (today-day).days <= 90 else 'NOTERT I ÅR',
                    groups=(['recent'] if (today-day).days <= 90 else []) + (['year'] if day.year == today.year else []),
                    listing_type='unknown', confirmation='Noteringsdato i offisielt register',
                    why_follow=['Dokumentert opptak til handel; følg de første rapportene og likviditeten.'],
                    risks=['Registeret alene skiller ikke nyintroduksjon fra overføring eller ny aksjeklasse.'],
                    next_event='Neste dokumenterte hendelse er ukjent.')
        enrich(item, row, now)
        items.append(item)
    # Only current, explicit pre-listing announcements qualify. No guessed dates.
    excluded = 0
    for row in sorted(candidates, key=lambda x: str(x.get('published_at') or ''), reverse=True):
        try:
            raw = json.loads(row.get('raw_payload') or '{}')
        except (ValueError, TypeError):
            raw = {}
        if not isinstance(raw, dict):
            continue
        text = ' '.join(str(raw.get(k) or row.get(k) or '') for k in ('title', 'summary'))
        published = _date(row.get('published_at'))
        expected = _expected(row.get('expected_listing_date_text'))
        ticker = _ticker(row.get('ticker'))
        market = str(row.get('market') or '').replace(' Oslo', '').lower()
        identity = (ticker or str(row.get('company') or '').casefold(), market)
        explicit = re.search(r'intention to (?:float|list)|planned listing|expected listing|expected to (?:be admitted|commence trading)|initial public offering|\bIPO\b', text, re.I)
        excluded_terms = re.search(r'\bbonds?\b|\bFRN\b|subsequent offering|additional shares|delist|withdraw|cancel|postpon|already listed|first day of trading|commenced trading|transfer|uplisting|downlisting', text, re.I)
        if (not raw.get('official') or not _source(row.get('source_url')) or not explicit or excluded_terms
                or not published or not 0 <= (today-published).days <= 90
                or (expected and expected < today) or (ticker and (ticker, market) in completed) or identity in seen):
            excluded += 1
            continue
        seen.add(identity)
        item = _base(row, tracked)
        item.update(groups=['upcoming'], display_status='PRE-IPO', listing_type=row.get('listing_type') or 'unknown',
                    listing_date=None, expected_listing_date=expected.isoformat() if expected else None,
                    expected_listing_date_text=row.get('expected_listing_date_text'),
                    confirmation='Offentlig noteringsplan – gjennomføring ikke bekreftet',
                    why_follow=['Offentlig noteringsplan: følg prospekt, endelige vilkår og opptaksbeslutning.'],
                    risks=['Planen kan endres eller avlyses. Tilgang for privatpersoner er ikke bekreftet.'],
                    next_event=('Forventet notering '+expected.isoformat()+' – betinget, ikke bekreftet.' if expected else 'Dato for neste hendelse er ikke verifisert.'))
        items.append(item)
    status = source_status or {}
    return {'status': 'partial' if 'unavailable' in status.values() else ('ok' if items else 'collecting'),
            'items': items, 'count': len(items), 'year': today.year, 'as_of': today.isoformat(),
            'generated_at': now.isoformat(), 'score_effect': 0, 'source_status': status,
            'counts': {g: sum(g in x['groups'] for x in items) for g in ('upcoming', 'recent', 'year')},
            'excluded_candidates': excluded,
            'coverage': 'Oslo: lagret Euronext-register og offentlige noteringsplaner. Ikke garantert full dekning. Nylig = siste 90 kalenderdager. Årets liste kan også inneholde overføringer og nye aksjeklasser.',
            'policy': 'Discovery-only. Ingen effekt på Aksjer Score, Opportunity eller varslingsterskler.'}


def build_discovery():
    # Separate short connections keep one failed optional source from poisoning
    # subsequent Postgres queries. No network fetch, refresh or schema writes here.
    values, status = {}, {}
    for key, sql in {
        'listings': 'SELECT * FROM ipo_listings ORDER BY listing_date DESC LIMIT 1000',
        'candidates': 'SELECT * FROM ipo_candidates ORDER BY published_at DESC LIMIT 500',
        'tracked': 'SELECT ticker FROM stocks WHERE active=1',
    }.items():
        conn = None
        try:
            conn = connect()
            values[key] = [dict(r) for r in conn.execute(sql).fetchall()]
            status[key] = 'stored' if values[key] else 'collecting'
        except Exception:
            log.warning('IPO discovery source unavailable: %s', key)
            values[key], status[key] = [], 'unavailable'
        finally:
            if conn is not None:
                conn.close()
    return project(values['listings'], values['candidates'],
                   {_ticker(r['ticker']) for r in values['tracked']}, source_status=status)
