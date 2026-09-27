"""Bounded official NewsWeb research ingestion, independent of signal inputs.

Public client contract observed at newsweb.oslobors.no on 2026-09-27.
Historical issuer metadata can be remapped after a rename/merger: require the
document title prefix, current issuer name AND ticker to agree. Fail closed.
"""
from datetime import timedelta
from zoneinfo import ZoneInfo
import hashlib
import json
import re
import uuid

API = 'https://api3.oslo.oslobors.no/v1/newsreader/'
SOURCE = 'https://newsweb.oslobors.no/message/'
MAX_BYTES = 3_000_000
LOOKBACK_DAYS = 730


def request(kind, params):
    if kind not in {'list','message'}:raise ValueError('Unsupported NewsWeb request')
    import requests
    with requests.post(API+kind, params=params, headers={'Content-Type':'application/json'},
                       timeout=12, allow_redirects=False, stream=True) as response:
        if response.status_code!=200 or 'application/json' not in response.headers.get('Content-Type',''):
            raise ValueError('NewsWeb unavailable')
        content=bytearray()
        for chunk in response.iter_content(16384):
            content.extend(chunk)
            if len(content)>MAX_BYTES:raise ValueError('NewsWeb response too large')
    data=json.loads(content)
    if data.get('header',{}).get('result.val')!=0 or not isinstance(data.get('data'),dict):
        raise ValueError('NewsWeb invalid response')
    return data['data']


def adapt(raw, universe, at):
    from company_context import norm, stamp, FINANCING, FINANCING_TYPES, financing_evidence
    ticker=raw.get('issuerSign')
    if not isinstance(ticker,str):return None
    row=universe.get(ticker)
    mid=raw.get('messageId'); iid=raw.get('issuerId')
    if (not row or raw.get('test') is not False or type(mid) is not int or mid<=0
        or raw.get('id')!=mid or type(iid) is not int or iid<=0
        or not set(raw.get('markets') or []) & {'XOSL','XOAS','MERK'}):return None
    issuer=raw.get('issuerName') or ''
    if norm(issuer)!=row['identity']:return None
    if sum(r.get('identity')==row['identity'] for r in universe.values())!=1:return None
    suffix=lambda s: re.search(r'\b(ASA|AS)$',str(s).upper().strip())
    a,b=suffix(issuer),suffix(row['company'])
    if a and b and a.group()!=b.group():return None
    title=raw.get('title') or ''
    prefix=re.match(r'^(.+?)(?:\s+[-–—]\s+|:\s+)(.+)$',title)
    if not prefix or norm(prefix[1])!=row['identity']:return None
    a,b=suffix(prefix[1]),suffix(issuer)
    if a and b and a.group()!=b.group():return None
    if not (FINANCING.search(title) or any(p.search(title) for _,p in FINANCING_TYPES)):return None
    published=stamp(raw.get('publishedTime'))
    if not published or published>at:return None
    for field in ('correctionForMessageId','correctedByMessageId'):
        if type(raw.get(field)) is not int or raw[field]<0:return None
    return {'ticker':ticker,'identity':row['identity'],'company':issuer,'title':title,
            'url':SOURCE+str(mid),'published_at':published.isoformat(),'observed_at':at.isoformat(),
            'kind':'financing_document','source_type':'newsweb_oam','source_issuer_id':iid,
            'source_message_id':mid,'correction_for_message_id':raw['correctionForMessageId'],
            'corrected_by_message_id':raw['correctedByMessageId'],
            **financing_evidence(prefix[2]),'status':'Historisk dokumentstatus; les siste vilkår i originalmeldingen'}


def document(event, fetch=None):
    from company_context import stamp
    from financing_documents import parse_lines
    mid=event.get('source_message_id')
    if type(mid) is not int or mid<=0 or event['url']!=SOURCE+str(mid):raise ValueError('Invalid document identity')
    raw=(fetch or request)('message',{'messageId':mid}).get('message')
    if not isinstance(raw,dict):raise ValueError('Missing document')
    expected={'id':mid,'messageId':mid,'issuerId':event['source_issuer_id'],
              'issuerSign':event['ticker'],'issuerName':event['company'],'title':event['title'],
              'correctionForMessageId':event['correction_for_message_id'],
              'correctedByMessageId':event['corrected_by_message_id']}
    if any(raw.get(k)!=v for k,v in expected.items()) or raw.get('test') is not False:
        raise ValueError('Document identity changed')
    if stamp(raw.get('publishedTime'))!=stamp(event['published_at']):raise ValueError('Document date changed')
    body=raw.get('body')
    if not isinstance(body,str) or not body.strip() or len(body.encode())>MAX_BYTES:raise ValueError('Missing body')
    digest=hashlib.sha256(body.encode()).hexdigest()
    if re.search(r'<[a-zA-Z][^>]*>',body):return {},'unsupported_document',digest
    terms,status=parse_lines([' '.join(s.split()) for s in body.splitlines() if s.strip()])
    return terms,status,digest


