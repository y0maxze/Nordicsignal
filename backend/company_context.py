"""Automatic company context. Independent research storage; never a model input.

GET reads snapshots only. The protected scheduler performs bounded enrichment.
News matching requires a unique exact normalized issuer name, never fuzzy tickers.
"""
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import json
import logging
import math
import re
import threading
from urllib.parse import urlsplit
from database import connect

log = logging.getLogger(__name__)
_LOCK = threading.Lock()
METRICS = {'annualTotalRevenue':'Omsetning', 'annualNetIncome':'Nettoresultat',
           'annualFreeCashFlow':'Fri kontantstrøm', 'annualTotalDebt':'Gjeld',
           'annualStockholdersEquity':'Egenkapital'}
FINANCING = re.compile(r'\b(rights issue|private placement|share capital increase|subsequent offering|repair offering|subscription rights|bridge financ\w*|bridge facility|refinanc\w*|convertible loan|emisjon\w*|kapitalforhøyelse\w*|tegningsrett\w*|fortrinnsrett\w*)\b', re.I)


def now():
    return datetime.now(timezone.utc)


def stamp(value):
    try:
        d = datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return d if d.tzinfo else None
    except (ValueError, TypeError):
        return None


def norm(value):
    words = re.sub(r'[^\w]+', ' ', str(value or '').casefold()).split()
    while words and words[-1] in {'asa','as','ab','plc','ltd','limited'}:
        words.pop()
    return ' '.join(words)


def ensure_schema():
    c = connect()
    try:
        c.executescript('''CREATE TABLE IF NOT EXISTS company_context_issuers (
          identity TEXT PRIMARY KEY, company TEXT NOT NULL, ticker TEXT, source_url TEXT NOT NULL, attempted_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS company_context_profiles (
          ticker TEXT PRIMARY KEY, identity TEXT NOT NULL, payload TEXT NOT NULL,
          attempted_at TEXT NOT NULL, captured_at TEXT, status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS company_context_events (
          event_key TEXT PRIMARY KEY, ticker TEXT NOT NULL, identity TEXT NOT NULL,
          payload TEXT NOT NULL, observed_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS company_context_state (
          id INTEGER PRIMARY KEY, checked_at TEXT NOT NULL, status TEXT NOT NULL);
        ''')
        c.commit()
    finally:
        c.close()


def universe():
    """Re-enrol every scan, including newly admitted issuers; reject collisions."""
    rows = []
    for sql in ('SELECT ticker,name AS company,sector FROM stocks WHERE active=1',
                'SELECT ticker,company FROM company_context_issuers WHERE ticker IS NOT NULL',
                "SELECT ticker,company,isin,listing_date FROM ipo_listings WHERE location='Oslo'"):
        c = connect()
        try:
            rows += [dict(r) for r in c.execute(sql).fetchall()]
        except Exception:
            log.warning('Company context universe source unavailable')
        finally:
            c.close()
    grouped = defaultdict(list)
    for row in rows:
        ticker = str(row.get('ticker') or '').upper().removesuffix('.OL')
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9-]{0,19}',ticker) or not norm(row.get('company')):
            continue
        if row.get('listing_date') and str(row['listing_date']) > now().date().isoformat():
            continue
        grouped[ticker].append(row)
    out = {}
    for ticker, matches in grouped.items():
        if len({norm(r['company']) for r in matches}) != 1:
            continue
        out[ticker] = {**matches[0], 'ticker':ticker, 'identity':norm(matches[0]['company'])}
    return out


def project_financials(series, at):
    out = []
    for key,label in METRICS.items():
        points = [p for block in series for p in block.get(key,[]) if isinstance(p,dict)]
        points = [p for p in points if re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(p.get('asOfDate',''))) and p['asOfDate'] <= at.date().isoformat()]
        if not points:
            continue
        p = max(points,key=lambda p:p['asOfDate'])
        value = p.get('reportedValue')
        if isinstance(value,dict):value=value.get('raw')
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):continue
        currency = p.get('currencyCode')
        out.append({'label':label,'value':value,'currency':currency if re.fullmatch(r'[A-Z]{3}',str(currency or '')) else None,
                    'period':p['asOfDate'],'period_type':p.get('periodType') or 'annual'})
    return out


