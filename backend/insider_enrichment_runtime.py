"""Enrich public primary-insider disclosures with structured trade and ownership fields.

This patch intentionally never invents a person, company, trade amount or ownership.
It only parses values present in the public disclosure. Ownership percentage is shown
only when the disclosure itself states it; disclosed post-trade share holdings remain
available separately without triggering another market-data request.
"""

import re


def _norm_number(value):
    if value is None:
        return None
    s=str(value).replace('\u00a0',' ').strip()
    s=re.sub(r'[^0-9,.-]','',s.replace(' ',''))
    if not s:
        return None
    if ',' in s and '.' in s:
        if s.rfind(',') > s.rfind('.'):
            s=s.replace('.','').replace(',','.')
        else:
            s=s.replace(',','')
    elif ',' in s:
        tail=s.rsplit(',',1)[-1]
        s=s.replace(',','.') if len(tail)<=2 else s.replace(',','')
    try:
        return float(s)
    except ValueError:
        return None


def _first(patterns, text, flags=re.I|re.S):
    for pattern in patterns:
        m=re.search(pattern,text or '',flags)
        if m:
            return m.group(1).strip(' \t\r\n:;,.–—-')
    return None


def _direction(text, current=None):
    if current in ('buy','sell'):
        return current
    nature=_first((
        r'(?:nature\s+of\s+(?:the\s+)?transaction|transaction\s+type|type\s+of\s+transaction|transaksjon(?:stype|ens\s+art)|handelstype)\s*[:\-]?\s*(purchase|buy|acquisition|sale|sell|disposal|kjøp|salg|ervervelse|avhendelse)',
    ),text)
    n=(nature or '').lower()
    if n in ('purchase','buy','acquisition','kjøp','ervervelse'):
        return 'buy'
    if n in ('sale','sell','disposal','salg','avhendelse'):
        return 'sell'
    if re.search(r'\b(purchased|bought|acquired|kjøpt|kjøpte|ervervet)\b',text or '',re.I):
        return 'buy'
    if re.search(r'\b(sold|disposed|solgt|solgte|avhendet)\b',text or '',re.I):
        return 'sell'
    return current or 'unknown'


def _shares(text, current=None):
    if current not in (None,0):
        return current
    raw=_first((
        r'(?:aggregated\s+volume|aggregate\s+volume|number\s+of\s+shares|no\.?\s+of\s+shares|volume|antall\s+aksjer|aggregert\s+volum)\s*[:\-]?\s*([0-9][0-9 .\u00a0,]*)',
        r'([0-9][0-9 .\u00a0,]*)\s+(?:shares|aksjer)\b',
    ),text)
    n=_norm_number(raw)
    return int(round(n)) if n is not None and n>=0 else current


def _price(text, current=None):
    if current not in (None,0):
        return current
    raw=_first((
        r'(?:price(?:\(s\))?|price\s+per\s+share|kurs|pris)\s*[:\-]?\s*(?:NOK|SEK|DKK|EUR|USD)?\s*([0-9][0-9 .\u00a0,]*)',
        r'(?:NOK|SEK|DKK|EUR|USD)\s*([0-9]+(?:[.,][0-9]+)?)\s*(?:per\s+share|per\s+aksje)?',
    ),text)
    n=_norm_number(raw)
    return n if n is not None and n>0 else current


def _person(text, current=None):
    if current:
        return current
    return _first((
        r'(?:name\s+of\s+(?:the\s+)?person\s+discharging\s+managerial\s+responsibilities|name\s+of\s+primary\s+insider|primary\s+insider|primærinnsider|primærinsider)\s*[:\-]?\s*([A-ZÆØÅ][A-Za-zÀ-ÿ .\'-]{2,80}?)(?=\s+(?:position|status|role|stilling|purchase|sale|kjøp|salg)|[;|])',
        r'\b(?:CEO|CFO|COO|CTO|Chair(?:man|woman)?|Board member|Director|Konsernsjef|Finansdirektør|Styreleder|Styremedlem)\s+([A-ZÆØÅ][A-Za-zÀ-ÿ .\'-]{2,80}?)(?=\s+(?:purchased|bought|acquired|sold|kjøpt|solgt)|[,;])',
    ),text)


def _role(text, current=None):
    if current:
        return current
    return _first((
        r'(?:position/status|position\s+and\s+status|position|role|stilling|rolle)\s*[:\-]?\s*([A-Za-zÆØÅæøå /&.-]{2,80}?)(?=\s+(?:nature|transaction|date|price|volume|name)|[;|])',
    ),text)


def _entity(text, current=None):
    if current:
        return current
    prefix=r'(?:closely\s+associated\s+(?:person|company|entity)|person\s+closely\s+associated|nærstående\s+(?:foretak|selskap)|through|via|gjennom)\s*[:\-]?\s*'
    return _first((
        prefix+r'([A-ZÆØÅ][A-Za-zÀ-ÿ0-9& .\'-]{1,100}?\s(?:ASA|AS|AB|A/S|Ltd\.?|Limited|PLC))\b',
        prefix+r'([A-ZÆØÅ][A-Za-zÀ-ÿ0-9& .\'-]{1,100}?\s(?:Holding(?:s)?|Investments?))\b',
    ),text)


