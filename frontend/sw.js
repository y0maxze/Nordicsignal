const CACHE_NAME='aksjer-shell-v36';
const SHELL=['/app','/morning','/morning_navigation.js','/stock','/theme.css','/finance_shell.css','/finance_shell.js','/company_context.js','/ipo_discovery.js','/ipo_discovery.css','/theme_light_fix.css','/theme_mode.js','/brand_config.js','/ui_shell.js','/mobile_nav.js','/mobile_shell.js','/manifest.webmanifest','/aksjer-mark.svg','/stock_selector.js','/stock_data_bridge.js','/stock_extras.js','/stock_analysis.js','/corporate_action_context.js','/stock_evidence_ui.js','/alert_local_capture.js','/alert_nav_ui.js'];

function shellRequest(url){
  if(url.origin!==self.location.origin||!SHELL.includes(url.pathname))return false;
  if(!url.search)return true;
  if(url.pathname==='/app')return [...url.searchParams].every(([key,value])=>key==='filter'&&value==='ipo');
  if(url.pathname==='/stock')return [...url.searchParams].every(([key,value])=>['ticker','symbol'].includes(key)&&/^[A-Za-z0-9._-]{1,32}$/.test(value));
  return false;
}
function cacheable(response,url){
  if(!response||!response.ok||response.redirected||response.type==='opaqueredirect')return false;
  const type=response.headers.get('content-type')||'';
  if(['/app','/stock','/morning'].includes(url.pathname))return type.includes('text/html')&&response.headers.get('x-aksjer-static-shell')==='1';
  if(url.pathname.endsWith('.js'))return /(?:javascript|ecmascript)/i.test(type);
  if(url.pathname.endsWith('.css'))return type.includes('text/css');
  if(url.pathname.endsWith('.svg'))return type.includes('image/svg+xml');
  return url.pathname.endsWith('.webmanifest')&&/(?:manifest\+json|application\/json)/i.test(type);
}

self.addEventListener('install',event=>{
  event.waitUntil(caches.open(CACHE_NAME).then(cache=>Promise.allSettled(SHELL.map(async path=>{const response=await fetch(path);if(cacheable(response,new URL(path,self.location.origin)))await cache.put(path,response)}))).catch(()=>null));
  self.skipWaiting();
});

self.addEventListener('activate',event=>{
  event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('aksjer-shell-')&&key!==CACHE_NAME).map(key=>caches.delete(key)))).then(()=>self.clients.claim()));
});

self.addEventListener('fetch',event=>{
  const request=event.request;
  if(request.method!=='GET')return;
  const url=new URL(request.url);
  if(!shellRequest(url))return;
  event.respondWith((async()=>{
    try{
      const response=await fetch(request);
      if(cacheable(response,url)){try{const cache=await caches.open(CACHE_NAME);await cache.put(request,response.clone())}catch{}}
      return response;
    }catch(error){
      let cached;try{cached=await (await caches.open(CACHE_NAME)).match(request)}catch{}
      if(cached&&cacheable(cached,url))return cached;
      if(request.mode==='navigate')return new Response('<!doctype html><html lang="no"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Aksjer · Frakoblet</title><h1>Du er frakoblet</h1><p>Denne siden er ikke tilgjengelig uten nett. Ingen markedsdata er bekreftet oppdatert.</p><a href="/app">Åpne lagret Marked</a></html>',{headers:{'content-type':'text/html; charset=utf-8'}});
      throw error;
    }
  })());
});

self.addEventListener('push',event=>{
  let data={};
  try{data=event.data?event.data.json():{}}catch{try{data={body:event.data?event.data.text():''}}catch{data={}}}
  const title=data.title||'Aksjer';
  const options={body:data.body||'Ny markedshendelse registrert.',tag:data.tag||'aksjer-update',renotify:true,data:{url:data.url||'/app',timestamp:data.timestamp||null}};
  event.waitUntil(self.registration.showNotification(title,options));
});

self.addEventListener('notificationclick',event=>{
  event.notification.close();
  let target='/app';try{const candidate=new URL((event.notification.data&&event.notification.data.url)||'/app',self.location.origin);if(candidate.origin===self.location.origin&&!/^\/(api|cdn-cgi)(\/|$)/.test(candidate.pathname))target=candidate.href}catch{}
  event.waitUntil((async()=>{
    const list=await clients.matchAll({type:'window',includeUncontrolled:true});
    for(const client of list){try{const url=new URL(client.url);if(url.origin===self.location.origin){await client.focus();if('navigate' in client)await client.navigate(target);return}}catch{}}
    if(clients.openWindow)return clients.openWindow(target);
  })());
});
