const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require('jsdom');
const script=fs.readFileSync('frontend/company_context.js','utf8');
const profiles=JSON.parse(fs.readFileSync('backend/data/company_reviewed_research.json','utf8')).profiles;
function payload(ticker){const r=structuredClone(profiles.find(p=>p.ticker===ticker));return {score_effect:0,ticker,identity:r.identity,reviewed_research:{...r,status:'reviewed_snapshot'},financials:[],yahoo_identity_verified:false};}
function setup(){const d=new JSDOM('<section id="summary"></section><section id="company"></section><section id="financial"></section>',{url:'https://app.test',runScripts:'outside-only'});d.window.eval(script);d.window.AbortSignal.timeout=()=>undefined;return d;}
test('one request supplies pilot summary, sourced financials and separate transaction histories',async()=>{
 const d=setup(),w=d.window,doc=w.document;let calls=0;
 w.fetch=async()=>{calls++;return {ok:true,json:async()=>payload('HDLY')};};
 await w.AksjerCompany.mount(doc.querySelector('#company'),'HDLY',{financialRoot:doc.querySelector('#financial'),summaryRoot:doc.querySelector('#summary')});
 assert.equal(calls,1);assert.equal(doc.querySelector('#summary').hidden,false);
 assert.match(doc.querySelector('#summary').textContent,/Risiko å følge/);
 assert.equal(doc.querySelectorAll('.reviewedFinancialGroup').length,4);
 assert.equal(doc.querySelectorAll('.reviewedFinancialGroup[open]').length,1);
 const transactions=doc.querySelectorAll('.researchTransactions article');assert.equal(transactions.length,2);
 assert.match(transactions[0].textContent,/Kapitalforhøyelsen registrert/);assert.doesNotMatch(transactions[0].textContent,/kansellert/);
 assert.match(transactions[1].textContent,/kansellert/);
 assert.match(doc.querySelector('#financial').textContent,/50,373/);
 assert.match(doc.querySelector('#financial').textContent,/dette er ikke dagens saldo/);
 assert.equal(doc.querySelector('#company .companyFinancials'),null);
 assert.ok(doc.querySelector('.researchArchive'));d.window.close();
});
test('Inify retains SEK, comparable dates and absolute loss differences without percent growth',()=>{
 const d=setup();d.window.document.body.innerHTML=d.window.AksjerCompany.financialPanel(payload('INIFY'));
 const q=d.window.document.querySelector('.reviewedFinancialGroup');
 assert.match(q.textContent,/mill. SEK/);assert.match(q.textContent,/01.04.2026–30.06.2026 mot 01.04.2025–30.06.2025/);
 const row=q.querySelector('tbody tr:last-child');assert.match(row.textContent,/[−-]21,821/);assert.match(row.textContent,/[−-]4,644/);assert.doesNotMatch(row.textContent,/%/);
 assert.ok(q.querySelector('a[href="https://mb.cision.com/Main/21520/4387640/4232762.pdf"]'));d.window.close();
});
test('review freshness and expired calendar are explicit, and content is escaped',()=>{
 const d=setup(),p=payload('HYPRO'),r=p.reviewed_research;
 r.needs_review=true;r.newer_financing_count=2;r.source_correction_observed=true;r.next_event.passed=true;r.business.text='<img src=x onerror=alert(1)>';r.sources.q2.url='javascript:alert(1)';
 d.window.document.body.innerHTML=d.window.AksjerCompany.summaryPanel(p);
 const text=d.window.document.body.textContent;
 assert.match(text,/2 nyere finansieringsmeldinger/);assert.match(text,/markert som korrigert/);assert.match(text,/er passert/);
 assert.equal(d.window.document.querySelector('img,script,a[href^="javascript:"]'),null);d.window.close();
});
test('wrong issuer, missing review, fetch failure and late responses cannot leave a stale summary',async()=>{
 const d=setup(),w=d.window,doc=w.document,root=doc.querySelector('#company'),summary=doc.querySelector('#summary'),financial=doc.querySelector('#financial');
 const p=payload('HDLY');p.reviewed_research.ticker='OTHER';assert.equal(w.AksjerCompany.summaryPanel(p),'');
 const resolves=[];w.fetch=()=>new Promise(resolve=>resolves.push(resolve));
 const first=w.AksjerCompany.mount(root,'HDLY',{financialRoot:financial,summaryRoot:summary});
 const second=w.AksjerCompany.mount(root,'OTHER',{financialRoot:financial,summaryRoot:summary});
 resolves[1]({ok:false});await second;resolves[0]({ok:true,json:async()=>payload('HDLY')});await first;
 assert.equal(summary.hidden,true);assert.equal(summary.textContent,'');assert.match(financial.textContent,/UTILGJENGELIG/);d.window.close();
});
