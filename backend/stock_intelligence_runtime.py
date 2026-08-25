from datetime import datetime, timezone


def classify_news_title(title):
    low=(title or '').lower()
    if any(k in low for k in ('insider','primary insider','mandatory notification','meldepliktig')):
        return 'Insider'
    if any(k in low for k in ('report','results','quarter','q1','q2','q3','q4','earnings','årsrapport','annual report','interim report')):
        return 'Rapport'
    if any(k in low for k in ('dividend','ex-dividend','utbytte','distribution')):
        return 'Utbytte'
    if any(k in low for k in ('acqui','merger','contract','order','agreement','avtale','kontrakt')):
        return 'Selskap'
    return 'Nyhet'


def install():
    try:
        import extra_api
        from dividend_runtime import fetch_dividend_events
    except Exception:
        return
    if getattr(extra_api,'_stock_intelligence_patch_v1',False):
        return
    original=extra_api.install

    def patched_install(app):
        original(app)
        provider=extra_api.YahooProvider()

        @app.get('/api/reports/{ticker}')
        def reports(ticker:str,limit:int=12):
            ticker=ticker.upper(); limit=max(1,min(limit,30)); items=[]; company=extra_api._company_name(ticker)
            try:
                query=f'{company} {ticker}' if company and company.upper()!=ticker else ticker
                data=provider._get(f'{provider.BASE}/v1/finance/search?q={extra_api.quote_plus(query)}&quotesCount=3&newsCount={min(limit*4,80)}')
                for n in data.get('news') or []:
                    if not extra_api.news_matches_ticker(n,ticker,company):
                        continue
                    title=n.get('title') or ''
                    if classify_news_title(title)!='Rapport':
                        continue
                    ts=n.get('providerPublishTime')
                    items.append({
                        'ticker':ticker,
                        'title':title,
                        'publisher':n.get('publisher') or 'Unknown',
                        'url':n.get('link') or '',
                        'published_at':datetime.fromtimestamp(ts,timezone.utc).isoformat() if ts else None,
                        'category':'Rapport',
                        'summary':title,
                        'related_tickers':n.get('relatedTickers') or [],
                    })
                    if len(items)>=limit: break
            except Exception as exc:
                return {'ticker':ticker,'items':[],'status':'unavailable','source':'Yahoo Finance search','error':str(exc)}
            return {'ticker':ticker,'company':company,'items':items,'status':'live_reports' if items else 'no_company_reports','source':'Yahoo Finance search','strict_issuer_filter':True}

        @app.get('/api/dividends/{ticker}')
        def dividends(ticker:str,years:int=10):
            ticker=ticker.upper(); years=max(1,min(years,25)); now=datetime.now(timezone.utc)
            start=int(now.timestamp())-int(years*365.25*86400)
            end=int(now.timestamp())+86400
            try:
                items=fetch_dividend_events(provider,ticker,start,end)
            except Exception as exc:
                return {'ticker':ticker,'items':[],'status':'unavailable','source':'Yahoo Finance chart events','error':str(exc)}
            total=sum(float(x.get('amount') or 0) for x in items)
            latest=items[-1] if items else None
            return {
                'ticker':ticker,
                'items':list(reversed(items)),
                'status':'live_dividends' if items else 'no_dividends',
                'source':'Yahoo Finance chart events',
                'event_count':len(items),
                'total_per_share':total,
                'latest':latest,
            }

        @app.get('/api/intelligence/{ticker}')
        def intelligence(ticker:str):
            ticker=ticker.upper()
            return {
                'ticker':ticker,
                'reports':reports(ticker,8),
                'dividends':dividends(ticker,10),
            }

    extra_api.install=patched_install
    extra_api._stock_intelligence_patch_v1=True

install()