def _holding_after(text):
    raw=_first((
        r'(?:following|after)\s+(?:the\s+)?transaction[^.]{0,180}?(?:owns?|holds?|holding(?:s)?(?:\s+will\s+be)?)\s*[:\-]?\s*([0-9][0-9 .\u00a0,]*)\s+(?:shares|aksjer)',
        r'(?:holding(?:s)?\s+after\s+(?:the\s+)?transaction|shares\s+held\s+after\s+(?:the\s+)?transaction|beholdning\s+etter\s+(?:transaksjonen|handelen)|aksjer\s+etter\s+(?:transaksjonen|handelen))\s*[:\-]?\s*([0-9][0-9 .\u00a0,]*)',
        r'(?:will\s+own|vil\s+eie|eier\s+etter\s+transaksjonen)\s*([0-9][0-9 .\u00a0,]*)\s+(?:shares|aksjer)',
    ),text)
    n=_norm_number(raw)
    return int(round(n)) if n is not None and n>=0 else None


def _disclosed_pct(text):
    raw=_first((
        r'(?:ownership|holding|shareholding|eierandel|andel)\s*(?:after\s+(?:the\s+)?transaction|etter\s+(?:transaksjonen|handelen))?\s*[:\-]?\s*([0-9]+(?:[.,][0-9]+)?)\s*%',
        r'([0-9]+(?:[.,][0-9]+)?)\s*%\s+(?:of\s+(?:the\s+)?(?:shares|company)|av\s+(?:aksjene|selskapet))',
    ),text)
    return _norm_number(raw)


def enrich_item(item, ticker):
    x=dict(item or {})
    text=' '.join(str(v or '') for v in (x.get('summary'),x.get('title')))
    x['direction']=_direction(text,x.get('direction'))
    x['transaction_type']=x['direction'] if x['direction'] in ('buy','sell') else 'other'
    x['shares']=_shares(text,x.get('shares'))
    x['price']=_price(text,x.get('price'))
    x['person']=_person(text,x.get('person'))
    x['role']=_role(text,x.get('role'))
    x['entity']=_entity(text,x.get('entity'))
    x['insider']=x.get('person') or x.get('entity') or x.get('insider')
    x['actor_type']='person' if x.get('person') else 'company' if x.get('entity') else x.get('actor_type')
    if x.get('shares') is not None and x.get('price') is not None:
        x['transaction_value']=float(x['shares'])*float(x['price'])
    holding=_holding_after(text)
    if holding is not None:
        x['holding_after_shares']=holding
    pct=_disclosed_pct(text)
    if pct is not None:
        x['ownership_pct']=pct
        x['ownership_pct_source']='disclosed'
    else:
        # Do not launch a second Yahoo fundamentals request merely to estimate a
        # percentage from an annual share-count proxy. It adds provider/RAM load and
        # can imply more precision than the underlying disclosure supports.
        x.pop('ownership_pct',None)
        x.pop('ownership_pct_source',None)
        x.pop('shares_outstanding_reference',None)
    details=[]
    if x.get('role'):
        details.append(str(x['role']))
    if x.get('holding_after_shares') is not None:
        details.append(f"Eier etter: {int(x['holding_after_shares']):,} aksjer".replace(',',' '))
    if x.get('ownership_pct') is not None:
        details.append(f"{x['ownership_pct']:.4f}% av selskapet oppgitt")
    if details:
        x['role']=' · '.join(details)
    x['verified_detail']=bool(x.get('person') or x.get('entity') or x.get('shares') is not None or x.get('price') is not None or x['direction'] in ('buy','sell'))
    return x


def install():
    try:
        from providers import NordicRegulatoryProvider
    except Exception:
        return
    if getattr(NordicRegulatoryProvider,'_insider_enrichment_v1',False):
        return
    original=NordicRegulatoryProvider.insider

    def insider(self,ticker,company_name=''):
        result=original(self,ticker,company_name)
        if not isinstance(result,dict):
            return result
        out=dict(result)
        enriched=[enrich_item(x,(ticker or '').upper()) for x in (result.get('items') or [])]
        # Do not clutter the UI with archive/navigation hits that contain no actual trade detail.
        actionable=[x for x in enriched if x.get('verified_detail')]
        out['items']=actionable
        out['buy_count']=sum(x.get('direction')=='buy' for x in actionable)
        out['sell_count']=sum(x.get('direction')=='sell' for x in actionable)
        out['unknown_count']=len(actionable)-out['buy_count']-out['sell_count']
        out['verified_detail_count']=sum(1 for x in actionable if x.get('verified_detail'))
        out['ownership_data_note']='Eierandel vises når prosentandelen er oppgitt i børsmeldingen. Oppgitt beholdning etter handel vises separat i antall aksjer; NordicSignal gjør ikke et ekstra nettverkskall for å gjette eierandel.'
        return out

    NordicRegulatoryProvider.insider=insider
    NordicRegulatoryProvider._insider_enrichment_v1=True


install()
