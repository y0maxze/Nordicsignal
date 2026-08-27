from datetime import datetime, timezone
from html.parser import HTMLParser
import re
import time
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from curl_cffi import requests


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.links=[]; self.href=None; self.link_parts=[]; self.skip=0
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag=='a': self.href=attrs.get('href'); self.link_parts=[]
        if tag in ('script','style','noscript'): self.skip+=1
    def handle_endtag(self, tag):
        if tag=='a' and self.href:
            self.links.append((self.href,' '.join(self.link_parts).strip())); self.href=None; self.link_parts=[]
        if tag in ('script','style','noscript'): self.skip=max(0,self.skip-1)
    def handle_data(self,data):
        if self.skip: return
        t=' '.join(data.split())
        if t:
            self.parts.append(t)
            if self.href is not None: self.link_parts.append(t)
    @property
    def text(self): return ' '.join(self.parts)


ISSUERS={
 'LSG':('Lerøy Seafood Group ASA',('lerøy seafood','leroy seafood','lerøy seafood group','leroy seafood group')),
 'MPCC':('MPC Container Ships',('mpc container ships',)), 'ELO':('Elopak',('elopak',)),
 'PEXIP':('Pexip',('pexip',)), 'XPLRA':('Xplora Technologies',('xplora',)), 'EQNR':('Equinor',('equinor',)),
 'DNB':('DNB',('dnb',)), 'NHY':('Norsk Hydro',('norsk hydro',)), 'YAR':('Yara International',('yara international','yara')),
 'MOWI':('Mowi',('mowi',)), 'SALM':('SalMar',('salmar',)), 'GJF':('Gjensidige Forsikring',('gjensidige',)),
 'TEL':('Telenor',('telenor',)), 'ORK':('Orkla',('orkla',)), 'TOM':('Tomra Systems',('tomra',)),
 'KOG':('Kongsberg Gruppen',('kongsberg gruppen','kongsberg')), 'NAS':('Norwegian Air Shuttle',('norwegian air shuttle',)),
 'AKRBP':('Aker BP',('aker bp',)), 'AKSO':('Aker Solutions',('aker solutions',)), 'SUBC':('Subsea 7',('subsea 7',)),
 'BWLPG':('BW LPG',('bw lpg',)), 'HAUTO':('Höegh Autoliners',('höegh autoliners','hoegh autoliners')),
 'CMBTO':('CMB.TECH',('cmb.tech','cmbt','cmbto')), 'VAR':('Vår Energi',('vår energi','var energi')),
}

ISSUER_ARCHIVES={
 'LSG':'https://live.euronext.com/en/product/equities/NO0003096208-XOSL',
 'AKRBP':'https://live.euronext.com/en/product/equities/NO0010345853-XOSL',
 'AKSO':'https://live.euronext.com/en/product/equities/NO0010716582-XOSL',
 'BWLPG':'https://live.euronext.com/en/product/equities/BMG173841013-XOSL',
}

ISSUER_RELEASE_FEEDS={'LSG':'https://www.globenewswire.com/en/search/organization/Ler%C3%B8y%2520Seafood%2520Group%2520ASA?page=1'}
PHRASES=('primary insider','primærinsider','mandatory notification of trade','notification of trade by primary insider','pdmr','meldepliktig handel for primærinnsidere')
BUY=re.compile(r'\b(purchased|purchase|bought|buy|acquired|acquisition|kjøpt|kjøpte|kjøp|ervervet|ervervelse)\b',re.I)
SELL=re.compile(r'\b(sold|sell|sale|disposed|avhendet|solgt|solgte|salg|avhendelse)\b',re.I)
TRADE_VERB=r'(?:purchased|purchase|bought|buy|acquired|acquisition|sold|sell|sale|disposed(?:\s+of)?|avhendet|solgt|solgte|salg|kjøpt|kjøpte|kjøp|ervervet|ervervelse)'
SHARES=re.compile(r'(?:purchased|purchase|bought|buy|acquired|sold|sell|disposed of|kjøpt|kjøpte|kjøp|solgt|solgte|salg|ervervet).{0,260}?(\d[\d .\u00a0,]*)\s+(?:shares|aksjer)\b',re.I|re.S)
ROLE=r'(?:CEO|CFO|COO(?:\s+Market Operations)?|CTO|Chair|Chairman|Chairwoman|Board member|Director|Styremedlem|Styreleder|Konsernsjef|Finansdirektør|Finansdirektor)'
ENTITY_SUFFIX=r'(?:AS|ASA|AB|A/S|B\.V\.|BV|Ltd\.?|Limited|PLC|Holding(?:s)?|Invest(?:ment)?(?:s)?)'
_CACHE={};_CACHE_TTL=45
_MONTHS={'january':1,'jan':1,'januar':1,'february':2,'feb':2,'februar':2,'march':3,'mar':3,'mars':3,'april':4,'apr':4,'may':5,'mai':5,'june':6,'jun':6,'juni':6,'july':7,'jul':7,'juli':7,'august':8,'aug':8,'september':9,'sep':9,'october':10,'oct':10,'oktober':10,'okt':10,'november':11,'nov':11,'december':12,'dec':12,'desember':12,'des':12}


