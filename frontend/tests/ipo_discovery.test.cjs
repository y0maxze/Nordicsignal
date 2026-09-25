const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {JSDOM}=require('jsdom');
const script=fs.readFileSync('frontend/ipo_discovery.js','utf8');
function setup(fetch){const dom=new JSDOM('<main id="root"></main>',{url:'https://example.test/app',runScripts:'outside-only'});dom.window.fetch=fetch;dom.window.AbortSignal=AbortSignal;dom.window.eval(script);return dom;}
const item={company:'New <img src=x onerror=alert(1)>',ticker:'NEW',market:'Euronext Growth Oslo',groups:['upcoming'],display_status:'PRE-IPO',confirmation:'Plan',why_follow:['Documented plan'],risks:['Not confirmed'],unknowns:['Valuation'],source_url:'javascript:alert(1)',analysis_available:false};
const payload={items:[item,{...item,company:'Listed',ticker:'LST',groups:['recent','year'],display_status:'NEW',analysis_available:true,source_url:'https://live.euronext.com/en/node/1'}],year:2026,counts:{upcoming:1,recent:1,year:1},score_effect:0,status:'ok'};
test('periods include untracked IPOs, search works and sources cannot inject script',async()=>{
 let calls=0;const dom=setup(async()=>{calls++;return {ok:true,json:async()=>payload}});const {document,AksjerIPO}=dom.window;const root=document.getElementById('root');
 await AksjerIPO.mount(root);assert.match(root.textContent,/New <img/);assert.equal(root.querySelectorAll('img').length,0);assert.equal(root.querySelectorAll('a').length,0);
 root.querySelector('[data-ipo-group="recent"]').click();assert.match(root.textContent,/Listed/);assert.equal(root.querySelector('a[href^="/stock"]').getAttribute('href'),'/stock?ticker=LST');
 const input=root.querySelector('input');input.value='no-match';input.dispatchEvent(new dom.window.Event('input'));assert.match(root.querySelector('.ipoResults').textContent,/Ingen verifiserte treff/);
 await AksjerIPO.mount(root,'LST');assert.match(root.textContent,/Ny på børs/);assert.equal(calls,1);dom.window.close();
});
test('failed or redirected sources show unavailable and retry, never a confirmed empty universe',async()=>{
 let fail=true;const dom=setup(async()=>fail?{ok:true,redirected:true}:{ok:true,json:async()=>payload});const root=dom.window.document.getElementById('root');
 await dom.window.AksjerIPO.mount(root);assert.match(root.textContent,/UTILGJENGELIG/);fail=false;root.querySelector('button').click();await new Promise(r=>setImmediate(r));assert.match(root.textContent,/Nye på børs/);assert.doesNotMatch(root.textContent,/UTILGJENGELIG/);dom.window.close();
});
test('a late request does not overwrite a detached view',async()=>{
 let release;const dom=setup(()=>new Promise(r=>{release=r}));const root=dom.window.document.getElementById('root');const loading=dom.window.AksjerIPO.mount(root);root.remove();release({ok:true,json:async()=>payload});await loading;assert.match(root.textContent,/Laster/);dom.window.close();
});
test('actual Market filter renders IPOs outside the ranked universe with one discovery request',async()=>{
 const html=fs.readFileSync('frontend/index.html','utf8');
 const dom=new JSDOM(html,{url:'https://example.test/app',runScripts:'outside-only'}),w=dom.window;
 const calls=[];w.AbortSignal=AbortSignal;
 w.fetch=async url=>{calls.push(url);const data=url==='/api/market-snapshot'?{items:[{ticker:'EQNR',name:'Equinor',score:69}]}:url.startsWith('/api/early-discovery')?{items:[]}:payload;return {ok:true,json:async()=>data};};
 w.eval(script);const inline=[...w.document.querySelectorAll('script')].find(s=>!s.src&&s.textContent.includes('function renderDashboard'));w.eval(inline.textContent);
 await new Promise(r=>setImmediate(r));await new Promise(r=>setImmediate(r));
 assert.match(w.document.querySelector('.marketTable').textContent,/Equinor/);
 w.setMarketFilter('ipo');await new Promise(r=>setImmediate(r));
 assert.match(w.document.querySelector('.marketTable').textContent,/Nye på børs/);
 assert.match(w.document.querySelector('.ipoResults').textContent,/New/);
 assert.equal(calls.filter(x=>x==='/api/ipo-radar/discovery').length,1);
 assert.equal(calls.length,3);dom.window.close();
});
