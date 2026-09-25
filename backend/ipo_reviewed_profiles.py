"""Versioned, manually source-reviewed IPO facts. Read-only research projection.

These snapshots are not a live feed and must never be used as PIT model inputs.
Identity requires ISIN, ticker, market and admission date; no fuzzy issuer joins.
"""
from copy import deepcopy
from functools import lru_cache
from zoneinfo import ZoneInfo
from datetime import datetime
import json
from pathlib import Path
from urllib.parse import urlsplit


@lru_cache(maxsize=1)
def _profiles():
    return json.loads((Path(__file__).parent / 'data' / 'ipo_reviewed_profiles.json').read_text())['profiles']


def enrich(item, row, now):
    for profile in _profiles():
        if any(str(row.get(k) or '') != profile[k] for k in ('ticker', 'isin', 'listing_date')):
            continue
        if str(row.get('market') or '').removesuffix(' Oslo') != profile['market']:
            continue
        if datetime.fromisoformat(profile['reviewed_at']) > now:
            continue
        sources = profile['sources']
        sections = profile['sections']
        if any(urlsplit(s['url']).scheme != 'https' or urlsplit(s['url']).username for s in sources.values()):
            continue
        if any(s['source_id'] not in sources for s in sections):
            continue
        item['documented_profile'] = deepcopy({k: profile[k] for k in ('reviewed_at', 'sources', 'sections')})
        item['documented_profile']['status'] = 'reviewed_snapshot'
        item['unknowns'] = list(profile['unknowns'])
        item['why_follow'] = list(profile['why_follow'])
        item['risks'] = list(profile['risks'])
        event = profile['next_event']
        if event['date'] >= now.astimezone(ZoneInfo('Europe/Oslo')).date().isoformat():
            item['next_event'] = f"{event['label']} – {event['date']}. Oppgitt i finanskalender; datoen kan endres."
            item['next_event_source'] = deepcopy(sources[event['source_id']])
        else:
            item['next_event'] = 'Den dokumenterte kalenderdatoen er passert. Ny hendelse er ikke kontrollert.'
        return item
    return item
