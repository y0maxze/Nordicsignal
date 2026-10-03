const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {JSDOM}=require('jsdom');
const read=n=>fs.readFileSync('frontend/'+n,'utf8');
test('both search controls expose partial provider coverage while keeping verified results',async()=>{
 for(const stock of [false,true]){
  const dom=new JSDOM(stock?'<main class="wrap"><div class="top"></div></main>':read('index.html'),{url:'https://example.test/'+(stock?'stock?ticker=TECH':'app'),runScripts:'outside-only'});
  const w=dom.window;let runSearch;
  w.setTimeout=fn=>{runSearch=fn;return 1};w.clearTimeout=()=>{};
  w.AksjerIPO={load:async()=>({items:[]})};
  w.fetch=async url=>({ok:true,json:async()=>url.includes('/api/search')?{items:[{ticker:'TECH',symbol:'TECH.OL',name:'Techstep ASA',tracked:false}],warning:'provider unavailable'}:{items:[]}});
  if(stock)w.eval(read('stock_selector.js'));
  else for(const s of w.document.querySelectorAll('script:not([src])'))w.eval(s.textContent);
  const input=w.document.getElementById(stock?'nsIntelInput':'search');
  input.value='TECH';input.dispatchEvent(new w.Event('input'));await runSearch();
  const box=w.document.getElementById(stock?'nsIntelResults':'searchResultsList');
  assert.match(box.textContent,/Techstep ASA/);assert.match(box.textContent,/Delvis søkedekning/);
  await new Promise(resolve=>setImmediate(resolve));
  dom.window.close();
 }
});
test('market renders readable trends without altering scores, ranking or unknown values',async()=>{
 const dom=new JSDOM(read('index.html'),{url:'https://example.test/app',runScripts:'outside-only'});
 const w=dom.window;
 w.AksjerIPO={load:async()=>({items:[]})};
 w.fetch=async url=>({ok:true,json:async()=>({items:url==='/api/market-snapshot'?[
  {ticker:'AAA',name:'Alpha',score:73,trend:'BOTTOMING'},
  {ticker:'BBB',name:'Beta',score:71,trend:'FALLING_OR_WEAK'},
  {ticker:'CCC',name:'Gamma',score:null,trend:'UNRECOGNIZED'},
  {ticker:'DDD',name:'Delta',score:null,trend:null},
 ]:[]})});
 for(const script of w.document.querySelectorAll('script:not([src])'))w.eval(script.textContent);
 await new Promise(resolve=>setImmediate(resolve));
 const rows=[...w.document.querySelectorAll('a.row')];
 assert.equal(rows.length,4);
 assert.match(rows[0].textContent,/Alpha.*73.*Mulig bunndannelse/);
 assert.match(rows[1].textContent,/Beta.*71.*Fallende eller svak/);
 assert.equal(rows[2].children[4].textContent,'—');
 assert.equal(rows[2].children[5].textContent,'Ukjent');
 assert.equal(rows[3].children[5].textContent,'—');
 assert.ok(rows.every(row=>row.textContent.includes('Ingen handling')));
 dom.window.close();
});
test('finance buttons change theme colours together instead of animating only the background',()=>{
 const dom=new JSDOM('<style>'+read('finance_shell.css')+'</style>');
 const rules=[...dom.window.document.styleSheets[0].cssRules];
 const rule=rules.find(r=>r.selectorText==='html.aksjerFinance:root .btn,html.aksjerFinance:root .tab'&&r.style.getPropertyValue('transition'));
 assert.equal(rule.style.getPropertyValue('transition'),'none');
 assert.equal(rule.style.getPropertyPriority('transition'),'important');
 dom.window.close();
});
