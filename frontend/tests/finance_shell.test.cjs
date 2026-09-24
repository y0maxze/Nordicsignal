const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {JSDOM}=require('jsdom');
const shell=fs.readFileSync('frontend/finance_shell.js','utf8');
const theme=fs.readFileSync('frontend/theme_mode.js','utf8');
function page(path='/app',density='normal'){
 const dom=new JSDOM('<!doctype html><html><head><script src="/finance_shell.js"></script></head><body><a class="nsGlobalHome">Old brand</a><main><div class="nsUtilityBar">Old bell</div><div class="top"><h1>Market</h1><button class="nsThemeToggle"></button></div><input id="search"></main></body></html>',{url:'https://example.test'+path,runScripts:'outside-only'});
 const w=dom.window;w.matchMedia=()=>({matches:false,addEventListener(){}});
 w.fetch=()=>{throw Error('Presentation must not fetch data')};
 w.localStorage.setItem('aksjer-table-density',density);
 w.eval(theme);w.eval(shell);w.eval(fs.readFileSync('frontend/ui_shell.js','utf8'));w.document.dispatchEvent(new w.Event('DOMContentLoaded'));
 return dom;
}
test('shared navigation is unique, canonical and keyboard dismissible',()=>{
 const dom=page(),w=dom.window,d=w.document;
 w.eval(shell);d.dispatchEvent(new w.Event('DOMContentLoaded'));
 assert.equal(d.querySelectorAll('#aksjerHeader').length,1);
 assert.equal(d.querySelectorAll('.nsUtilityBar,.nsGlobalHome,.top>.nsThemeToggle').length,0);
 assert.equal(d.querySelector('.aksjerPrimary [aria-current]').getAttribute('href'),'/app');
 assert.deepEqual([...d.querySelectorAll('#aksjerMenu nav a')].map(a=>a.getAttribute('href')),['/app','/morning','/alerts']);
 const menu=d.querySelector('#aksjerMenu');menu.open=true;
 d.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
 assert.equal(menu.open,false);assert.equal(d.activeElement,menu.querySelector('summary'));
 menu.open=true;d.querySelector('main').click();assert.equal(menu.open,false);
 dom.window.close();
});
test('density persists and the visible theme control changes both modes',()=>{
 const dom=page('/app','compact'),w=dom.window,d=w.document,b=d.querySelector('#aksjerDensity');
 assert.equal(b.getAttribute('aria-pressed'),'true');b.click();
 assert.equal(d.documentElement.dataset.density,'normal');
 assert.equal(w.localStorage.getItem('aksjer-table-density'),'normal');
 b.click();assert.equal(b.querySelector('span').textContent,'På');
 const toggle=d.querySelector('#aksjerHeader [data-ns-theme-toggle]');
 assert.equal(d.documentElement.dataset.theme,'dark');toggle.click();
 assert.equal(d.documentElement.dataset.theme,'light');assert.equal(toggle.getAttribute('aria-label'),'Bytt til mørkt tema');toggle.click();assert.equal(d.documentElement.dataset.theme,'dark');
 dom.window.close();
});
test('stock section links target actual rendered analysis sections without hiding content',()=>{
 const dom=page('/stock?ticker=EQNR'),d=dom.window.document;
 // Use actual static and generated section markup as the source of valid ids.
 const source=fs.readFileSync('frontend/stock.html','utf8');
 const ids=new Set([...source.matchAll(/id="([^"]+)"/g)].map(m=>m[1]));
 const links=[...d.querySelectorAll('.aksjerStockSections a')];
 assert.equal(links.length,7);
 for(const link of links)assert.ok(ids.has(link.getAttribute('href').slice(1)));
 assert.equal(d.querySelectorAll('.tabs,[role=tab]').length,0);
 dom.window.close();
});
test('primary pages and offline shell include the same presentation assets',()=>{
 for(const name of ['index.html','stock.html','morning.html','alerts.html']){
  const source=fs.readFileSync('frontend/'+name,'utf8');
  assert.equal(source.split('src="/finance_shell.js"').length-1,1);
  assert.equal(source.split('href="/finance_shell.css"').length-1,1);
 }
 const sw=fs.readFileSync('frontend/sw.js','utf8');
 assert.ok(sw.includes("'/finance_shell.js'"));assert.ok(sw.includes("'/finance_shell.css'"));
});
