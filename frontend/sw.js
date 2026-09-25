const CACHE_NAME='aksjer-shell-v10';
const SHELL=['/app','/morning','/stock','/theme.css','/finance_shell.css','/finance_shell.js','/ipo_discovery.js','/ipo_discovery.css','/theme_light_fix.css','/theme_mode.js','/brand_config.js','/ui_shell.js','/mobile_nav.js','/mobile_shell.js','/manifest.webmanifest','/aksjer-mark.svg','/stock_selector.js','/stock_data_bridge.js','/stock_extras.js','/stock_analysis.js','/stock_evidence_ui.js','/alert_local_capture.js','/alert_nav_ui.js'];

function cacheable(response){return response&&response.ok&&!response.redirected&&response.type!=='opaqueredirect'}

self.addEventListener('install',event=>{
  event.waitUntil(caches.open(CACHE_NAME).then(cache=>Promise.all(SHELL.map(async path=>{const response=await fetch(path);if(cacheable(response))await cache.put(path,response)}))).catch(()=>null));
  self.skipWaiting();
});

self.addEventListener('activate',event=>{
  event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE_NAME).map(key=>caches.delete(key)))));
  self.clients.claim();
});

self.addEventListener('fetch',event=>{
  const request=event.request;
  if(request.method!=='GET')return;
  const url=new URL(request.url);
  if(url.origin!==self.location.origin)return;
  if(url.pathname.startsWith('/api/'))return;
  event.respondWith((async()=>{
    try{
      const response=await fetch(request);
      if(cacheable(response)){const copy=response.clone();caches.open(CACHE_NAME).then(cache=>cache.put(request,copy)).catch(()=>null)}
      return response;
    }catch(error){
      const cached=await caches.match(request);if(cached)return cached;
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
  const candidate=new URL((event.notification.data&&event.notification.data.url)||'/app',self.location.origin);const target=candidate.origin===self.location.origin?candidate.href:'/app';
  event.waitUntil((async()=>{
    const list=await clients.matchAll({type:'window',includeUncontrolled:true});
    for(const client of list){try{const url=new URL(client.url);if(url.origin===self.location.origin){await client.focus();if('navigate' in client)await client.navigate(target);return}}catch{}}
    if(clients.openWindow)return clients.openWindow(target);
  })());
});
