"""Brønnøysundregistrene open-data v2 adapter (NLOD attribution retained).

No fuzzy issuer discovery: a full Norwegian legal name is required and the
complete bounded result must contain exactly one exact legal-name match.
Only company activity/identity/industry are retained, no personal/contact data.
"""
import re
from datetime import timedelta

BASE = 'https://data.brreg.no/enhetsregisteret/api/enheter'
SOURCE = 'Brønnøysundregistrene / Enhetsregisteret'
LICENSE = 'NLOD 2.0'


def documented_issuer_name(row, documents, at):
    """Use recent, already reconciled NewsWeb issuer metadata; never infer a suffix.

    This selects a name for a fresh exact Brreg lookup, not a company description
    or a current financing state. Conflicting legal names or issuer IDs fail closed.
    """
    from company_context import norm, stamp
    if len(documents) > 500:
        return {'status': 'unavailable', 'reason': 'document_limit'}
    candidates = []
    for event in documents:
        if not isinstance(event, dict):
            continue
        mid, iid = event.get('source_message_id'), event.get('source_issuer_id')
        name = event.get('company')
        published, observed = stamp(event.get('published_at')), stamp(event.get('observed_at'))
        if (event.get('source_type') != 'newsweb_oam' or event.get('kind') != 'financing_document'
                or event.get('ticker') != row['ticker'] or event.get('identity') != row['identity']
                or type(mid) is not int or mid <= 0 or type(iid) is not int or iid <= 0
                or event.get('url') != 'https://newsweb.oslobors.no/message/' + str(mid)
                or type(event.get('corrected_by_message_id')) is not int or event['corrected_by_message_id'] != 0
                or type(event.get('correction_for_message_id')) is not int or event['correction_for_message_id'] < 0
                or not isinstance(name, str) or not re.search(r'\s(?:ASA|AS)$', name, re.I)
                or norm(name) != row['identity']
                or not published or not observed or not published <= observed <= at
                or at - published > timedelta(days=180)):
            continue
        title = event.get('title')
        prefix = re.match(r'^(.+?)(?:\s+[-–—]\s+|:\s+)(.+)$', title) if isinstance(title, str) else None
        if not prefix or norm(prefix[1]) != row['identity']:
            continue
        title_form = re.search(r'\s(ASA|AS)$', prefix[1], re.I)
        if title_form and not legal_name(name).endswith(' ' + title_form[1].casefold()):
            continue
        candidates.append(event)
    if not candidates:
        return {'status': 'unknown'}
    if len({(legal_name(e['company']), e['source_issuer_id']) for e in candidates}) != 1:
        return {'status': 'ambiguous'}
    latest = max(candidates, key=lambda e: stamp(e['published_at']))
    return {'status': 'documented', 'legal_name': latest['company'],
            'source': 'NewsWeb official issuer metadata', 'source_url': latest['url'],
            'source_issuer_id': latest['source_issuer_id'], 'published_at': latest['published_at'],
            'captured_at': latest['observed_at'], 'attempted_at': at.isoformat(),
            'scope': 'legal_name_for_exact_registry_lookup', 'maximum_age_days': 180}


def legal_name(value):
    return ' '.join(str(value or '').casefold().split())


def fetch_registry(name):
    import requests
    r = requests.get(BASE, params={'navn':name, 'navnMetodeForSoek':'FORTLOEPENDE', 'size':100},
                     headers={'Accept':'application/vnd.brreg.enhetsregisteret.enhet.v2+json'},
                     timeout=10, allow_redirects=False)
    if r.status_code != 200 or len(r.content) > 1_000_000:
        raise ValueError('registry unavailable')
    return r.json()


def collect_registry(name, at, fetch=None):
    # A shortened display name could accidentally identify a Norwegian subsidiary
    # of a foreign listed parent. Never append a legal suffix to guess that identity.
    form = re.search(r'\s(ASA|AS)$', str(name or ''), re.I)
    if not form:
        return None
    payload = (fetch or fetch_registry)(name)
    page = payload.get('page') or {}
    rows = (payload.get('_embedded') or {}).get('enheter') or []
    if (page.get('number') != 0 or page.get('totalPages') != 1
            or page.get('totalElements') != len(rows) or len(rows) > 100):
        return None
    matches = [r for r in rows if legal_name(r.get('navn')) == legal_name(name)]
    if len(matches) != 1:
        return None
    row = matches[0]
    org = str(row.get('organisasjonsnummer') or '')
    if (not re.fullmatch(r'\d{9}', org) or row.get('slettedato')
            or (row.get('organisasjonsform') or {}).get('kode') != form.group(1).upper()):
        return None
    activity = row.get('aktivitet')
    description = ' '.join(activity) if isinstance(activity,list) and all(isinstance(v,str) for v in activity) else None
    if description and len(description) > 5000:
        description = None
    return {'official_name':row['navn'],'organisation_number':org,
            'registered_activity':description or None,
            'industry':(row.get('naeringskode1') or {}).get('beskrivelse'),
            'industry_code':(row.get('naeringskode1') or {}).get('kode'),
            'source':SOURCE,'source_url':BASE+'/'+org,'license':LICENSE,
            'captured_at':at.isoformat(),'attempted_at':at.isoformat(),
            'status':'stored','identity_method':'exact_legal_name_complete_result',
            'scope':'registered_activity_not_a_consolidated_group_description'}