def ensure_schema(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS company_newsweb_windows (
      day TEXT PRIMARY KEY, attempted_at TEXT, token TEXT, lease_until TEXT, payload TEXT);
    ''')


def scan(connect, universe, at, fetch=None, clock=None):
    from company_context import stamp, save_event, now
    clock=clock or now
    today=at.astimezone(ZoneInfo('Europe/Oslo')).date()
    c=connect()
    try: previous={r['day']:dict(r) for r in c.execute('SELECT * FROM company_newsweb_windows').fetchall()}
    finally:c.close()
    target=None
    for offset in range(LOOKBACK_DAYS):
        day=(today-timedelta(days=offset)).isoformat(); old=previous.get(day,{})
        last=stamp(old.get('attempted_at')); state=json.loads(old.get('payload') or '{}')
        lease=stamp(old.get('lease_until'))
        if (not last or (not state and (not lease or lease<=at))
            or (old.get('token') and lease and lease<=at)
            or (offset>0 and state.get('open_day') is True)
            or (offset==0 and at-last>=timedelta(hours=1))
            or (state.get('status') in {'unavailable','truncated'} and at-last>=timedelta(days=1))):
            target=day;break
    if not target:return {'status':'idle'}
    token=uuid.uuid4().hex;c=connect()
    try:
        c.execute('INSERT INTO company_newsweb_windows(day) VALUES(?) ON CONFLICT(day) DO NOTHING',(target,))
        claimed=c.execute("UPDATE company_newsweb_windows SET token=?,lease_until=?,attempted_at=? WHERE day=? AND (lease_until IS NULL OR lease_until<=?) AND COALESCE(attempted_at,'')=?",
                          (token,(at+timedelta(minutes=3)).isoformat(),at.isoformat(),target,at.isoformat(),previous.get(target,{}).get('attempted_at') or '')).rowcount
        c.commit()
    finally:c.close()
    if not claimed:return {'status':'busy'}
    events=[];state={'status':'unavailable','day':target,'open_day':target==today.isoformat(),
                     'matched':0,'source_count':None,'overflow':None}
    try:
        data=(fetch or request)('list',{'fromDate':target,'toDate':target})
        rows=data.get('messages');overflow=data.get('overflow')
        if not isinstance(rows,list) or type(overflow) is not bool:raise ValueError('Invalid list')
        rejected=0
        for raw in rows:
            d=stamp(raw.get('publishedTime')) if isinstance(raw,dict) else None
            if not d or d.astimezone(ZoneInfo('Europe/Oslo')).date().isoformat()!=target:
                rejected+=1;continue
            try:e=adapt(raw,universe,at)
            except (TypeError,ValueError,KeyError):e=None
            if e:events.append(e)
        state.update(status='truncated' if overflow else 'partial',source_count=len(rows),overflow=overflow,
                     matched=len(events),rejected_dates=rejected)
    except Exception:
        pass  # Retain an explicit failed window, never claim an empty result.
    finished=clock();c=connect()
    try:
        cursor=c.execute('UPDATE company_newsweb_windows SET token=NULL,lease_until=NULL,payload=? WHERE day=? AND token=? AND lease_until>?',
                         (json.dumps(state),target,token,finished.isoformat()))
        if cursor.rowcount:
            for event in events:
                event['observed_at']=finished.isoformat()
                save_event(c,event,finished)
        else:
            state={**state,'status':'lease_lost','matched':0}
        c.commit()
    finally:c.close()
    return state


def coverage(connect):
    c=connect()
    try:rows=c.execute('SELECT day,payload,attempted_at FROM company_newsweb_windows WHERE payload IS NOT NULL ORDER BY day').fetchall()
    finally:c.close()
    values=[json.loads(r['payload']) for r in rows]
    return {'historical_backfill':'partial','queried_days':len(rows),
            'failed_days':sum(v['status']=='unavailable' for v in values),
            'truncated_days':sum(v.get('overflow') is True for v in values),
            'oldest_queried_day':rows[0]['day'] if rows else None,
            'newest_queried_day':rows[-1]['day'] if rows else None,
            'attempted_at':max((r['attempted_at'] for r in rows),default=None),
            'identity_policy':'Ticker, issuer name and title prefix must agree; renamed historical issuers may be omitted.'}
