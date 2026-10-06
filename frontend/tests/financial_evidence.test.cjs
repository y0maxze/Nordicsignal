const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require('jsdom');
const source=fs.readFileSync('frontend/company_context.js','utf8');
const analysis=fs.readFileSync('frontend/stock_analysis.js','utf8');
const payload=()=>({score_effect:0,ticker:'TECH',identity:'techstep',yahoo_identity_verified:true,
 financials:[{label:'Omsetning',value:1000000,currency:'USD',period:'2025-12-31',period_type:'12M'},{label:'Gjeld',value:0,period:'2024-12-31'}],
 field_sources:{financials:{source:'Yahoo Finance',source_url:'https://finance.yahoo.com/quote/TECH.OL/',captured_at:'2026-10-01T12:00:00Z',attempted_at:'2026-10-05T12:00:00Z',status:'stale'}}});
function setup(fetch){
 const d=new JSDOM('<section id="company"></section><section id="financial"></section>',{url:'https://app.test',runScripts:'outside-only'});
 d.window.eval(source);d.window.AbortSignal.timeout=()=>undefined;d.window.fetch=fetch;
 return {d,c:d.window.document.getElementById('company'),f:d.window.document.getElementById('financial'),mount:d.window.AksjerCompany.mount};
}
test('both panels share one snapshot, dates, source, stale status and unknown currency',async()=>{
 const calls=[],p=payload();const {d,c,f,mount}=setup(async url=>{calls.push(url);return {ok:true,json:async()=>p};});
 await mount(c,'TECH',{financialRoot:f});
 assert.deepEqual(calls,['/api/company-context/TECH']);
 assert.equal(c.querySelector('.companyFinancials').innerHTML,f.querySelector('.companyFinancials').innerHTML);
 for(const root of [c,f]){assert.match(root.textContent,/USD/);assert.match(root.textContent,/2025-12-31/);assert.match(root.textContent,/2024-12-31/);assert.match(root.textContent,/valuta ukjent/);assert.match(root.textContent,/Eldre opplysning/);assert.match(root.textContent,/Gjeld0/);assert.ok(root.querySelector('a[href="https://finance.yahoo.com/quote/TECH.OL/"]'));}
 assert.match(f.textContent,/P\/E, P\/B og EV\/EBITDA: Ukjent/);d.window.close();
});
test('unverified financials are withheld in both panels even when amounts exist',async()=>{
 const p={...payload(),yahoo_identity_verified:false};const {d,c,f,mount}=setup(async()=>({ok:true,json:async()=>p}));
 await mount(c,'TECH',{financialRoot:f});
 for(const root of [c,f]){assert.equal(root.querySelector('.companyFinancials'),null);assert.match(root.textContent,/Identitetskontrollerte regnskapstall/);assert.doesNotMatch(root.textContent,/Omsetning|2025-12-31/);}d.window.close();
});
test('failure, redirect and wrong issuer end loading consistently without research fallback',async()=>{
 for(const response of [{ok:false},{ok:true,redirected:true},{ok:true,json:async()=>({...payload(),ticker:'OTHER'})}]){
  const {d,c,f,mount}=setup(async()=>response);await mount(c,'TECH',{financialRoot:f});
  for(const root of [c,f]){assert.match(root.textContent,/UTILGJENGELIG/);assert.doesNotMatch(root.textContent,/Laster|Omsetning/);}d.window.close();
 }
});
test('a late snapshot cannot replace either panel after changing issuer',async()=>{
 const resolve=[];const {d,c,f,mount}=setup(()=>new Promise(r=>resolve.push(r)));
 const first=mount(c,'TECH',{financialRoot:f}),second=mount(c,'OTHER',{financialRoot:f});
 resolve[1]({ok:true,json:async()=>({...payload(),ticker:'OTHER',identity:'other',financials:[{label:'Other fact',value:7,currency:'NOK',period:'2025-12-31'}]})});await second;
 resolve[0]({ok:true,json:async()=>payload()});await first;
 for(const root of [c,f]){assert.match(root.textContent,/Other fact/);assert.doesNotMatch(root.textContent,/Omsetning/);}d.window.close();
});
test('stock analysis passes the financial target to the shared collector and never requests raw research',async()=>{
 const {d,c,f}=setup();const w=d.window,calls=[];let target;
 w.$=id=>id==='companyContextSection'?c:id==='fundamentalSection'?f:w.document.createElement('section');
 w.ticker='TECH';w.data={};w.esc=String;w.news=()=>'';w.renderDecisionPanels=()=>{};
 w.get=async url=>{calls.push(url);return {items:[]};};
 w.AksjerCompany.mount=(root,ticker,options)=>{target=options.financialRoot;};w.AksjerIPO={mount(){}};
 w.eval(analysis);await w.loadAnalysis();await new Promise(r=>setImmediate(r));
 assert.equal(target,f);assert.ok(calls.every(url=>!url.includes('/research/')));d.window.close();
});
test('financial source text is escaped and malformed numeric values never appear as facts',()=>{
 const {d,f}=setup();const p=payload();p.financials=[{label:'<img src=x>',value:-3,currency:'<script>',period:'unknown'},{label:'Infinity',value:Infinity},{label:'Bool',value:true}];
 f.innerHTML=d.window.AksjerCompany.financialPanel(p);assert.equal(f.querySelector('img,script'),null);assert.doesNotMatch(f.textContent,/Infinity|Bool/);assert.match(f.textContent,/<img src=x>/);d.window.close();
});
