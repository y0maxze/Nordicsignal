from datetime import datetime, timezone
import json
import re
import subprocess
from pathlib import Path
import market_snapshot as market
from quote_snapshot import quote_snapshot
from oslo_session import previous_close

ROOT=Path(__file__).resolve().parents[1]


def test_market_snapshot_uses_constant_reads_and_does_not_infer_ownership(monkeypatch):
    calls=[]
    def rows(sql):
        calls.append(sql)
        if 'quotes' in sql:return []
        return [{'ticker':'EQNR','observed_at':'2026-09-24T09:00:00Z','payload':json.dumps({'reversal':{'metrics':{'close':270,'close_date':'2026-09-23'}},'opportunity':{'label':'NO_OPPORTUNITY'},'insider_signal_v2':{'evidence_coverage':'no_recent_detail','evidence_item_count':0}})}]
    monkeypatch.setattr(market,'read_rows',rows)
    result=market.snapshot([{'ticker':'EQNR','score':70,'insider':12} for _ in range(100)])
    assert len(calls)==2
    assert result['items'][0]['score']==70
    assert result['items'][0]['ownership_status']=='unavailable'
    assert result['items'][0]['insider_coverage'] is False
    assert result['items'][0]['data_status']=='LAGRET'
    assert result['items'][0]['change_pct'] is None


def test_quote_uses_previous_completed_daily_bar_not_range_start():
    now=datetime(2026,9,24,10,tzinfo=timezone.utc)
    prior=int(datetime(2026,9,23,7,tzinfo=timezone.utc).timestamp())
    today=int(datetime(2026,9,24,7,tzinfo=timezone.utc).timestamp())
    d=quote_snapshot({'meta':{'regularMarketPrice':110,'regularMarketTime':int(now.timestamp()),'chartPreviousClose':80,'exchangeTimezoneName':'Europe/Oslo'},'timestamp':[prior,today],'indicators':{'quote':[{'close':[100,110]}]}},now)
    assert d['previous_close']==100
    assert abs(d['change_pct']-10)<0.00001
    assert d['realtime_verified'] is False
    assert d['data_status']=='FORSINKET'


def test_quote_missing_trade_time_is_not_live():
    assert quote_snapshot({'meta':{'regularMarketPrice':100}})['data_status']=='LAGRET'
    assert quote_snapshot({'meta':{}})['data_status']=='UTILGJENGELIG'


def test_oslo_holiday_and_auction_boundary():
    assert previous_close(datetime(2026,5,15,6,tzinfo=timezone.utc)).date().isoformat()=='2026-05-13'
    assert previous_close(datetime(2026,9,24,14,22,tzinfo=timezone.utc)).date().isoformat()=='2026-09-23'
    assert previous_close(datetime(2026,9,24,14,26,tzinfo=timezone.utc)).minute==25
    assert previous_close(datetime(2027,2,1,tzinfo=timezone.utc)) is None


def test_stock_required_sections_and_data_states_execute():
    page=(ROOT/'frontend/stock.html').read_text()
    script=re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>',page,re.S)[-1]
    script=script[:script.rfind('load().catch')]
    program="""
const vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map();const ctx={URLSearchParams,location:{search:'?ticker=EQNR'},document:{getElementById(id){if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:''});return elements.get(id)}},window:{}};
vm.createContext(ctx);vm.runInContext(SCRIPT,ctx);vm.runInContext("render('overview')",ctx);
for(const id of ['signalTimeline','nsSignalEvidence','chartSection','ownershipSection'])assert.ok(elements.get('content').innerHTML.includes('id="'+id+'"'));
assert.equal(vm.runInContext('dataState({price:100})',ctx),'LAGRET');
assert.equal(vm.runInContext('dataState({price:null})',ctx),'UTILGJENGELIG');
assert.equal(vm.runInContext('fmtPct(null)',ctx),'—');
assert.equal(vm.runInContext('stockList([{ticker:"EQNR"}]).length',ctx),1);
""".replace('SCRIPT',json.dumps(script))
    subprocess.run(['node','-e',program],check=True,capture_output=True,text=True)


