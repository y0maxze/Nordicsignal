"""Brønnøysundregistrene open-data v2 adapter (NLOD attribution retained).

No fuzzy issuer discovery: a full Norwegian legal name is required and the
complete bounded result must contain exactly one exact legal-name match.
Only company activity/identity/industry are retained, no personal/contact data.
"""
import re

BASE = 'https://data.brreg.no/enhetsregisteret/api/enheter'
SOURCE = 'Brønnøysundregistrene / Enhetsregisteret'
LICENSE = 'NLOD 2.0'


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
