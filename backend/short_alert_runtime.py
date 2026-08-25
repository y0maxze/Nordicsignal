"""Public short-position change alerts and transparent market-pressure proxies."""

from statistics import mean


def _to_percent(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text=str(value).strip().replace('%','').replace(',','.')
    if text.startswith('<'):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _short_change_from_cache(provider, result):
    items=result.get('items') or []
    if not items:
        return result
    selected=max(items,key=lambda x:x.get('date') or '')
    isin=selected.get('isin')
    instrument=next((x for x in (provider._short_cache or []) if x.get('isin')==isin),None)
    events=sorted((instrument or {}).get('events') or [],key=lambda x:x.get('date') or '',reverse=True)
    current=_to_percent(selected.get('short_percent'))
    previous=_to_percent(events[1].get('shortPercent')) if len(events)>1 else None
    delta=(current-previous) if current is not None and previous is not None else None
    alert_level='none'; alert_text=None
    if delta is not None and delta>=0.50:
        alert_level='high'; alert_text=f'Offentlig netto short økte {delta:.2f} prosentpoeng.'
    elif delta is not None and delta>=0.10:
        alert_level='elevated'; alert_text=f'Offentlig netto short økte {delta:.2f} prosentpoeng.'
    elif delta is not None and delta<=-0.10:
        alert_level='easing'; alert_text=f'Offentlig netto short falt {abs(delta):.2f} prosentpoeng.'
    elif current is not None and current>=3.0:
        alert_level='elevated'; alert_text=f'Høy offentlig netto short: {current:.2f}%.'
    result.update({
        'previous_short_percent':previous,
        'short_change_pp':delta,
        'short_alert_level':alert_level,
        'short_alert':alert_text,
        'public_threshold_pct':0.5,
        'reporting_threshold_pct':0.1,
        'public_data_note':'Offentlig SSR viser bare posisjoner på minst 0,5 %. Endringer under offentlig terskel er ikke synlige.',
    })
    return result


def _long_proxy(volume_ratio, change_pct, short):
    """Classify transparent bullish pressure without pretending to observe real long orders."""
    ratio=float(volume_ratio) if volume_ratio is not None else None
    change=float(change_pct) if change_pct is not None else None
    short_delta=short.get('short_change_pp') if isinstance(short,dict) else None
    reasons=[]
    score=0
    if ratio is not None and ratio>=3.0:
        score+=2; reasons.append(f'volum {ratio:.1f}× 20-dagers snitt')
    elif ratio is not None and ratio>=2.0:
        score+=1; reasons.append(f'volum {ratio:.1f}× 20-dagers snitt')
    if change is not None and change>=2.0:
        score+=2; reasons.append(f'kurs +{change:.2f}%')
    elif change is not None and change>=1.0:
        score+=1; reasons.append(f'kurs +{change:.2f}%')
    if short_delta is not None and short_delta<=-0.25:
        score+=1; reasons.append(f'offentlig short ned {abs(short_delta):.2f} pp')
    if ratio is None or change is None or change<=0:
        return {'level':'none','message':None,'score':0,'reasons':reasons,'is_proxy':True}
    if score>=4:
        level='high'
    elif score>=2:
        level='elevated'
    else:
        level='none'
    message=(f'LONG-proxy: sterk kjøpsinteresse indikert av {", ".join(reasons)}.' if level=='high' else
             f'LONG-proxy: mulig kjøpspress ({", ".join(reasons)}).' if level=='elevated' else None)
    return {'level':level,'message':message,'score':score,'reasons':reasons,'is_proxy':True}


def install():
    try:
        import extra_api
        from providers import NordicRegulatoryProvider, YahooProvider
    except Exception:
        return
    if getattr(extra_api,'_market_pressure_patch_v2',False):
        return

    if not getattr(NordicRegulatoryProvider,'_short_alert_patch_v1',False):
        original_short=NordicRegulatoryProvider.short
        def enhanced_short(self,ticker,company_name=''):
            return _short_change_from_cache(self,original_short(self,ticker,company_name))
        NordicRegulatoryProvider.short=enhanced_short
        NordicRegulatoryProvider._short_alert_patch_v1=True

    original_install=extra_api.install
    def patched_install(app):
        original_install(app)
        market=YahooProvider(); regulatory=NordicRegulatoryProvider()

        @app.get('/api/market-pressure/{ticker}')
        def market_pressure(ticker:str):
            ticker=ticker.upper(); company=extra_api._company_name(ticker)
            try:
                short=regulatory.short(ticker,company)
            except Exception as exc:
                short={'ticker':ticker,'status':'unavailable','items':[],'error':str(exc),'short_alert_level':'none'}
            try:
                quote=market.quote(ticker)
                history=market.historical(ticker,'1m')
            except Exception as exc:
                quote={'ticker':ticker,'price':None,'change_pct':None,'volume':None,'error':str(exc)}; history=[]
            volumes=[float(x['volume']) for x in history if x.get('volume') not in (None,0)]
            current_volume=float(quote.get('volume')) if quote.get('volume') not in (None,0) else (volumes[-1] if volumes else None)
            baseline=volumes[:-1][-20:] if len(volumes)>1 else []
            avg_volume=mean(baseline) if baseline else None
            volume_ratio=current_volume/avg_volume if current_volume is not None and avg_volume else None
            change=quote.get('change_pct')
            pressure='neutral'; pressure_text='Ingen tydelig volum-/kursanomali.'
            if volume_ratio is not None and volume_ratio>=2 and change is not None and change>=1:
                pressure='buying_proxy'; pressure_text='Høyt omsatt volum samtidig med kursoppgang – mulig kjøpspress-proxy.'
            elif volume_ratio is not None and volume_ratio>=2 and change is not None and change<=-1:
                pressure='selling_proxy'; pressure_text='Høyt omsatt volum samtidig med kursfall – mulig salgspress-proxy.'
            long_signal=_long_proxy(volume_ratio,change,short)
            alerts=[]
            if short.get('short_alert'):
                alerts.append({'type':'short','level':short.get('short_alert_level'),'message':short.get('short_alert')})
            if long_signal.get('message'):
                alerts.append({'type':'long','level':long_signal.get('level'),'message':long_signal.get('message')})
            if volume_ratio is not None and volume_ratio>=2:
                alerts.append({'type':'volume','level':'elevated','message':f'Volum er ca. {volume_ratio:.1f}× 20-dagers snitt.'})
            return {
                'ticker':ticker,
                'short':short,
                'long_proxy':long_signal,
                'price_change_pct':change,
                'current_volume':current_volume,
                'average_volume_20d':avg_volume,
                'volume_ratio':volume_ratio,
                'pressure_proxy':pressure,
                'pressure_text':pressure_text,
                'alerts':alerts,
                'order_book_available':False,
                'order_book_note':'Dette er ikke Level 2 ordrebok. LONG-/SHORT-proxyene bruker offentlig shortdata, kurs og volum. Reelle ventende kjøps-/salgsordre krever lisensiert Euronext Oslo Børs markedsdybde.',
            }

    extra_api.install=patched_install
    extra_api._market_pressure_patch_v2=True


install()