def test_morning_brief_caps_total_and_deduplicates():
    page=(ROOT/'frontend/morning.html').read_text()
    fn=page[page.index('function briefPoints'):page.index('async function load(force')]
    script="const assert=require('node:assert/strict');const pct=v=>v+'%';"+fn+";const result=briefPoints({must_know:Array.from({length:15},(_,i)=>({url:'https://example.test/'+i,title:'event'})),overnight_news:[{official:true,url:'https://example.test/0'}]});assert.equal(result.length,8);assert.equal(new Set(result.map(x=>x.url)).size,8);"
    subprocess.run(['node','-e',script],check=True,capture_output=True,text=True)


def test_worker_does_not_relay_public_writes_or_personal_reads():
    worker=(ROOT/'worker.js').as_uri()
    script="""
import assert from 'node:assert/strict';
import worker from WORKER;
let calls=0;globalThis.fetch=async()=>{calls++;return new Response('{}')};
const env={NORDICSIGNAL_WRITE_TOKEN:'test-only',ASSETS:{fetch:async()=>new Response('<html><head></head><body></body></html>',{headers:{'content-type':'text/html'}})}};
for(const [path,method] of [['/api/refresh','POST'],['/api/watchlist','GET'],['/api/holdings','GET'],['/api/dashboard-home?phase=core','GET'],['/api/push/test','POST'],['/api/opportunity/EQNR?refresh=true','GET']]){
 const response=await worker.fetch(new Request('https://example.test'+path,{method}),env);assert.equal(response.status,403,path);
}
assert.equal(calls,0);
const page=await(await worker.fetch(new Request('https://example.test/app'),env)).text();
assert.ok(page.includes('/mobile_shell.js'));assert.ok(!page.includes('/alert_nav_ui.js'));assert.ok(!page.includes('/alert_local_capture.js'));
""".replace('WORKER',json.dumps(worker))
    subprocess.run(['node','--input-type=module','-e',script],check=True,capture_output=True,text=True)


def test_market_filters_preserve_rank_and_missing_values():
    page=(ROOT/'frontend/index.html').read_text()
    script=re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>',page,re.S)[-1].replace('init();','')
    program="""
const vm=require('node:vm'),assert=require('node:assert/strict');
const ctx={URLSearchParams,location:{},search:{addEventListener(){}},document:{},console};vm.createContext(ctx);vm.runInContext(SCRIPT,ctx);
vm.runInContext('universe=[{ticker:"EQNR",name:"Equinor",score:90,market_rank:1,insider_coverage:false},{ticker:"DNB",name:"DNB",score:70,market_rank:2,insider_coverage:true}];marketFilter="owner"',ctx);
assert.equal(vm.runInContext('filteredMarket().length',ctx),1);
assert.ok(vm.runInContext('rows(filteredMarket())',ctx).includes('class="rank">2</span>'));
assert.equal(vm.runInContext('supportedStock({symbol:"EQNRX",quote_type:"MUTUALFUND"})',ctx),false);
assert.equal(vm.runInContext('supportedStock({symbol:"EQNR.OL",quote_type:"EQUITY"})',ctx),true);
assert.equal(vm.runInContext('priceText({price:null})',ctx),'—');
assert.equal(vm.runInContext('relativeText({relative_strength:null})',ctx),'—');
""".replace('SCRIPT',json.dumps(script))
    subprocess.run(['node','-e',program],check=True,capture_output=True,text=True)


def test_market_prefers_newer_dated_observation_over_old_quote(monkeypatch):
    def rows(sql):
        if 'quotes' in sql:
            return [{'ticker':'EQNR','price':200,'change_pct':2,'captured_at':'2026-09-10T10:00:00Z'}]
        return [{'ticker':'EQNR','payload':json.dumps({'reversal':{'metrics':{'close':300,'close_date':'2026-09-24'}}})}]
    monkeypatch.setattr(market,'read_rows',rows)
    row=market.snapshot([{'ticker':'EQNR','score':69}])['items'][0]
    assert row['price']==300
    assert row['change_pct'] is None
    assert row['quote_as_of']=='2026-09-24'
    assert row['data_status']=='LAGRET'
