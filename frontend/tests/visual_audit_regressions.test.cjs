const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),{JSDOM}=require('jsdom');
const read=n=>fs.readFileSync('frontend/'+n,'utf8'),settle=()=>new Promise(r=>setImmediate(r));
function page(t,name,path){const dom=new JSDOM(read(name),{url:'https://app.test'+path,runScripts:'outside-only'});t.after(()=>dom.window.close());dom.window.AbortSignal.timeout=()=>undefined;return dom;}
function inline(dom){for(const script of dom.window.document.querySelectorAll('script:not([src])'))vm.runInContext(script.textContent,dom.getInternalVMContext());}
test('calendar loads public events immediately and rejects broken responses and unsafe source links',async t=>{
 const dom=page(t,'calendar.html','/calendar'),w=dom.window,calls=[];let payload={items:[{date:'2026-10-13',company:'Example',url:'javascript:alert(1)',days_until:3}],generated_at:'2026-10-10T05:00:00Z'};
 w.fetch=async u=>{calls.push(u);return {ok:true,json:async()=>payload}};inline(dom);await settle();
 assert.equal(calls[0],'/api/calendar?days=90&limit=180');assert.doesNotMatch(w.document.body.textContent,/Min beholdning/);
 assert.match(w.document.getElementById('calendar').textContent,/Example/);assert.equal(w.document.querySelector('a[href^="javascript:"]'),null);
 payload={};w.document.getElementById('refresh').click();await settle();assert.match(w.document.getElementById('statusText').textContent,/utilgjengelig/);assert.equal(w.document.getElementById('sourceText').textContent,'');
});
test('rule-based news overview does not turn a trading update into an asserted full report',async t=>{
 const dom=page(t,'news.html','/news'),w=dom.window;
 w.fetch=async()=>({ok:true,json:async()=>({items:[{title:'Q3 trading update',category:'Rapport',url:'javascript:alert(1)'}]})});inline(dom);await settle();
 assert.match(w.document.getElementById('aiText').textContent,/Tittelen alene bekrefter ikke/);assert.match(w.document.querySelector('.aiBadge').textContent,/REGELBASERT/);
 assert.equal(w.document.querySelector('a[href^="javascript:"]'),null);
});
test('empty instrument state ends loading, offers search and does not request data',async t=>{
 const dom=page(t,'instrument.html','/instrument'),w=dom.window;w.fetch=()=>{throw Error('No symbol must not fetch')};inline(dom);
 assert.equal(w.document.getElementById('name').textContent,'Velg instrument');assert.equal(w.document.querySelector('.tabs').hidden,true);
 assert.equal(w.document.querySelector('#status a').getAttribute('href'),'/intelligence');
});
test('history analysis link follows selected ticker and null prices are excluded',async t=>{
 const dom=page(t,'history.html','/history?ticker=DVD'),w=dom.window;
 w.fetch=async()=>({ok:true,json:async()=>({items:[{date:'2026-10-07',close:null},{date:'2026-10-08',close:2},{date:'2026-10-09',close:3}]})});inline(dom);await settle();
 assert.equal(w.document.getElementById('historyAnalysis').getAttribute('href'),'/stock?ticker=DVD');assert.match(w.document.getElementById('historyStatus').textContent,/2 observasjoner/);assert.equal(w.document.getElementById('historyLow').textContent,'2');
 w.document.getElementById('historyTicker').value='AKSO';w.document.getElementById('historyLoad').click();await settle();assert.equal(w.document.getElementById('historyAnalysis').getAttribute('href'),'/stock?ticker=AKSO');
});
test('blocked push cannot prompt or subscribe and becomes actionable after permission changes',async t=>{
 const dom=page(t,'alerts.html','/alerts'),w=dom.window,calls=[];w.matchMedia=()=>({matches:false});w.Notification={permission:'denied',requestPermission(){throw Error('must not prompt denied permission')}};w.PushManager=function(){};w.navigator.serviceWorker={register:async()=>({})};
 w.fetch=async(url,opts)=>{calls.push({url,opts});return {ok:true,json:async()=>({push_write_allowed:true})}};w.eval(read('mobile_shell.js'));await settle();
 const b=w.document.getElementById('nsEnableAlerts');assert.equal(b.disabled,true);assert.match(w.document.getElementById('alertStatus').textContent,/innstillinger/);await w.NordicSignalMobile.enableAlerts();assert.ok(calls.every(c=>c.url==='/api/push/access'));
 w.Notification.permission='default';await w.NordicSignalMobile.refreshAlertPermission();assert.equal(b.disabled,false);assert.equal(b.textContent,'Aktiver');
});
test('historical signal changes show the observation date and do not synthesize a score from null',async t=>{
 const dom=page(t,'stock.html','/stock?ticker=DVD'),w=dom.window;w.AksjerCompany={mount(){}};w.AksjerIPO={mount(){}};
 w.fetch=async u=>({ok:true,json:async()=>u.includes('/opportunity/')?{opportunity:{label:'NO_OPPORTUNITY'}}:{items:[]}});
 vm.runInContext(read('stock_analysis.js'),dom.getInternalVMContext());inline(dom);await settle();
 w.renderChangedSince({items:[{label:'WATCH',research_score:10},{label:'WATCH',research_score:null}]},{items:[{previous_label:'REVERSAL_CANDIDATE',label:'WATCH_CONFLUENCE',observed_at:'2026-09-11T10:00:00Z'}]});
 const text=w.document.getElementById('changedSince').textContent;assert.match(text,/11\.09\.2026/);assert.match(text,/Historiske observasjoner/);assert.doesNotMatch(text,/Endret siden sist|Early score/);
});
test('stock capital flow retains source URL and event timestamp without adding model effects',async t=>{
 const dom=page(t,'stock.html','/stock?ticker=DVD'),w=dom.window;w.AksjerCompany={mount(){}};w.AksjerIPO={mount(){}};
 w.fetch=async u=>({ok:true,json:async()=>u.startsWith('/api/capital-flow')?{items:[{ticker:'DVD',title:'Mandatory trade',source:'Euronext',event_at:'2026-09-10T10:00:00Z',source_url:'https://example.test/source'}]}:{items:[]}});
 vm.runInContext(read('stock_analysis.js'),dom.getInternalVMContext());inline(dom);await settle();
 const root=w.document.getElementById('capitalSection');assert.equal(root.querySelector('a').href,'https://example.test/source');assert.match(root.textContent,/10\.09\.2026/);assert.match(root.textContent,/Ingen score-effekt/);
});
test('corporate action context escapes evidence and preserves retrospective limitations',t=>{
 const dom=page(t,'results.html','/results'),w=dom.window;w.eval(read('corporate_action_context.js'));
 const x={type:'cash_dividend',amount:20.6,ticker:'DVD',currency:'NOK',isin:'NO0010955917',issuer:'<img src=x>',source_url:'https://example.test/proof',reviewed_at:'2026-10-10T05:00:00Z',ex_date:'2026-10-08',revision:1};
 w.document.getElementById('resultsContent').innerHTML=w.AksjerActions.render([x],{windowContext:true});
 assert.equal(w.document.querySelector('#resultsContent img'),null);assert.match(w.document.body.textContent,/20,60 NOK/);assert.match(w.document.body.textContent,/lagt til i ettertid/);assert.match(w.document.body.textContent,/identiteten i den gamle måleposten er ikke verifisert/);
 assert.equal(w.AksjerActions.render([{...x,source_url:'javascript:alert(1)'}]),'');
});
