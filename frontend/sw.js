const CACHE_NAME='aksjer-shell-v6';
const SHELL=['/app','/morning','/stock','/theme.css','/theme_light_fix.css','/theme_mode.js','/brand_config.js','/ui_shell.js','/mobile_nav.js','/mobile_shell.js','/manifest.webmanifest','/aksjer-mark.svg','/stock_selector.js','/stock_data_bridge.js','/stock_extras.js','/stock_readiness.js','/stock_evidence_ui.js','/stock_opportunity_ui.js','/alert_local_capture.js','/alert_nav_ui.js'];

self.addEventListener('install',event=>{
  event.waitUntil(caches.open(CACHE_NAME).then(cache=>cache.addAll(SHELL)).catch(()=>null));
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
      if(response&&response.ok){const copy=response.clone();caches.open(CACHE_NAME).then(cache=>cache.put(request,copy)).catch(()=>null)}
      return response;
    }catch(error){
      const cached=await caches.match(request);if(cached)return cached;
      if(request.mode==='navigate'){const app=await caches.match('/app');if(app)return app}
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
  const target=(event.notification.data&&event.notification.data.url)||'/app';
  event.waitUntil((async()=>{
    const list=await clients.matchAll({type:'window',includeUncontrolled:true});
    for(const client of list){try{const url=new URL(client.url);if(url.origin===self.location.origin){await client.focus();if('navigate' in client)await client.navigate(target);return}}catch{}}
    if(clients.openWindow)return clients.openWindow(target);
  })());
});
