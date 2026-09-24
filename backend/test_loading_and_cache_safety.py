import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_calendar_cannot_turn_failed_opportunity_into_no_action():
    page = (ROOT / 'frontend/stock.html').read_text()
    script = re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', page, re.S)[-1]
    script = script[:script.rfind('load().catch')]
    program = r'''
const vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map();let fail=true,calls=0;
const ctx={URLSearchParams,AbortSignal,location:{search:'?ticker=AKSO'},document:{getElementById(id){if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:''});return elements.get(id)}},window:{},fetch:async()=>{calls++;if(fail)throw Error('timeout');return {ok:true,json:async()=>({opportunity:{label:'NO_OPPORTUNITY',components:{}}})}},renderTechnical(){}};
vm.createContext(ctx);vm.runInContext(SCRIPT,ctx);
(async()=>{
 await vm.runInContext('loadOpportunity()',ctx);
 vm.runInContext('renderDecisionPanels(data.opportunity)',ctx);
 assert.equal(elements.get('oppState').textContent,'Utilgjengelig');
 assert.ok(elements.get('whatNow').innerHTML.includes('Ingen systemhandling bekreftet'));
 assert.ok(!elements.get('whatNow').innerHTML.includes('Ingen handling ennå'));
 assert.ok(!elements.get('whyFollow').innerHTML.includes('Ingen sterke nye signaler'));
 fail=false;await elements.get('retryOpportunity').onclick();
 assert.equal(calls,2);assert.equal(elements.get('oppState').textContent,'Ingen handling');
 assert.ok(elements.get('whatNow').innerHTML.includes('Ingen handling ennå'));
})().catch(e=>{console.error(e);process.exit(1)});
'''.replace('SCRIPT',json.dumps(script))
    subprocess.run(['node','-e',program],check=True,capture_output=True,text=True)


def test_service_worker_does_not_cache_access_redirects_or_api():
    script = (ROOT / 'frontend/sw.js').read_text()
    program = r'''
const vm=require('node:vm'),assert=require('node:assert/strict');
const handlers={},writes=[];let redirected=true;
const response=()=>({ok:true,redirected,type:'basic',clone(){return this}});
const ctx={URL,Response,self:{location:{origin:'https://example.test'},addEventListener(k,v){handlers[k]=v},skipWaiting(){},clients:{claim(){}}},caches:{open:async()=>({put:async(...x)=>writes.push(x)}),match:async()=>null},fetch:async()=>response()};
vm.createContext(ctx);vm.runInContext(SCRIPT,ctx);
(async()=>{
 let installed;handlers.install({waitUntil(p){installed=p}});await installed;assert.equal(writes.length,0);
 let loaded;const request={method:'GET',url:'https://example.test/app',mode:'navigate'};
 handlers.fetch({request,respondWith(p){loaded=p}});await loaded;assert.equal(writes.length,0);
 redirected=false;handlers.fetch({request,respondWith(p){loaded=p}});await loaded;await Promise.resolve();assert.equal(writes.length,1);
 let intercepted=false;handlers.fetch({request:{...request,url:'https://example.test/api/stocks'},respondWith(){intercepted=true}});assert.equal(intercepted,false);
})().catch(e=>{console.error(e);process.exit(1)});
'''.replace('SCRIPT',json.dumps(script))
    subprocess.run(['node','-e',program],check=True,capture_output=True,text=True)
