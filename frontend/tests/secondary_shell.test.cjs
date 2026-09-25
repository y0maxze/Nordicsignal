const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('fs');
const {JSDOM}=require('jsdom');
const read=n=>fs.readFileSync('frontend/'+n,'utf8');
function page(){const dom=new JSDOM(read('capital-flow.html'),{url:'https://example.test/capital-flow?ticker=NCOD',runScripts:'outside-only'});dom.window.matchMedia=()=>({matches:false,addEventListener(){}});return dom;}
test('navigation occupies a separate viewport row, outside content, in either script order',()=>{
 for(const order of [['finance_shell.js','mobile_nav.js'],['mobile_nav.js','finance_shell.js']]){
  const dom=page(),w=dom.window,d=w.document;w.eval(read('theme_mode.js'));
  for(const name of order)w.eval(read(name));d.dispatchEvent(new w.Event('DOMContentLoaded'));
  w.eval(read('mobile_learning_nav.js'));w.eval(read('alert_nav_ui.js'));w.eval(read('mobile_nav.js'));d.dispatchEvent(new w.Event('DOMContentLoaded'));
  const nav=d.getElementById('nsMobileNav'),area=d.getElementById('aksjerScrollArea');
  assert.equal(nav.parentElement,d.body);assert.equal(area.parentElement,d.body);assert.ok(area.contains(d.querySelector('main')));assert.ok(!area.contains(nav));assert.ok(!area.contains(d.getElementById('aksjerHeader')));
  assert.equal(d.querySelectorAll('#nsMobileNav').length,1);assert.equal(nav.children.length,2);assert.equal(d.querySelectorAll('#nsAlertShortcut').length,0);
  const css=d.getElementById('aksjerMobileNavStyle').textContent;assert.match(css,/minmax\(0,1fr\) auto/);assert.match(css,/height:100dvh/);assert.match(css,/position:relative!important/);assert.doesNotMatch(css,/position:fixed/);
  dom.window.close();
 }
});
test('capital-flow refresh stays read-only and missing values remain missing',async()=>{
 const dom=page(),w=dom.window,d=w.document,calls=[];
 w.fetch=async url=>{calls.push(url);return {ok:true,json:async()=>url.includes('/ownership/status')?{snapshots:0,tickers:0}:url.includes('/ownership/')?{status:'no_snapshot',changes:[]}:{items:[{ticker:'NCOD',title:'Test',state:'NEW',shares:null,price:null,value_nok:null,event_at:'2026-09-25T10:00:00Z',source_url:'javascript:alert(1)'}],counts:{NEW:1},generated_at:'2026-09-25T10:00:00Z'}}};
 w.eval(read('capital-flow.js'));await new Promise(r=>setImmediate(r));d.getElementById('cfRefresh').click();await new Promise(r=>setImmediate(r));
 assert.ok(calls.every(url=>!url.includes('refresh=true')));assert.doesNotMatch(d.getElementById('cfList').textContent,/0 kr/);assert.equal(d.querySelector('a[href^="javascript:"]'),null);assert.match(d.getElementById('ownershipState').textContent,/UTILGJENGELIG/);assert.match(d.getElementById('cfList').textContent,/12:00/);dom.window.close();
});
test('late Capital Flow responses cannot replace the selected state',async()=>{
 const dom=page(),w=dom.window,d=w.document;let initial;
 w.fetch=url=>url.includes('/ownership')?Promise.resolve({ok:true,json:async()=>({status:'no_snapshot',snapshots:0})}):url.includes('state=NEW')?new Promise(r=>{initial=r}):Promise.resolve({ok:true,json:async()=>({items:[{ticker:'NCOD',title:'Historical result',state:'HISTORICAL'}]})});
 w.eval(read('capital-flow.js'));d.querySelector('[data-state="HISTORICAL"]').click();await new Promise(r=>setImmediate(r));initial({ok:true,json:async()=>({items:[{ticker:'NCOD',title:'Late new result',state:'NEW'}]})});await new Promise(r=>setImmediate(r));assert.match(d.getElementById('cfList').textContent,/Historical result/);assert.doesNotMatch(d.getElementById('cfList').textContent,/Late new result/);dom.window.close();
});
test('Worker injects one shared shell and no retired navigation or local polling',async()=>{
 const worker=(await import('../../worker.js')).default;
 for(const path of ['/capital-flow','/history','/stock']){
  const env={ASSETS:{fetch:async()=>new Response(read('capital-flow.html'),{headers:{'content-type':'text/html'}})}};
  const html=await(await worker.fetch(new Request('https://example.test'+path),env)).text();
  assert.equal(html.split('src="/finance_shell.js"').length-1,1);
  for(const name of ['mobile_learning_nav.js','alert_nav_ui.js','alert_local_capture.js'])assert.ok(!html.includes('src="/'+name+'"'));
 }
});
