from datetime import datetime, timezone
from html.parser import HTMLParser
import re
from urllib.parse import quote
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
 'LSG':('Lerøy Seafood Group ASA',('lerøy seafood','leroy seafood')),
 'MPCC':('MPC Container Ships',('mpc container ships',)), 'ELO':('Elopak',('elopak',)),
 'PEXIP':('Pexip',('pexip',)), 'XPLRA':('Xplora Technologies',('xplora',)), 'EQNR':('Equinor',('equinor',)),
 'DNB':('DNB',('dnb',)), 'NHY':('Norsk Hydro',('norsk hydro',)), 'YAR':('Yara International',('yara international','yara')),
 'MOWI':('Mowi',('mowi',)), 'SALM':('SalMar',('salmar',)), 'GJF':('Gjensidige Forsikring',('gjensidige',)),
 'TEL':('Telenor',('telenor',)), 'ORK':('Orkla',('orkla',)), 'TOM':('Tomra Systems',('tomra',)),
 'KOG':('Kongsberg Gruppen',('kongsberg gruppen','kongsberg')), 'NAS':('Norwegian Air Shuttle',('norwegian air shuttle',)),
 'AKRBP':('Aker BP',('aker bp',)), 'AKSO':('Aker Solutions',('aker solutions',)), 'SUBC':('Subsea 7',('subsea 7',)),
 'BWLPG':('BW LPG',('bw lpg',)), 'HAUTO':('Höegh Autoliners',('höegh autoliners','hoegh autoliners')),
 'GOGL':('Golden Ocean',('golden ocean',)), 'VAR':('Vår Energi',('vår energi','var energi')),
}
# Stable Euronext issuer archive pages. These are much more reliable than the
# generic company-news page, which is often rendered through client-side filters.
ISSUER_ARCHIVES={
 'LSG':'https://live.euronext.com/en/listview/company-press-release/108681',
 'AKRBP':'https://live.euronext.com/en/listview/company-press-release/148951',
 'AKSO':'https://live.euronext.com/en/listview/company-press-release/208056',
 'BWLPG':'https://live.euronext.com/en/listview/company-press-release/203005',
}
PHRASES=('primary insider','primærinsider','mandatory notification of trade','notification of trade by primary insider','pdmr','meldepliktig handel for primærinnsidere')
BUY=re.compile(r'\b(purchased|purchase|bought|buy|acquired|kjøpt|kjøpte|kjøp|kjøpte)\b',re.I)
SELL=re.compile(r'\b(sold|sell|sale|disposed|avhendet|solgt|solgte|salg)\b',re.I)
SHARES=re.compile(r'(?:purchased|purchase|bought|buy|acquired|sold|sell|disposed of|kjøpt|kjøpte|kjøp|solgt|solgte|salg).{0,220}?(\d[\d .\u00a0,]*)\s+(?:shares|aksjer)\b',re.I|re.S)

def norm(v): return re.sub(r'[^a-z0-9]+',' ',(v or '').lower().replace('ø','o').replace('æ','ae').replace('å','a')).strip()
def date_of(t):
    m=re.search(r'\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b',t or '')
    if m:return f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'
    m=re.search(r'\b(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})\b',t or '')
    return f'{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}' if m else None

def issuer_ok(body,ticker,name):
    n=norm(body); cname,aliases=ISSUERS.get(ticker,(name,()))
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
    return {'ticker':ticker,'date':date_of(body),'trade_date':date_of(body),'title':title or 'Primary insider transaction','direction':direction,'transaction_type':direction if direction in ('buy','sell') else 'other','shares':shares,'insider':person,'source':source,'verified_detail':direction in ('buy','sell') or shares is not None,'summary':' '.join(body.split())[:1000],'url':url}

def fetch(session,url,params=None):
    r=session.get(url,params=params,timeout=20,allow_redirects=True)
    if r.status_code>=400: raise RuntimeError(f'HTTP {r.status_code}')
    return r.text

