(()=>{
 const list=document.getElementById('alertList'),summary=document.getElementById('summary'),refresh=document.getElementById('refreshAlerts');
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const names={score_change:'Scoreendring',trend_activity:'Trend / aktivitet',early_opportunity:'Opportunity'};
 function time(value){if(!value)return 'Tidspunkt ukjent';const d=new Date(value);return Number.isFinite(d.getTime())?d.toLocaleString('nb-NO',{timeZone:'Europe/Oslo'}):'Tidspunkt ukjent'}
 function render(items){if(!items.length){list.innerHTML='<div class="notice">Ingen signalhendelser i tilgjengelig historikk.</div>';return}list.innerHTML=items.map(x=>{const ticker=String(x.ticker||x.symbol||'').toUpperCase().replace(/\.OL$/,'');const content='<span class="time">'+esc(names[x.event_type]||'Signalhendelse')+' · '+esc(time(x.updated_at))+' (Oslo)</span><h2>'+esc(x.name||ticker||'Marked')+'</h2><p>'+esc(x.event||'Registrert hendelse')+'</p>'+(x.detail?'<p class="muted">'+esc(x.detail)+'</p>':'');return /^[A-Z0-9.-]{1,16}$/.test(ticker)?'<a class="alertCard" href="/stock?ticker='+encodeURIComponent(ticker)+'">'+content+'<span>'+esc(ticker)+' →</span></a>':'<article class="alertCard">'+content+'</article>'}).join('')}
 async function load(){if(refresh.disabled)return;refresh.disabled=true;summary.textContent='Laster…';try{const r=await fetch('/api/signal-events?asset_class=Aksjer&limit=30',{cache:'no-store',signal:AbortSignal.timeout(30000)});if(!r.ok)throw Error('HTTP '+r.status);const d=await r.json();if(!Array.isArray(d.items))throw Error('Uventet dataformat');render(d.items);summary.textContent=d.items.length+' hendelser · maks 30 vist'}catch{list.innerHTML='<div class="notice">UTILGJENGELIG · kunne ikke hente signalhendelser. Prøv Oppdater igjen.</div>';summary.textContent='Kunne ikke laste'}finally{refresh.disabled=false}}
 async function loadPushStatus(){
  const button=document.getElementById('refreshPushStatus');if(button.disabled)return;button.disabled=true;
  const permission=document.getElementById('pushPermission'),subscription=document.getElementById('pushSubscription'),server=document.getElementById('pushServer');
  const supported='Notification' in window&&'PushManager' in window&&'serviceWorker' in navigator;
  permission.textContent='Varseltillatelse: '+(!('Notification' in window)?'ikke støttet':({granted:'tillatt',denied:'blokkert',default:'ikke gitt'})[Notification.permission]||'ukjent');
  subscription.textContent=supported?'Nettleserabonnement: kontrollerer…':'Nettleserabonnement: ikke støttet her';
  server.textContent='Push-tjeneste: kontrollerer…';
  const local=async()=>{
   if(!supported)return;
   try{const reg=await navigator.serviceWorker.getRegistration('/'),sub=reg?await reg.pushManager.getSubscription():null;subscription.textContent='Nettleserabonnement: '+(sub?'finnes på denne enheten · serverregistrering ikke bekreftet':'ikke funnet på denne enheten')}
   catch{subscription.textContent='Nettleserabonnement: kunne ikke kontrolleres'}
  };
  const remote=async()=>{
   try{const r=await fetch('/api/push/status',{cache:'no-store',signal:AbortSignal.timeout(15000)});if(!r.ok||r.redirected)throw Error();const d=await r.json();server.textContent='Push-tjeneste: '+(d.delivery_ready===true?'serveroppsett klart · mottak ikke bekreftet':d.delivery_ready===false?'serveroppsett ikke klart':'ukjent status')}
   catch{server.textContent='Push-tjeneste: utilgjengelig · status ukjent'}
  };
  try{await Promise.all([local(),remote()])}finally{button.disabled=false}
 }
 // An older cached HTML shell may not have the status panel yet.
 const pushRefresh=document.getElementById('refreshPushStatus');if(pushRefresh){pushRefresh.onclick=loadPushStatus;loadPushStatus()}
 refresh.onclick=load;load();
})();