def norm(v): return re.sub(r'[^a-z0-9]+',' ',(v or '').lower().replace('ø','o').replace('æ','ae').replace('å','a')).strip()


def date_of(t):
    text=t or ''
    m=re.search(r'\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b',text)
    if m:return f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'
    m=re.search(r'\b(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})\b',text)
    if m:return f'{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}'
    month_names='|'.join(sorted((re.escape(x) for x in _MONTHS),key=len,reverse=True))
    m=re.search(rf'\b(\d{{1,2}})\.?\s+({month_names})\s+(20\d{{2}})\b',text,re.I)
    if m:return f'{m.group(3)}-{_MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}'
    m=re.search(rf'\b({month_names})\s+(\d{{1,2}}),?\s+(20\d{{2}})\b',text,re.I)
    if m:return f'{m.group(3)}-{_MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}'
    return None


def issuer_ok(body,ticker,name,title=''):
    n=norm(' '.join((body or '',title or '')));cname,aliases=ISSUERS.get(ticker,(name,()))
    return any(x and norm(x) in n for x in (cname,*aliases,name))


def _number(value):
    if value is None:return None
    value=value.replace('\u00a0',' ').replace(' ','').strip()
    if not value:return None
    if ',' in value and '.' in value:
        if value.rfind(',')>value.rfind('.'):value=value.replace('.','').replace(',','.')
        else:value=value.replace(',','')
    elif ',' in value:
        head,tail=value.rsplit(',',1)
        if tail.isdigit() and 1<=len(tail)<=4 and head.replace('-','').isdigit():value=head+'.'+tail
        else:value=value.replace(',','')
    try:return float(value)
    except ValueError:return None


def _price_of(body):
    patterns=(r'\b(?:at|for)\s+(?:a\s+)?(?:price\s+(?:of\s+)?)?(?:NOK|SEK|DKK|EUR|USD)\s*([0-9][0-9 .\u00a0,]*)',r'\b(?:price|kurs)\s*(?:of|på|til|:)?\s*(?:NOK|SEK|DKK|EUR|USD)?\s*([0-9][0-9 .\u00a0,]*)',r'\btil\s+(?:en\s+)?kurs\s+(?:på\s+)?(?:NOK|SEK|DKK|EUR|USD)?\s*([0-9][0-9 .\u00a0,]*)')
    for p in patterns:
        m=re.search(p,body or '',re.I)
        if m:
            value=_number(m.group(1))
            if value is not None and value>0:return value
    return None


def _clean_entity_candidate(candidate):
    text=' '.join(str(candidate or '').split()).strip(' ,.-–—')
    if not text:return text
    # Keep only the final sentence before extracting a legal entity. This removes
    # issuer/title prefixes such as "Lerøy Seafood Group ASA. Nordbrand Invest AS".
    text=re.split(r'[.!?]\s+',text)[-1].strip(' ,.-–—')
    # Euronext often writes "Issuer AS has been notified that Entity AS ...".
    # Everything before these connector phrases describes the issuer, not the actor.
    for sep in (r'\bnotified\s+that\b',r'\binformed\s+that\b',r'\breported\s+that\b',r'\bthrough\b',r'\bvia\b',r'\bgjennom\b'):
        parts=re.split(sep,text,flags=re.I)
        if len(parts)>1:text=parts[-1].strip(' ,.-–—')
    # Prefer a compact final legal-entity name (max six words). This prevents a
    # complete prose clause from becoming the actor while retaining names such as
    # "Riverborg B.V." and "Nordbrand Invest AS".
    matches=list(re.finditer(rf'([A-ZÆØÅ][A-Za-zÀ-ÿ0-9&.\'-]*(?:\s+[A-ZÆØÅ][A-Za-zÀ-ÿ0-9&.\'-]*){{0,5}}\s+{ENTITY_SUFFIX})\b',text,re.I))
    if matches:return matches[-1].group(1).strip(' ,.-–—')
    return text


