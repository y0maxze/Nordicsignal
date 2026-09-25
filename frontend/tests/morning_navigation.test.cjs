const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),vm=require('node:vm');
const {JSDOM}=require('jsdom');
const html=fs.readFileSync('frontend/morning.html','utf8'),script=fs.readFileSync('frontend/morning_navigation.js','utf8');
const tick=()=>new Promise(r=>setImmediate(r));
async function setup(search){
 const dom=new JSDOM(html,{url:'https://example.test/morning',runScripts:'outside-only'}),w=dom.window,calls=[],location={href:''};
 w.fetch=async()=>({ok:true,json:async()=>({must_know:[{company:'Techstep ASA',title:'Award of contract',source_context:'radar',url:'https://example.test/release'},{company:'Equinor',ticker:'EQNR',source_context:'calendar'},{company:'Brent',source_context:'market'}]})});
 w.AbortSignal=AbortSignal;
 for(const el of w.document.querySelectorAll('script:not([src])'))w.eval(el.textContent);
 await tick();
 vm.runInNewContext(script,{document:w.document,location,AbortSignal,fetch:async url=>{calls.push(url);return search(url)}});
 return {dom,d:w.document,w,calls,location};
}
test('morning company without ticker resolves on click only to unique exact Oslo equity',async()=>{
 const p=await setup(()=>({ok:true,json:async()=>({items:[{name:'Techstep ASA',symbol:'TECH.OL',ticker:'TECH.OL',quote_type:'EQUITY'}]})}));
 assert.equal(p.calls.length,0);assert.equal(p.d.querySelector('a.morningCompany').getAttribute('href'),'/stock?ticker=EQNR');
 assert.equal(p.d.querySelectorAll('[data-company-query]').length,1);
 p.d.querySelector('[data-company-query]').click();await tick();
 assert.equal(p.calls.length,1);assert.equal(p.location.href,'/stock?ticker=TECH');p.dom.window.close();
});
test('ambiguous or fuzzy results require choosing; foreign shares and funds are excluded',async()=>{
 const p=await setup(()=>({ok:true,json:async()=>({items:[{name:'Techstep Group',symbol:'TECH.OL',quote_type:'EQUITY'},{name:'Techstep Other',symbol:'OTHER.OL',quote_type:'EQUITY'},{name:'Techstep ASA',symbol:'TECH.ST',quote_type:'EQUITY'},{name:'Techstep ASA',symbol:'FUND.OL',quote_type:'ETF'}]})}));
 p.d.querySelector('[data-company-query]').click();await tick();
 assert.equal(p.location.href,'');assert.deepEqual([...p.d.querySelectorAll('.morningStockChoice')].map(x=>x.getAttribute('href')),['/stock?ticker=TECH','/stock?ticker=OTHER']);p.dom.window.close();
});
test('failed lookup can retry and source links never initiate stock lookup',async()=>{
 let fail=true;const p=await setup(()=>{if(fail)throw Error('offline');return {ok:true,json:async()=>({items:[]})}});
 const source=p.d.querySelector('[data-source-link]');source.addEventListener('click',e=>e.preventDefault());source.click();assert.equal(p.calls.length,0);assert.equal(p.location.href,'');
 const button=p.d.querySelector('[data-company-query]');button.click();await tick();assert.match(p.d.querySelector('.morningStockChoices').textContent,/utilgjengelig/);assert.equal(button.disabled,false);
 fail=false;button.click();await tick();assert.match(p.d.querySelector('.morningStockChoices').textContent,/Ingen Oslo-aksje/);assert.equal(p.location.href,'');p.dom.window.close();
});
