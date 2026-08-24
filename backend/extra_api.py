from datetime import datetime, timezone
from urllib.parse import quote_plus

from fastapi import HTTPException
from pydantic import BaseModel, Field

from database import connect
from providers import YahooProvider


def _now():
    return datetime.now(timezone.utc).isoformat()


def _ensure_schema():
    conn = connect()
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS paper_accounts (
        id INTEGER PRIMARY KEY CHECK(id=1),
        starting_cash REAL NOT NULL DEFAULT 100000,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS paper_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL DEFAULT 1,
        ticker TEXT NOT NULL,
        side TEXT NOT NULL CHECK(side IN ('buy','sell')),
        shares REAL NOT NULL,
        price REAL NOT NULL,
        fee REAL NOT NULL DEFAULT 0,
        executed_at TEXT NOT NULL,
        note TEXT,
        FOREIGN KEY(account_id) REFERENCES paper_accounts(id)
    );
    ''')
    if not conn.execute('SELECT 1 FROM paper_accounts WHERE id=1').fetchone():
        now = _now()
        conn.execute('INSERT INTO paper_accounts(id,starting_cash,created_at,updated_at) VALUES(1,?,?,?)',(100000,now,now))
    conn.commit(); conn.close()


class TradeIn(BaseModel):
    ticker: str = Field(min_length=1, max_length=12)
    side: str
    shares: float = Field(gt=0)
    price: float | None = Field(default=None, gt=0)
    fee: float = Field(default=0, ge=0)
    note: str | None = Field(default=None, max_length=240)


class AccountIn(BaseModel):
    starting_cash: float = Field(gt=0, le=1000000000)


def _quote(provider, ticker):
    q = provider.quote(ticker)
    if q.get('price') is None:
        raise HTTPException(502, detail='Live quote unavailable')
    return q


def _positions(provider):
    conn = connect()
    account = conn.execute('SELECT starting_cash FROM paper_accounts WHERE id=1').fetchone()
    trades = conn.execute('SELECT * FROM paper_trades WHERE account_id=1 ORDER BY id').fetchall()
    conn.close()
    starting = float(account['starting_cash']) if account else 100000.0
    cash = starting
    positions = {}
    for t in trades:
        ticker=t['ticker']; shares=float(t['shares']); gross=shares*float(t['price']); fee=float(t['fee'] or 0)
        if t['side']=='buy':
            cash -= gross + fee; positions[ticker]=positions.get(ticker,0)+shares
        else:
            cash += gross - fee; positions[ticker]=positions.get(ticker,0)-shares
    result=[]
    for ticker, shares in positions.items():
        if abs(shares) < 1e-10: continue
        try: q=_quote(provider,ticker); price=float(q['price'])
        except Exception: price=None
        value=shares*price if price is not None else None
        cost=0.0
        for t in trades:
            if t['ticker']==ticker:
                gross=float(t['shares'])*float(t['price']); fee=float(t['fee'] or 0)
                cost += gross+fee if t['side']=='buy' else -(gross-fee)
        pnl=(value-cost) if value is not None else None
        result.append({'ticker':ticker,'shares':shares,'price':price,'value':value,'cost_basis':cost,'pnl':pnl,'change_pct':(pnl/cost*100 if pnl is not None and cost else None)})
    market_value=sum(x['value'] or 0 for x in result)
    return {'starting_cash':starting,'cash':cash,'positions':result,'market_value':market_value,'equity':cash+market_value,'pnl':cash+market_value-starting,'pnl_pct':(cash+market_value-starting)/starting*100}


def _dividends(provider, ticker, start_ts, end_ts):
    symbol=provider.symbol(ticker)
    data=provider._get(f'{provider.BASE}/v8/finance/chart/{symbol}', {'period1':int(start_ts),'period2':int(end_ts),'interval':'1d','events':'div,splits'})
    events=((data.get('chart') or {}).get('result') or [{}])[0].get('events') or {}
    out=[]
    for ts, item in (events.get('dividends') or {}).items():
        amount=item.get('amount') if isinstance(item,dict) else None
        if amount is not None: out.append({'timestamp':int(ts),'amount':float(amount)})
    return sorted(out,key=lambda x:x['timestamp'])


def _backtest(provider, ticker, start, end, initial_cash, monthly_investment, reinvest_dividends):
    history=provider.historical(ticker,'max')
    start_ts=int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp()) if 'T' not in start else int(datetime.fromisoformat(start.replace('Z','+00:00')).timestamp())
    end_ts=int(datetime.fromisoformat(end).replace(tzinfo=timezone.utc).timestamp())+86399 if 'T' not in end else int(datetime.fromisoformat(end.replace('Z','+00:00')).timestamp())
    rows=[x for x in history if start_ts<=int(x['timestamp'])<=end_ts]
    if not rows: raise HTTPException(404,detail='No historical data for selected period')
    divs=_dividends(provider,ticker,start_ts-86400,end_ts+86400)
    div_by_day={datetime.fromtimestamp(d['timestamp'],timezone.utc).date().isoformat():d['amount'] for d in divs}
    cash=float(initial_cash); shares=0.0; invested=0.0; last_month=None; points=[]; tx=[]
    for row in rows:
        d=datetime.fromtimestamp(int(row['timestamp']),timezone.utc).date(); price=float(row['close'])
        if last_month != (d.year,d.month):
            contribution=float(initial_cash if last_month is None and monthly_investment<=0 else monthly_investment)
            if last_month is None and monthly_investment>0: contribution += float(initial_cash)
            cash += contribution
            buy_shares=contribution/price if price else 0
            shares += buy_shares; cash -= buy_shares*price; invested += contribution
            tx.append({'date':d.isoformat(),'side':'buy','shares':buy_shares,'price':price,'amount':contribution})
            last_month=(d.year,d.month)
        div_per_share=div_by_day.get(d.isoformat(),0)
        if div_per_share and shares:
            dividend=shares*div_per_share
            if reinvest_dividends and price>0:
                add=dividend/price; shares+=add; tx.append({'date':d.isoformat(),'side':'dividend_reinvest','shares':add,'price':price,'amount':dividend})
            else:
                cash+=dividend; tx.append({'date':d.isoformat(),'side':'dividend_cash','shares':shares,'price':price,'amount':dividend})
        equity=cash+shares*price
        points.append({'date':d.isoformat(),'price':price,'shares':shares,'cash':cash,'value':shares*price,'equity':equity,'invested':invested})
    end_equity=points[-1]['equity']; total_return=end_equity-invested
    return {'ticker':ticker,'start':rows[0]['date'],'end':rows[-1]['date'],'initial_cash':initial_cash,'monthly_investment':monthly_investment,'reinvest_dividends':reinvest_dividends,'invested':invested,'final_equity':end_equity,'return':total_return,'return_pct':total_return/invested*100 if invested else 0,'shares':shares,'cash':cash,'dividends':sum(x['amount'] for x in tx if x['side'].startswith('dividend')),'points':points,'transactions':tx[-30:]}


def install(app):
    _ensure_schema(); provider=YahooProvider()

    @app.get('/api/paper/account')
    def paper_account():
        conn=connect(); row=conn.execute('SELECT * FROM paper_accounts WHERE id=1').fetchone(); conn.close()
        return dict(row) if row else {'id':1,'starting_cash':100000}

    @app.post('/api/paper/account')
    def set_paper_account(payload: AccountIn):
        conn=connect(); now=_now(); conn.execute('UPDATE paper_accounts SET starting_cash=?,updated_at=? WHERE id=1',(payload.starting_cash,now)); conn.commit(); conn.close(); return paper_account()

    @app.get('/api/paper/portfolio')
    def paper_portfolio(): return _positions(provider)

    @app.get('/api/paper/trades')
    def paper_trades(limit:int=100):
        conn=connect(); rows=conn.execute('SELECT * FROM paper_trades WHERE account_id=1 ORDER BY id DESC LIMIT ?',(min(limit,500),)).fetchall(); conn.close(); return {'items':[dict(r) for r in rows]}

    @app.post('/api/paper/trades')
    def paper_trade(payload: TradeIn):
        side=payload.side.lower(); ticker=payload.ticker.upper()
        if side not in ('buy','sell'): raise HTTPException(400,detail='side must be buy or sell')
        price=payload.price or float(_quote(provider,ticker)['price']); shares=float(payload.shares); fee=float(payload.fee)
        port=_positions(provider); position=next((p for p in port['positions'] if p['ticker']==ticker),None); held=position['shares'] if position else 0
        if side=='buy' and port['cash'] < shares*price+fee: raise HTTPException(400,detail='Insufficient paper cash')
        if side=='sell' and held < shares-1e-10: raise HTTPException(400,detail=f'Insufficient paper shares; holding {held:g}')
        conn=connect(); conn.execute('INSERT INTO paper_trades(account_id,ticker,side,shares,price,fee,executed_at,note) VALUES(1,?,?,?,?,?,?,?)',(ticker,side,shares,price,fee,_now(),payload.note)); conn.commit(); conn.close()
        return {'status':'ok','trade':{'ticker':ticker,'side':side,'shares':shares,'price':price,'fee':fee},'portfolio':_positions(provider)}

    @app.post('/api/paper/reset')
    def paper_reset():
        conn=connect(); conn.execute('DELETE FROM paper_trades WHERE account_id=1'); conn.commit(); conn.close(); return {'status':'ok','portfolio':_positions(provider)}

    @app.get('/api/paper/backtest')
    def paper_backtest(ticker:str, start:str, end:str, initial_cash:float=100000, monthly_investment:float=0, reinvest_dividends:bool=True):
        if initial_cash<=0 or monthly_investment<0: raise HTTPException(400,detail='Invalid investment amounts')
        return _backtest(provider,ticker.upper(),start,end,initial_cash,monthly_investment,reinvest_dividends)

    @app.get('/api/news/{ticker}')
    def stock_news(ticker:str, limit:int=12):
        ticker=ticker.upper(); limit=max(1,min(limit,20)); items=[]
        try:
            url=f'{provider.BASE}/v1/finance/search?q={quote_plus(ticker)}&quotesCount=1&newsCount={limit}'
            data=provider._get(url)
            for n in data.get('news') or []:
                title=n.get('title') or ''; publisher=n.get('publisher') or 'Unknown'; link=n.get('link') or ''; ts=n.get('providerPublishTime')
                dt=datetime.fromtimestamp(ts,timezone.utc).isoformat() if ts else None
                low=title.lower(); category='Nyhet'
                if any(k in low for k in ('insider','primary insider','mandatory notification')): category='Insider'
                elif any(k in low for k in ('report','results','quarter','q1','q2','q3','q4','earnings')): category='Rapport'
                elif any(k in low for k in ('dividend','ex-dividend')): category='Utbytte'
                elif any(k in low for k in ('acqui','merger','contract','order','agreement')): category='Selskap'
                items.append({'ticker':ticker,'title':title,'publisher':publisher,'url':link,'published_at':dt,'category':category,'summary':title})
        except Exception as exc:
            return {'ticker':ticker,'items':[],'status':'unavailable','source':'Yahoo Finance search','error':str(exc)}
        return {'ticker':ticker,'items':items,'status':'live_news' if items else 'no_news','source':'Yahoo Finance search'}

    @app.get('/api/news/{ticker}/summary')
    def news_summary(ticker:str):
        d=stock_news(ticker,8); items=d.get('items') or []
        counts={}
        for x in items: counts[x['category']]=counts.get(x['category'],0)+1
        return {'ticker':ticker.upper(),'headline_count':len(items),'categories':counts,'summary':(' · '.join(x['title'] for x in items[:3]) if items else 'Ingen nye offentlige nyheter funnet.'),'items':items}