def collect_profile(row, provider):
    """Separate failures preserve usable partial data; no unsafe derived multiples."""
    at = now()
    payload = {'company':row['company'],'ticker':row['ticker'],'sector':row.get('sector'),
               'description':None,'financials':[], 'source_url':'https://finance.yahoo.com/quote/'+row['ticker']+'.OL/',
               'source':'Yahoo Finance', 'source_status':{}}
    symbol = row['ticker']+'.OL'
    try:
        data = provider._get(provider.BASE+'/v10/finance/quoteSummary/'+symbol,
                             {'modules':'assetProfile,price'},need_crumb=True)
        result = (data.get('quoteSummary',{}).get('result') or [{}])[0]
        price = result.get('price') or {}
        # Require symbol and issuer identity; do not silently accept reused tickers.
        if price.get('symbol') != symbol or norm(price.get('longName') or price.get('shortName')) != row['identity']:
            raise ValueError('identity mismatch')
        profile = result.get('assetProfile') or {}
        payload.update(description=str(profile.get('longBusinessSummary') or '')[:5000] or None,
                       sector=profile.get('sector') or payload['sector'])
        payload['source_status']['description']='stored' if payload['description'] else 'unavailable'
    except Exception:
        payload['source_status']['description']='unavailable'
    try:
        result = provider.fundamentals(row['ticker'])
        if result.get('symbol') != symbol:raise ValueError('symbol mismatch')
        payload['financials']=project_financials(result.get('series') or [],at)
        payload['source_status']['financials']='stored' if payload['financials'] else 'unavailable'
    except Exception:
        payload['source_status']['financials']='unavailable'
    return payload


def event_for(item, identities, at):
    name = norm(item.get('company'))
    matches = identities.get(name,[])
    title = str(item.get('title') or '')
    published = stamp(item.get('published_at'))
    try:u=urlsplit(str(item.get('url') or ''))
    except ValueError:return None
    if (len(matches)!=1 or item.get('official') is not True or u.scheme!='https' or
        u.hostname!='live.euronext.com' or u.username or not published or
        not timedelta(0)<=at-published<=timedelta(days=180) or not FINANCING.search(title)):
        return None
    # This is a document flag, NOT a claimed current issue status or cash emergency.
    return {'ticker':matches[0], 'identity':name, 'title':title, 'url':u.geturl(),
            'published_at':published.isoformat(),'observed_at':at.isoformat(),
            'kind':'financing_document','status':'Les siste vilkår i originalmeldingen'}


def enrol_news_issuers(items, provider, at, limit=4):
    """Expand research coverage from official news, never the scoring universe."""
    c=connect()
    try:
        previous={r['identity']:dict(r) for r in c.execute('SELECT * FROM company_context_issuers').fetchall()}
    finally:c.close()
    existing={r['identity'] for r in universe().values()}
    count=0
    for item in items:
        name=norm(item.get('company'))
        published=stamp(item.get('published_at'))
        try:u=urlsplit(str(item.get('url') or ''))
        except ValueError:continue
        if (not name or name in existing or item.get('official') is not True or
            u.scheme!='https' or u.hostname!='live.euronext.com' or u.username or
            not published or not timedelta(0)<=at-published<=timedelta(days=180)):continue
        old=previous.get(name,{})
        if old and at-(stamp(old['attempted_at']) or at)<timedelta(days=1):continue
        ticker=None
        try:
            data=provider._get(provider.BASE+'/v1/finance/search',{'q':item['company'],'quotesCount':10,'newsCount':0,'enableFuzzyQuery':'false'})
            matches={str(q.get('symbol')) for q in data.get('quotes',[]) if q.get('quoteType')=='EQUITY' and
                     str(q.get('symbol') or '').endswith('.OL') and
                     norm(q.get('longname') or q.get('shortname'))==name}
            if len(matches)==1:ticker=matches.pop().removesuffix('.OL')
        except Exception:
            log.warning('Company context issuer resolution unavailable')
        c=connect()
        try:
            c.execute('INSERT INTO company_context_issuers(identity,company,ticker,source_url,attempted_at) VALUES(?,?,?,?,?) ON CONFLICT(identity) DO UPDATE SET ticker=excluded.ticker,attempted_at=excluded.attempted_at',
                      (name,item['company'],ticker,item['url'],at.isoformat()))
            c.commit()
        finally:c.close()
        previous[name]={'attempted_at':at.isoformat()};count+=1
        if count>=limit:break


