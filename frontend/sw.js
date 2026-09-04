const CACHE_NAME='nordicsignal-shell-v4';
const SHELL=['/mobile','/alerts','/insider','/news','/readiness','/stock','/calendar','/theme.css','/theme_mode.js','/ui_shell.js','/mobile_shell.js','/access_gate.js','/manifest.webmanifest','/insider_clean_ui.js','/portfolio_dashboard.js','/analysis.js','/stock_evidence_ui.js','/alerts.js','/alert_local_capture.js','/alert_nav_ui.js'];

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
      if(request.mode==='navigate'){const mobile=await caches.match('/mobile');if(mobile)return mobile}
      throw error;
    }
  })());
});

self.addEventListener('push',event=>{
  let data={};
  try{data=event.data?event.data.json():{}}catch{try{data={body:event.data?event.data.text():''}}catch{data={}}}
  const title=data.title||'NordicSignal';
  const options={
    body:data.body||'Ny markedshendelse registrert.',
    tag:data.tag||'nordicsignal-update',
    renotify:true,
    data:{url:data.url||'/mobile',timestamp:data.timestamp||null},
  };
  event.waitUntil(self.registration.showNotification(title,options));
});

self.addEventListener('notificationclick',event=>{
  event.notification.close();
  const target=(event.notification.data&&event.notification.data.url)||'/mobile';
  event.waitUntil((async()=>{
    const list=await clients.matchAll({type:'window',includeUncontrolled:true});
    for(const client of list){
      try{const url=new URL(client.url);if(url.origin===self.location.origin){await client.focus();if('navigate' in client)await client.navigate(target);return}}catch{}
    }
    if(clients.openWindow)return clients.openWindow(target);
  })());
});