def parse_trade(body,ticker,title,source,url):
    direction='buy' if BUY.search(body) else 'sell' if SELL.search(body) else 'unknown'
    shares=None;m=SHARES.search(body)
    if m:
        d=re.sub(r'[^0-9]','',m.group(1));shares=int(d) if d else None
    person=None;role=None
    role_first=re.search(rf'\b(?P<role>{ROLE})\s+(?P<name>[A-ZÆØÅ][A-Za-zÀ-ÿ .\'-]{{2,80}}?)(?=\s*(?:,|-|–|—)?\s*{TRADE_VERB}\b)',body or '',re.I)
    if role_first:role=role_first.group('role').strip();person=role_first.group('name').strip(' ,.-–—')
    else:
        name_first=re.search(rf'\b(?P<name>[A-ZÆØÅ][A-Za-zÀ-ÿ .\'-]{{2,80}}?),\s*(?P<role>{ROLE})\b',body or '',re.I)
        if name_first:person=name_first.group('name').strip(' ,.-–—');role=name_first.group('role').strip()
    entity=None
    represented=re.search(rf'\b(?P<entity>[A-ZÆØÅ][A-Za-zÀ-ÿ0-9& .\'-]{{1,100}}\s{ENTITY_SUFFIX}),\s*(?:represented|representert).*?\b(?:by|ved)\s+(?P<rep>[A-ZÆØÅ][A-Za-zÀ-ÿ .\'-]{{2,80}})',body or '',re.I)
    if represented:
        entity=_clean_entity_candidate(represented.group('entity'));representative=represented.group('rep').strip(' ,.-–—')
        if not role:role=f'Representert ved {representative}'
    else:
        entity_patterns=(rf'\b(?P<entity>[A-ZÆØÅ][A-Za-zÀ-ÿ0-9& .\'-]{{1,100}}\s{ENTITY_SUFFIX})(?=\s+{TRADE_VERB}\b)',rf'\b(?:through|via|by|gjennom)\s+(?P<entity>[A-ZÆØÅ][A-Za-zÀ-ÿ0-9& .\'-]{{1,100}}\s{ENTITY_SUFFIX})\b')
        for p in entity_patterns:
            mm=re.search(p,body or '',re.I)
            if mm:
                candidate=_clean_entity_candidate(mm.group('entity'));issuer_name=ISSUERS.get(ticker,(ticker,()))[0]
                if norm(candidate)!=norm(issuer_name):entity=candidate
                break
    price=_price_of(body);actor=person or entity;transaction_value=(float(shares)*price) if shares is not None and price is not None else None
    return {'ticker':ticker,'date':date_of(body) or date_of(title),'trade_date':date_of(body),'title':title or 'Primary insider transaction','direction':direction,'transaction_type':direction if direction in ('buy','sell') else 'other','shares':shares,'price':price,'transaction_value':transaction_value,'insider':actor,'person':person,'entity':entity,'role':role,'actor_type':'person' if person else 'company' if entity else None,'source':source,'verified_detail':direction in ('buy','sell') or shares is not None,'issuer_verified':True,'summary':' '.join(body.split())[:1000],'url':url}


def parse_trades(body,ticker,title,source,url):
    text=' '.join((body or '').split());release_date=date_of(text) or date_of(title);rows=[]
    for segment in re.split(r'(?<=[.!?])\s+(?=[A-ZÆØÅ])',text):
        if not (BUY.search(segment) or SELL.search(segment)) or not SHARES.search(segment):continue
        row=parse_trade(segment,ticker,title,source,url)
        if row.get('trade_date') is None and release_date:row['trade_date']=release_date;row['date']=release_date
        if row.get('shares') is not None or row.get('insider') or row.get('direction') in ('buy','sell'):rows.append(row)
    if not rows:
        rows=[parse_trade(text,ticker,title,source,url)]
        if rows[0].get('trade_date') is None and release_date:rows[0]['trade_date']=release_date;rows[0]['date']=release_date
    dedup=[];seen=set()
    for row in rows:
        key=(row.get('date'),row.get('direction'),row.get('shares'),norm(row.get('insider')))
        if key in seen:continue
        seen.add(key);dedup.append(row)
    return dedup


def fetch(session,url,params=None):
    last=None
    for attempt in range(3):
        try:
            r=session.get(url,params=params,timeout=20,allow_redirects=True)
            if r.status_code==429 or r.status_code>=500:last=RuntimeError(f'HTTP {r.status_code}');time.sleep(0.8*(attempt+1));continue
            if r.status_code>=400:raise RuntimeError(f'HTTP {r.status_code}')
            return r.text
        except Exception as exc:
            last=exc
            if attempt<2:time.sleep(0.5*(attempt+1))
    raise last or RuntimeError('request failed')


def canonical_url(url):
    try:
        parts=urlsplit(url);path=re.sub(r'^/(?:en|fr|nb|nl|pt|de|it|el)(?=/)', '',parts.path,flags=re.I);return urlunsplit((parts.scheme,parts.netloc,path,parts.query,''))
    except Exception:return url


