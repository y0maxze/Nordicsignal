from datetime import datetime, timezone
from html.parser import HTMLParser
import re
import time
from urllib.parse import quote, urlsplit, urlunsplit
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

PHRASES=('primary insider','primærinsider','mandatory notification of trade','notification of trade by primary insider','pdmr','meldepliktig handel for primærinnsidere')
BUY=re.compile(r'\b(purchased|purchase|bought|buy|acquired|acquisition|kjøpt|kjøpte|kjøp|ervervet|ervervelse)\b',re.I)
SELL=re.compile(r'\b(sold|sell|sale|disposed|avhendet|solgt|solgte|salg|avhendelse)\b',re.I)
SHARES=re.compile(r'(?:purchased|purchase|bought|buy|acquired|sold|sell|disposed of|kjøpt|kjøpte|kjøp|solgt|solgte|salg|ervervet).{0,260}?(\d[\d .\u00a0,]*)\s+(?:shares|aksjer)\b',re.I|re.S)

_CACHE={}
_CACHE_TTL=45


def norm(v): return re.sub(r'[^a-z0-9]+',' ',(v or '').lower().replace('ø','o').replace('æ','ae').replace('å','a')).strip()


def date_of(t):
    m=re.search(r'\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b',t or '')
    if m:return f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'
    m=re.search(r'\b(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})\b',t or '')
    return f'{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}' if m else None


def issuer_ok(body,ticker,name,title=''):
    n=norm(' '.join((body or '', title or '')))
    cname,aliases=ISSUERS.get(ticker,(name,()))
    return any(x and norm(x) in n for x in (cname,*aliases,name))


def parse_trade(body,ticker,title,source,url):
    direction='buy' if BUY.search(body) else 'sell' if SELL.search(body) else 'unknown'
    shares=None; m=SHARES.search(body)
    if m:
        d=re.sub(r'[^0-9]','',m.group(1)); shares=int(d) if d else None
    person=None
    patterns=(r'\b([A-Z][A-Za-zÀ-ÿ .\'-]{2,80}),\s*(?:CEO|CFO|Chair|Chairman|Board member|Styremedlem|Konsernsjef)\b',r'\b(?:CEO|CFO)\s+([A-Z][A-Za-zÀ-ÿ .\'-]{2,80})')
    for p in patterns:
        mm=re.search(p,body,re.I)
        if mm: person=mm.group(1).strip(); break
    return {'ticker':ticker,'date':date_of(body) or date_of(title),'trade_date':date_of(body),'title':title or 'Primary insider transaction','direction':direction,'transaction_type':direction if direction in ('buy','sell') else 'other','shares':shares,'insider':person,'source':source,'verified_detail':direction in ('buy','sell') or shares is not None,'issuer_verified':True,'summary':' '.join(body.split())[:1000],'url':url}


def fetch(session,url,params=None):
    last=None
    for attempt in range(3):
        try:
            r=session.get(url,params=params,timeout=20,allow_redirects=True)
            if r.status_code==429 or r.status_code>=500:
                last=RuntimeError(f'HTTP {r.status_code}')
                time.sleep(0.8*(attempt+1)); continue
            if r.status_code>=400: raise RuntimeError(f'HTTP {r.status_code}')
            return r.text
        except Exception as exc:
            last=exc
            if attempt<2: time.sleep(0.5*(attempt+1))
    raise last or RuntimeError('request failed')


def canonical_url(url):
    """Collapse Euronext language variants to one disclosure URL identity."""
    try:
        parts=urlsplit(url)
        path=re.sub(r'^/(?:en|fr|nb|nl|pt|de|it|el)(?=/)', '', parts.path, flags=re.I)
        return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ''))
    except Exception:
        return url


def install():
    try: from providers import NordicRegulatoryProvider
    except Exception: return
    if getattr(NordicRegulatoryProvider,'_robust_insider_patch_v6',False): return

    def insider(self,ticker,company_name=''):
        ticker=(ticker or '').upper(); name=company_name or ISSUERS.get(ticker,(ticker,()))[0]
        cached=_CACHE.get(ticker)
        if cached and time.time()-cached[0] < _CACHE_TTL: return cached[1]

        session=getattr(self,'session',requests.Session(impersonate='chrome'))
        candidates=[]; seen=set(); pages=[]
        if ticker in ISSUER_ARCHIVES: pages.append(ISSUER_ARCHIVES[ticker])
        pages.append('https://live.euronext.com/en/markets/oslo/equities/company-news')

        for page in pages:
            try: html=fetch(session,page,{'keys':ticker,'page':0})
            except Exception: continue
            p=_Parser(); p.feed(html)
            for href,label in p.links:
                full=href if href and href.startswith('http') else ('https://live.euronext.com'+href if href else '')
                canonical=canonical_url(full)
                if not full or canonical in seen: continue
                low=norm(label)
                if any(x in low for x in ('insider','primar','pdmr','mandatory notification','meldepliktig')) or ticker in ISSUER_ARCHIVES:
                    seen.add(canonical); candidates.append((full,label))

        items=[]
        for url,label in candidates[:80]:
            try:
                detail=fetch(session,url); p=_Parser(); p.feed(detail); body=p.text; low=norm(body)
                if not any(norm(x) in low for x in PHRASES): continue
                if not issuer_ok(body,ticker,name,label): continue
                items.append(parse_trade(body,ticker,label,'Euronext Oslo Børs Newspoint',url))
            except Exception: continue

        try:
            q=quote(f'{name} Primary Insider Transaction')
            data=session.get(f'https://query2.finance.yahoo.com/v1/finance/search?q={q}&newsCount=20',timeout=15).json()
            for n in data.get('news',[]):
                title=n.get('title',''); url=n.get('link') or ''
                if not any(x in norm(title) for x in ('primary insider','primærinsider','mandatory notification','meldepliktig')): continue
                try:
                    detail=fetch(session,url); p=_Parser(); p.feed(detail); body=p.text
                except Exception: continue
                if not issuer_ok(body,ticker,name,title) or not any(norm(x) in norm(body) for x in PHRASES): continue
                items.append(parse_trade(body,ticker,title,'Yahoo Finance syndicated issuer release',url))
        except Exception: pass

        # Deduplicate translated Euronext copies of the same disclosure.
        # URL alone is insufficient because the same notice exists at /en/,
        # /nb/, /fr/, etc. Use disclosure facts instead.
        dedup={}
        for x in items:
            k=(x.get('date'),x.get('direction'),x.get('shares'),norm(x.get('insider')),norm(x.get('summary',''))[:240])
            if k not in dedup: dedup[k]=x
        items=sorted(dedup.values(),key=lambda x:x.get('date') or '',reverse=True)[:12]
        buys=sum(x['direction']=='buy' for x in items); sells=sum(x['direction']=='sell' for x in items); unknown=len(items)-buys-sells
        verified_detail_count=sum(1 for x in items if x.get('verified_detail'))
        now=datetime.now(timezone.utc).isoformat()
        status='live' if not items or verified_detail_count > 0 else 'partial_live'
        result={'ticker':ticker,'items':items,'source':'Euronext Oslo Børs Newspoint + issuer release fallback','status':status,'buy_count':buys,'sell_count':sells,'unknown_count':unknown,'verified_detail_count':verified_detail_count,'signal':'buying' if buys>sells else 'selling' if sells>buys else 'activity' if items else 'no_activity','updated_at':now,'provider_checked':True}
        _CACHE[ticker]=(time.time(),result)
        return result

    NordicRegulatoryProvider.insider=insider
    NordicRegulatoryProvider._robust_insider_patch_v6=True

install()
