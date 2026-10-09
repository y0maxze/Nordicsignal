const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require('jsdom');
const read=n=>fs.readFileSync('frontend/'+n,'utf8');
const settle=()=>new Promise(r=>setImmediate(r));
async function stockPage(newsItem,failOpportunity=false){
 const dom=new JSDOM(read('stock.html'),{url:'https://app.test/stock?ticker=TECH',runScripts:'outside-only'}),w=dom.window;
 w.AbortSignal.timeout=()=>undefined;
 w.AksjerCompany={mount(){}};w.AksjerIPO={mount(){}};
 let finishNews;
 w.fetch=async url=>{
  if(url==='/api/news/TECH')return new Promise(r=>finishNews=()=>r({ok:true,json:async()=>({items:[newsItem]})}));
  if(url==='/api/opportunity/TECH'&&failOpportunity)throw Error('timeout');
  const data=url==='/api/stocks/TECH'?{ticker:'TECH',name:'Techstep ASA',score:null}:url==='/api/quote/TECH'?{price:5.5,currency:'NOK',source:'Yahoo Finance'}:url==='/api/opportunity/TECH'?{opportunity:{label:'EARLY_OPPORTUNITY',components:{}},reversal:{regime:'FALLING_OR_WEAK',metrics:{}}}:{items:[]};
  return {ok:true,json:async()=>data};
 };
 const vm=require('node:vm'),context=dom.getInternalVMContext();
 vm.runInContext(read('stock_analysis.js'),context);
 for(const s of w.document.querySelectorAll('script:not([src])'))vm.runInContext(s.textContent,context);
 await settle();finishNews();await settle();return dom;
}
test('late media response keeps media provenance and never becomes an official message',async()=>{
 const dom=await stockPage({title:'2 Cash-Producing Stocks',publisher:'Editorial <img>',official:false,published_at:new Date().toISOString()});
 const d=dom.window.document,t=d.getElementById('whyFollow').textContent;
 assert.match(t,/Medieomtale · Editorial <img>:/);assert.doesNotMatch(t,/offentlig melding|Offisiell melding/);
 assert.equal(d.querySelector('#whyFollow img'),null);
 assert.match(d.getElementById('price').textContent,/5,5 NOK/);assert.equal(d.getElementById('score').textContent,'—');
 dom.window.close();
});
test('only explicitly official recent news receives an official label',async()=>{
 for(const [official,at,expected] of [[true,new Date().toISOString(),'Offisiell melding'],[undefined,new Date().toISOString(),'Medieomtale'],[true,'2020-01-01T00:00:00Z',null]]){
  const dom=await stockPage({title:'Source title',publisher:'Source',official,published_at:at});
  const t=dom.window.document.getElementById('whyFollow').textContent;
  if(expected)assert.match(t,new RegExp(expected));else assert.doesNotMatch(t,/Source title/);
  dom.window.close();
 }
});
test('technical fields use readable Norwegian labels and preserve unknown states',async()=>{
 const dom=await stockPage({}),w=dom.window,d=w.document;
 assert.match(d.getElementById('technicalSection').textContent,/Fallende eller svak/);
 assert.match(d.getElementById('technicalSection').textContent,/Mangler data/);
 assert.match(d.getElementById('technicalSection').textContent,/ikke bekreftet totalavkastning/);
 assert.match(d.getElementById('ticker').textContent,/Markedsplass ukjent/);
 assert.doesNotMatch(d.getElementById('technicalSection').textContent,/FALLING_OR_WEAK|UTILGJENGELIG/);
 w.renderTechnical({reversal:{regime:'NEW_UNKNOWN_REGIME',metrics:{}}});
 assert.match(d.getElementById('technicalSection').textContent,/Ukjent/);
 dom.window.close();
});
test('failed Opportunity load ends loading with a retry and no inferred system action',async()=>{
 const dom=await stockPage({},true),d=dom.window.document;
 assert.equal(d.getElementById('oppState').textContent,'Utilgjengelig');
 assert.match(d.getElementById('whatNow').textContent,/Ingen systemhandling bekreftet/);
 assert.ok(d.getElementById('retryOpportunity'));
 assert.doesNotMatch(d.getElementById('whatNow').textContent,/Laster/);dom.window.close();
});
async function alertPage({permission='granted',sub=true,ready=true,fail=false,supported=true,items=[]}={}){
 const dom=new JSDOM(read('alerts.html'),{url:'https://app.test/alerts',runScripts:'outside-only'}),w=dom.window,calls=[];
 w.AbortSignal.timeout=()=>undefined;
 if(supported){w.Notification={permission};w.PushManager=function(){};Object.defineProperty(w.navigator,'serviceWorker',{value:{getRegistration:async()=>({pushManager:{getSubscription:async()=>sub?{endpoint:'private-test-endpoint'}:null}})}})}
 w.fetch=async(url,opts)=>{calls.push({url,opts});if(fail&&url.includes('/push/'))throw Error();return {ok:true,json:async()=>url.includes('/push/')?{delivery_ready:ready}:{items}}};
 w.eval(read('alerts.js'));await settle();return {dom,calls};
}
test('existing push subscription is described without claiming server registration or delivery',async()=>{
 const {dom,calls}=await alertPage(),d=dom.window.document;
 assert.match(d.getElementById('pushPermission').textContent,/tillatt/);
 assert.match(d.getElementById('pushSubscription').textContent,/finnes på denne enheten · serverregistrering ikke bekreftet/);
 assert.match(d.getElementById('pushServer').textContent,/serveroppsett klart · mottak ikke bekreftet/);
 assert.doesNotMatch(d.body.textContent,/private-test-endpoint|ikke aktivert i denne versjonen/);
 d.getElementById('refreshPushStatus').click();await settle();
 assert.ok(calls.every(c=>!c.opts.method&&!c.opts.body));
 assert.equal(calls.filter(c=>c.url==='/api/push/status').length,2);dom.window.close();
});
test('trend alerts distinguish price changes from total return without rewriting stored evidence',async(t)=>{
 const {dom}=await alertPage({items:[{ticker:'DVD',event_type:'trend_activity',event:'Trend ned',detail:'5d -90.4%'},{ticker:'AAA',event_type:'score_change',event:'Scoreendring'}]});
 t.after(()=>dom.window.close());
 const cards=dom.window.document.querySelectorAll('.alertCard');
 assert.equal(cards.length,2);
 assert.match(cards[0].textContent,/5d -90.4%/);
 assert.match(cards[0].textContent,/Kursendring, ikke bekreftet totalavkastning/);
 assert.match(cards[0].textContent,/Utbytte, splitt/);
 assert.equal(cards[1].querySelector('.trendReturnNotice'),null);
});
test('push permissions, absent subscriptions, server failure and unsupported browsers stay distinct',async()=>{
 const cases=[{permission:'denied',sub:false,ready:false},{permission:'default',fail:true},{supported:false}];
 for(const opts of cases){const {dom}=await alertPage(opts),d=dom.window.document;
  if(opts.permission==='denied'){assert.match(d.getElementById('pushPermission').textContent,/blokkert/);assert.match(d.getElementById('pushSubscription').textContent,/ikke funnet/);assert.match(d.getElementById('pushServer').textContent,/ikke klart/)}
  if(opts.fail){assert.match(d.getElementById('pushPermission').textContent,/ikke gitt/);assert.match(d.getElementById('pushServer').textContent,/utilgjengelig · status ukjent/)}
  if(opts.supported===false)assert.match(d.getElementById('pushSubscription').textContent,/ikke støttet/);
  assert.equal(d.getElementById('refreshPushStatus').disabled,false);dom.window.close();
 }
});