def install():
    try: from providers import NordicRegulatoryProvider
    except Exception: return
    if getattr(NordicRegulatoryProvider,'_robust_insider_patch_v3',False): return
    def insider(self,ticker,company_name=''):
        ticker=(ticker or '').upper(); name=company_name or ISSUERS.get(ticker,(ticker,()))[0]
        session=getattr(self,'session',requests.Session(impersonate='chrome')); candidates=[]; seen=set()
        pages=[]
        if ticker in ISSUER_ARCHIVES: pages.append(ISSUER_ARCHIVES[ticker])
        if ticker=='LSG': pages.append('https://live.euronext.com/en/product/equities/NO0003096208-XOSL/company-information')
        pages.append('https://live.euronext.com/en/markets/oslo/equities/company-news')
        for page in pages:
            try: html=fetch(session,page,{'keys':ticker,'page':0})
            except Exception: continue
            p=_Parser(); p.feed(html)
            for href,label in p.links:
                if '/products/equities/company-news/' not in href: continue
                full=href if href.startswith('http') else 'https://live.euronext.com'+href
                if full in seen: continue
                low=norm(label)
                if ticker in ISSUER_ARCHIVES or any(x in low for x in ('insider','primar','pdmr','mandatory notification','meldepliktig')):
                    seen.add(full); candidates.append((full,label))
        items=[]
        for url,label in candidates[:40]:
            try:
                detail=fetch(session,url); p=_Parser(); p.feed(detail); body=p.text; low=norm(body)
                if not any(norm(x) in low for x in PHRASES): continue
                if not issuer_ok(body,ticker,name): continue
                item=parse_trade(body,ticker,label,'Euronext Oslo Børs Newspoint',url)
                if item['verified_detail']: items.append(item)
            except Exception: continue
        # Yahoo syndicated release fallback.
        if not items:
            try:
                q=quote(f'{name} Primary Insider Transaction')
                data=session.get(f'https://query2.finance.yahoo.com/v1/finance/search?q={q}&newsCount=10',timeout=15).json()
                for n in data.get('news',[]):
                    title=n.get('title',''); url=n.get('link') or ''
                    if not any(x in norm(title) for x in ('primary insider','primærinsider','mandatory notification','meldepliktig')): continue
                    try:
                        detail=fetch(session,url); p=_Parser(); p.feed(detail); body=p.text
                    except Exception: continue
                    if not issuer_ok(body,ticker,name) or not any(norm(x) in norm(body) for x in PHRASES): continue
                    item=parse_trade(body,ticker,title,'Yahoo Finance syndicated issuer release',url)
                    if item['verified_detail']: items.append(item)
            except Exception: pass
        dedup={}
        for x in items:
            k=(x.get('date'),x.get('direction'),x.get('shares'),norm(x.get('insider')))
            if k not in dedup: dedup[k]=x
        items=sorted(dedup.values(),key=lambda x:x.get('date') or '',reverse=True)[:12]
        buys=sum(x['direction']=='buy' for x in items); sells=sum(x['direction']=='sell' for x in items)
        now=datetime.now(timezone.utc).isoformat()
        if items:
            return {'ticker':ticker,'items':items,'source':'Euronext Oslo Børs Newspoint + issuer release fallback','status':'live','buy_count':buys,'sell_count':sells,'unknown_count':len(items)-buys-sells,'verified_detail_count':len(items),'signal':'buying' if buys>sells else 'selling' if sells>buys else 'activity','updated_at':now}
        return {'ticker':ticker,'items':[],'source':'Euronext Oslo Børs Newspoint + issuer release fallback','status':'no_recent_disclosures','buy_count':0,'sell_count':0,'unknown_count':0,'verified_detail_count':0,'signal':'unavailable','updated_at':now}
    NordicRegulatoryProvider.insider=insider; NordicRegulatoryProvider._robust_insider_patch_v3=True
install()