def scan_once(provider=None, fetch_news=None, batch_size=4):
    if not _LOCK.acquire(blocking=False):return {'status':'busy'}
    try:
        ensure_schema()
        at = now()
        if provider is None:
            from providers import YahooProvider
            provider=YahooProvider()
        rows = universe()
        if fetch_news is None:
            from general_news_runtime import parse_general_euronext_html
            from news_runtime import _fetch_text, EURONEXT_LATEST
            fetch_news=lambda:parse_general_euronext_html(_fetch_text(EURONEXT_LATEST),60)
        identities=defaultdict(list)
        for ticker,row in rows.items():identities[row['identity']].append(ticker)
        news_status='unavailable'
        events=[]
        try:
            items=fetch_news()
            enrol_news_issuers(items,provider,at)
            rows=universe()
            identities=defaultdict(list)
            for ticker,row in rows.items():identities[row['identity']].append(ticker)
            news_status='partial' if items else 'unavailable'
            events=[e for item in items if (e:=event_for(item,identities,at))]
        except Exception:
            log.warning('Company context exchange news unavailable')
        c=connect()
        try:
            for e in events:
                c.execute('INSERT INTO company_context_events(event_key,ticker,identity,payload,observed_at) VALUES(?,?,?,?,?) ON CONFLICT(event_key) DO NOTHING',
                          (e['ticker']+'|'+e['url'],e['ticker'],e['identity'],json.dumps(e),at.isoformat()))
            c.execute('INSERT INTO company_context_state(id,checked_at,status) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET checked_at=excluded.checked_at,status=excluded.status',(at.isoformat(),news_status))
            previous={r['ticker']:dict(r) for r in c.execute('SELECT * FROM company_context_profiles').fetchall()}
            c.commit()
        finally:c.close()
        due=[r for t,r in rows.items() if t not in previous or previous[t]['identity']!=r['identity'] or
             at-(stamp(previous[t]['attempted_at']) or datetime.min.replace(tzinfo=timezone.utc))>=timedelta(hours=24)]
        due.sort(key=lambda r:previous.get(r['ticker'],{}).get('attempted_at',''))
        for row in due[:batch_size]:
            data=collect_profile(row,provider)
            usable=bool(data['description'] or data['financials'])
            old=previous.get(row['ticker'],{})
            captured=at.isoformat() if usable else None
            status='partial' if usable else 'unavailable'
            if not usable and old.get('identity')==row['identity'] and old.get('captured_at'):
                data=json.loads(old['payload']);captured=old['captured_at'];status='stale'
            c=connect()
            try:
                c.execute('INSERT INTO company_context_profiles(ticker,identity,payload,attempted_at,captured_at,status) VALUES(?,?,?,?,?,?) ON CONFLICT(ticker) DO UPDATE SET identity=excluded.identity,payload=excluded.payload,attempted_at=excluded.attempted_at,captured_at=excluded.captured_at,status=excluded.status',
                          (row['ticker'],row['identity'],json.dumps(data),at.isoformat(),captured,status))
                c.commit()
            finally:c.close()
        return {'status':'ok','universe_count':len(rows),'refreshed':min(len(due),batch_size),'pending':max(0,len(due)-batch_size),'score_effect':0}
    finally:_LOCK.release()


def read_all():
    """One cached-data query set, no schema changes or external I/O on GET."""
    at=now();profiles={};events=defaultdict(list);state={}
    c=connect()
    try:
        for row in c.execute('SELECT * FROM company_context_profiles').fetchall():
            r=dict(row);data=json.loads(r['payload']);captured=stamp(r['captured_at'])
            profiles[r['ticker']]={**data,'identity':r['identity'],'captured_at':r['captured_at'],
                'attempted_at':r['attempted_at'],'status':'stale' if captured and at-captured>timedelta(days=2) else r['status']}
        for row in c.execute('SELECT payload FROM company_context_events ORDER BY observed_at DESC').fetchall():
            e=json.loads(row['payload']);d=stamp(e['published_at'])
            if d and timedelta(0)<=at-d<=timedelta(days=180):events[e['ticker']].append(e)
        row=c.execute('SELECT * FROM company_context_state WHERE id=1').fetchone()
        state=dict(row) if row else {}
    except Exception:
        log.warning('Company context snapshots unavailable')
    finally:c.close()
    return profiles,events,state


def context(ticker, snapshots=None, identity=None):
    profiles,events,state=snapshots if snapshots is not None else read_all()
    p=profiles.get(ticker,{})
    if identity and p.get('identity')!=norm(identity):p={}
    event_rows=[e for e in events.get(ticker,[]) if not identity or e['identity']==norm(identity)][:8]
    return {**p,'ticker':ticker,'status':p.get('status','collecting'),'score_effect':0,
            'financing_documents':event_rows,'news_checked_at':state.get('checked_at'),
            'news_status':state.get('status','unavailable'),
            'coverage':'Siste tilgjengelige børsmeldinger, ikke full historikk. Ingen treff betyr ikke at emisjon eller finansieringsrisiko er utelukket.'}