def _is_insider_label(label):
    low=norm(label);return any(x in low for x in ('insider','primar','pdmr','mandatory notification','meldepliktig'))


def install():
    try:from providers import NordicRegulatoryProvider
    except Exception:return
    if getattr(NordicRegulatoryProvider,'_robust_insider_patch_v10',False):return
    def insider(self,ticker,company_name=''):
        ticker=(ticker or '').upper();name=company_name or ISSUERS.get(ticker,(ticker,()))[0];cached=_CACHE.get(ticker)
        if cached and time.time()-cached[0]<_CACHE_TTL:return cached[1]
        session=getattr(self,'session',requests.Session(impersonate='chrome'));candidates=[];seen=set();pages=[]
        if ticker in ISSUER_ARCHIVES:pages.append(ISSUER_ARCHIVES[ticker])
        pages.append('https://live.euronext.com/en/markets/oslo/equities/company-news')
        for page in pages:
            try:html=fetch(session,page,{'keys':ticker,'page':0})
            except Exception:continue
            p=_Parser();p.feed(html);relevant=[];fallback=[]
            for href,label in p.links:
                full=urljoin(page,href or '');canonical=canonical_url(full)
                if not href or canonical in seen:continue
                if _is_insider_label(label):relevant.append((full,label,'Euronext Oslo Børs Newspoint'));seen.add(canonical)
                elif page==ISSUER_ARCHIVES.get(ticker) and norm(label) in ('open in new window','open'):fallback.append((full,label,'Euronext Oslo Børs Newspoint'));seen.add(canonical)
            candidates.extend(relevant)
            if not relevant:candidates.extend(fallback[:12])
        feed=ISSUER_RELEASE_FEEDS.get(ticker)
        if feed:
            try:
                html=fetch(session,feed);p=_Parser();p.feed(html)
                for href,label in p.links:
                    if not _is_insider_label(label):continue
                    full=urljoin(feed,href or '');canonical=canonical_url(full)
                    if not href or canonical in seen:continue
                    seen.add(canonical);candidates.append((full,label,'GlobeNewswire issuer release'))
            except Exception:pass
        items=[]
        for url,label,source in candidates[:60]:
            try:
                detail=fetch(session,url);p=_Parser();p.feed(detail);body=p.text;low=norm(body)
                if not any(norm(x) in low for x in PHRASES):continue
                if not issuer_ok(body,ticker,name,label):continue
                items.extend(parse_trades(body,ticker,label,source,url))
            except Exception:continue
        try:
            q=quote(f'{name} Primary Insider Transaction');data=session.get(f'https://query2.finance.yahoo.com/v1/finance/search?q={q}&newsCount=20',timeout=15).json()
            for n in data.get('news',[]):
                title=n.get('title','');url=n.get('link') or ''
                if not _is_insider_label(title):continue
                try:detail=fetch(session,url);p=_Parser();p.feed(detail);body=p.text
                except Exception:continue
                if not issuer_ok(body,ticker,name,title) or not any(norm(x) in norm(body) for x in PHRASES):continue
                items.extend(parse_trades(body,ticker,title,'Yahoo Finance syndicated issuer release',url))
        except Exception:pass
        dedup={}
        for x in items:
            actor_key=norm(x.get('insider'))
            if actor_key or x.get('shares') is not None:k=(x.get('date'),x.get('direction'),x.get('shares'),actor_key)
            else:k=(x.get('date'),x.get('direction'),canonical_url(x.get('url') or ''),norm(x.get('title')))
            if k not in dedup:dedup[k]=x
        items=sorted(dedup.values(),key=lambda x:x.get('date') or '',reverse=True)[:12];buys=sum(x['direction']=='buy' for x in items);sells=sum(x['direction']=='sell' for x in items);unknown=len(items)-buys-sells;verified_detail_count=sum(1 for x in items if x.get('verified_detail'));now=datetime.now(timezone.utc).isoformat();status='live' if not items or verified_detail_count>0 else 'partial_live'
        result={'ticker':ticker,'items':items,'source':'Euronext Oslo Børs Newspoint + issuer release fallback','status':status,'buy_count':buys,'sell_count':sells,'unknown_count':unknown,'verified_detail_count':verified_detail_count,'signal':'buying' if buys>sells else 'selling' if sells>buys else 'activity' if items else 'no_activity','updated_at':now,'provider_checked':True};_CACHE[ticker]=(time.time(),result);return result
    NordicRegulatoryProvider.insider=insider;NordicRegulatoryProvider._robust_insider_patch_v10=True


install()