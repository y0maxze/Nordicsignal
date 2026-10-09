const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const origin='https://example.test';
const shell=()=>new Response('<html>Aksjer</html>',{headers:{'content-type':'text/html','x-aksjer-static-shell':'1'}});
test('deployed Worker marks static HTML but not errors or API responses',async()=>{
 const {default:worker}=await import('../../worker.js');
 const env={ASSETS:{fetch:async()=>new Response('<html><head></head><body></body></html>',{headers:{'content-type':'text/html'}})}};
 const page=await worker.fetch(new Request(origin+'/app'),env);
 assert.equal(page.headers.get('x-aksjer-static-shell'),'1');
 assert.equal((await worker.fetch(new Request(origin+'/api/holdings'),env)).headers.get('x-aksjer-static-shell'),null);
 env.ASSETS.fetch=async()=>new Response('missing',{status:404});
 assert.equal((await worker.fetch(new Request(origin+'/app'),env)).headers.get('x-aksjer-static-shell'),null);
});
function setup(){
 const handlers={},stores=new Map(),opened=[],deleted=[],navigated=[];let claimed=false,fetcher=async()=>shell();
 const key=r=>new URL(typeof r==='string'?r:r.url,origin).href;
 const cache=name=>{if(!stores.has(name))stores.set(name,new Map());return {put:async(r,s)=>stores.get(name).set(key(r),s.clone()),match:async r=>stores.get(name).get(key(r))?.clone()};};
 const clients={claim:async()=>{claimed=true},matchAll:async()=>[],openWindow:async url=>navigated.push(url)};
 const context={URL,Response,Headers,self:{location:{origin},addEventListener:(n,fn)=>handlers[n]=fn,skipWaiting(){},clients},clients,
  caches:{open:async n=>{opened.push(n);return cache(n)},keys:async()=>[...stores.keys()],delete:async n=>{deleted.push(n);return stores.delete(n)}},fetch:r=>fetcher(r)};
 vm.createContext(context);vm.runInContext(fs.readFileSync('frontend/sw.js','utf8'),context);
 const current=vm.runInContext('CACHE_NAME',context);
 return {handlers,stores,cache,current,opened,deleted,navigated,setFetch(fn){fetcher=fn},get claimed(){return claimed},
  async lifecycle(name){let promise;handlers[name]({waitUntil:p=>promise=p});await promise},
  async request(path,{method='GET',mode='navigate'}={}){let promise;handlers.fetch({request:{url:new URL(path,origin).href,method,mode},respondWith:p=>promise=p});return promise?await promise:null}};
}
test('offline cache never intercepts identity, Access, API, unknown routes or token queries',async()=>{
 const h=setup();let calls=0;h.setFetch(async()=>{calls++;return shell()});
 for(const path of ['/api/stocks','/api/push/status','/cdn-cgi/access/get-identity','/cdn-cgi/access/logout','/unknown','/app?token=private','/stock?ticker=EQNR&code=private','/theme.css?token=private','https://other.test/app'])assert.equal(await h.request(path),null,path);
 assert.equal(await h.request('/app',{method:'POST'}),null);assert.equal(calls,0);assert.equal(h.stores.size,0);
});
test('only genuine static shell HTML and correctly typed assets are cached',async()=>{
 const h=setup();
 for(const response of [new Response('Access login',{headers:{'content-type':'text/html'}}),new Response('denied',{status:401}),new Response('failure',{status:503})]){
  h.setFetch(async()=>response);await h.request('/app');assert.equal(h.stores.size,0);
 }
 h.setFetch(async()=>new Response('login',{headers:{'content-type':'text/html'}}));await h.request('/theme_mode.js');assert.equal(h.stores.size,0);
 h.setFetch(async()=>shell());await h.request('/app');assert.ok(h.stores.get(h.current).has(origin+'/app'));
 h.setFetch(async()=>new Response('body{}',{headers:{'content-type':'text/css'}}));await h.request('/theme.css');assert.ok(h.stores.get(h.current).has(origin+'/theme.css'));
});
test('offline fallback uses only this version and preserves explicit missing-data warning',async()=>{
 const h=setup();await h.cache('aksjer-shell-v1').put('/app',shell());h.setFetch(async()=>{throw Error('offline')});
 const first=await h.request('/app');assert.match(await first.text(),/Ingen markedsdata er bekreftet oppdatert/);
 await h.cache(h.current).put('/app',shell());const cached=await h.request('/app');assert.match(await cached.text(),/Aksjer/);
 const stock=await h.request('/stock?ticker=EQNR');assert.match(await stock.text(),/Du er frakoblet/);
});
test('online authentication failure never falls back to cached authenticated shell',async()=>{
 const h=setup();await h.cache(h.current).put('/app',shell());h.setFetch(async()=>new Response('sign in',{status:401}));
 assert.equal((await h.request('/app')).status,401);
});
test('installation completes other assets when one fails, and activation removes only old app caches',async()=>{
 const h=setup();h.setFetch(async path=>{if(path==='/stock')throw Error('offline');return path.endsWith('.css')?new Response('body{}',{headers:{'content-type':'text/css'}}):shell()});
 await h.lifecycle('install');assert.ok(h.stores.get(h.current).has(origin+'/app'));assert.ok(h.stores.get(h.current).has(origin+'/theme.css'));
 h.cache('aksjer-shell-v1');h.cache('unrelated-cache');await h.lifecycle('activate');
 assert.deepEqual(h.deleted,['aksjer-shell-v1']);assert.ok(h.stores.has('unrelated-cache'));assert.equal(h.claimed,true);
});
test('malformed, external and authentication notification destinations fall back safely',async()=>{
 for(const url of ['http://[','https://other.test/app','/cdn-cgi/access/logout','/api/refresh','javascript:alert(1)','/stock?ticker=EQNR']){
  const h=setup();let promise,closed=false;
  h.handlers.notificationclick({notification:{data:{url},close(){closed=true}},waitUntil:p=>promise=p});await promise;
  assert.equal(closed,true);assert.deepEqual(h.navigated,[url.startsWith('/stock')?origin+url:'/app']);
 }
});
