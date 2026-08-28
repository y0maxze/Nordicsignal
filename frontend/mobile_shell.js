(function(){
  const isStandalone=()=>window.matchMedia('(display-mode: standalone)').matches||window.navigator.standalone===true;
  const isIOS=()=>/iphone|ipad|ipod/i.test(navigator.userAgent||'');
  const isMobile=()=>window.matchMedia('(max-width:900px)').matches;
  const ALERT_ENABLED='ns-mobile-alerts-v1';
  const ALERT_SEEN='ns-mobile-alert-seen-v1';
  let deferredInstallPrompt=null,alertTimer=null;

  window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();deferredInstallPrompt=event});

  async function registerServiceWorker(){
    if(!('serviceWorker' in navigator))return null;
    try{return await navigator.serviceWorker.register('/sw.js',{scope:'/'})}
    catch(error){console.warn('NordicSignal service worker registration failed',error);return null}
  }

  function migrateLegacyMobileRoutes(){
    if(!isMobile())return false;
    const path=location.pathname,view=new URLSearchParams(location.search).get('view');
    if((path==='/'||path==='/app'||path==='/index.html')&&view==='insider'){location.replace('/insider');return true}
    if((path==='/'||path==='/app'||path==='/index.html')&&view==='radar'){location.replace('/stock');return true}
    if((path==='/'||path==='/app'||path==='/index.html')&&isStandalone()&&!view){location.replace('/mobile');return true}
    return false;
  }

  function installInstructions(){
    let modal=document.getElementById('nsInstallModal');if(modal){modal.hidden=false;return}
    modal=document.createElement('div');modal.id='nsInstallModal';modal.className='nsMobileModal';
    modal.innerHTML=`<div class="nsMobileModalCard"><div class="nsMobileModalHead"><strong>Installer NordicSignal</strong><button type="button" id="nsInstallClose">×</button></div>${isIOS()?'<p>På iPhone/iPad i Safari:</p><ol><li>Trykk <b>Del</b>.</li><li>Velg <b>Legg til på Hjem-skjerm</b>.</li><li>Trykk <b>Legg til</b>.</li></ol><p class="nsMobileMuted">Den installerte appen åpner den fokuserte mobiloversikten.</p>':'<p>Åpne nettlesermenyen og velg <b>Installer app</b> eller <b>Legg til på startskjerm</b>.</p>'}</div>`;
    document.body.appendChild(modal);document.getElementById('nsInstallClose').onclick=()=>modal.hidden=true;modal.onclick=e=>{if(e.target===modal)modal.hidden=true};
  }
  async function installApp(){if(deferredInstallPrompt){deferredInstallPrompt.prompt();try{await deferredInstallPrompt.userChoice}catch{}deferredInstallPrompt=null}else installInstructions()}

  function mountNav(){
    if(document.getElementById('nsMobileNav'))return;
    const style=document.createElement('style');style.id='nsMobileShellStyle';style.textContent=`
      .nsMobileNav,.nsMobileModal{display:none}.nsPushTest{margin-left:6px}
      @media(max-width:900px){body{padding-bottom:78px!important}.main{padding-bottom:96px!important}.section,.card{max-width:100%}.table{display:block;overflow-x:auto;-webkit-overflow-scrolling:touch;white-space:nowrap}.nsGlobalHome{display:none!important}.nsMobileNav{display:grid;position:fixed;z-index:2147483000;left:8px;right:8px;bottom:max(8px,env(safe-area-inset-bottom));grid-template-columns:repeat(5,1fr);background:rgba(13,13,13,.97);border:1px solid #2b2b2b;border-radius:15px;box-shadow:0 18px 50px rgba(0,0,0,.6);backdrop-filter:blur(15px);overflow:hidden}.nsMobileNav a{color:#9c9c9c!important;text-decoration:none!important;padding:10px 2px 9px;text-align:center;font:700 9px Inter,system-ui,-apple-system,"Segoe UI",sans-serif}.nsMobileNav a.active{background:#181818;color:#fff!important}.nsMobileNavIcon{display:block;font-size:16px;line-height:18px;margin-bottom:3px;color:#eaeaea}.nsMobileModal{position:fixed;display:flex;z-index:2147483646;inset:0;background:rgba(0,0,0,.82);align-items:center;justify-content:center;padding:16px}.nsMobileModal[hidden]{display:none}.nsMobileModalCard{width:min(460px,100%);background:#0d0d0d;border:1px solid #303030;border-radius:14px;padding:18px;color:#f4f4f4}.nsMobileModalHead{display:flex;justify-content:space-between;align-items:center}.nsMobileModalHead strong{font-size:18px}.nsMobileModalHead button{font-size:24px;border:0;background:transparent;color:#ddd}.nsMobileModalCard p,.nsMobileModalCard li{color:#c4c4c4;line-height:1.6}.nsMobileMuted{color:#8f8f8f;font-size:11px}}
    `;document.head.appendChild(style);
    const p=location.pathname;const active=name=>name==='home'?(p==='/mobile'||p==='/mobile/') : name==='insider'?p.startsWith('/insider') : name==='investment'?(p.startsWith('/readiness')||p.startsWith('/investment-check')) : name==='signals'?(p.startsWith('/stock')||p.startsWith('/intelligence')||p.startsWith('/instrument')) : name==='news'?p.startsWith('/news'):false;
    const nav=document.createElement('nav');nav.id='nsMobileNav';nav.className='nsMobileNav';nav.setAttribute('aria-label','NordicSignal mobilnavigasjon');nav.innerHTML=`<a href="/mobile" class="${active('home')?'active':''}"><span class="nsMobileNavIcon">⌂</span>Oversikt</a><a href="/insider" class="${active('insider')?'active':''}"><span class="nsMobileNavIcon">◎</span>Insider</a><a href="/readiness" class="${active('investment')?'active':''}"><span class="nsMobileNavIcon">✓</span>Investment</a><a href="/stock" class="${active('signals')?'active':''}"><span class="nsMobileNavIcon">↗</span>Signaler</a><a href="/news" class="${active('news')?'active':''}"><span class="nsMobileNavIcon">◫</span>Nyheter</a>`;document.body.appendChild(nav);
  }

  async function getJson(path){const r=await fetch(path,{cache:'no-store'});if(!r.ok)throw Error(path+' '+r.status);return r.json()}
  function alertId(x){return [x.kind||x.type||'event',x.ticker||x.company||'',x.occurred_at||x.trade_date||x.latest_date||'',x.url||x.title||x.signal_label||''].join('|').toLowerCase()}
  async function collectAlerts(){
    const out=[];
    const results=await Promise.allSettled([getJson('/api/holdings/events?limit=24'),getJson('/api/insider-market?limit=50&days=7')]);
    const holdings=results[0].status==='fulfilled'?(results[0].value.items||[]):[];
    holdings.filter(x=>x.importance==='high'||x.kind==='report'||x.kind==='insider').forEach(x=>out.push({id:alertId(x),title:`${x.ticker||'Beholdning'} · ${x.title||'Viktig hendelse'}`,body:x.brief||x.title||'Ny hendelse i beholdningen',url:x.url||'/mobile'}));
    const market=results[1].status==='fulfilled'?results[1].value:{};
    (market.pulses||[]).filter(p=>p.flags?.includes('cluster_buying')||p.flags?.includes('large_buy')||p.flags?.includes('repeated_buying')||p.tone==='negative').slice(0,15).forEach(p=>out.push({id:alertId(p),title:`${p.company||p.ticker||'Insider'} · ${p.signal_label||'Insideraktivitet'}`,body:`${p.buy_count||0} kjøp · ${p.sell_count||0} salg${(p.actors||[]).length?' · '+p.actors.slice(0,2).join(', '):''}`,url:'/insider'}));
    return out;
  }
  function readSeen(){try{return new Set(JSON.parse(localStorage.getItem(ALERT_SEEN)||'[]'))}catch{return new Set()}}
  function writeSeen(set){localStorage.setItem(ALERT_SEEN,JSON.stringify([...set].slice(-160)))}
  async function showAlert(item){try{const reg=await navigator.serviceWorker.ready;await reg.showNotification(item.title,{body:item.body,tag:item.id,data:{url:item.url||'/mobile'}})}catch{try{new Notification(item.title,{body:item.body,tag:item.id})}catch{}}}
  async function pollAlerts({baseline=false}={}){
    if(localStorage.getItem(ALERT_ENABLED)!=='1'||typeof Notification==='undefined'||Notification.permission!=='granted')return;
    let items=[];try{items=await collectAlerts()}catch{return}
    const seen=readSeen();if(baseline||seen.size===0){items.forEach(x=>seen.add(x.id));writeSeen(seen);return}
    const fresh=items.filter(x=>!seen.has(x.id));fresh.slice(0,4).forEach(x=>{seen.add(x.id);showAlert(x)});items.forEach(x=>seen.add(x.id));writeSeen(seen);
  }

  function base64Key(value){
    const padding='='.repeat((4-value.length%4)%4),base64=(value+padding).replace(/-/g,'+').replace(/_/g,'/'),raw=atob(base64),out=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)out[i]=raw.charCodeAt(i);return out;
  }
  async function registerRealPush(){
    if(!('PushManager' in window)||!('serviceWorker' in navigator))return {ready:false,reason:'unsupported'};
    let keyInfo;try{keyInfo=await getJson('/api/push/public-key')}catch{return {ready:false,reason:'backend_unavailable'}}
    if(!keyInfo.configured||!keyInfo.public_key)return {ready:false,reason:'not_configured'};
    const reg=await navigator.serviceWorker.ready;
    let sub=await reg.pushManager.getSubscription();
    if(!sub)sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:base64Key(keyInfo.public_key)});
    const json=sub.toJSON();
    const response=await fetch('/api/push/subscribe',{method:'POST',cache:'no-store',headers:{'content-type':'application/json'},body:JSON.stringify({endpoint:json.endpoint,keys:json.keys,user_agent:navigator.userAgent})});
    if(!response.ok)throw Error('push subscribe '+response.status);
    return {ready:true,subscription:sub};
  }
  async function currentPushState(){
    if(!('serviceWorker' in navigator)||!('PushManager' in window))return {active:false,configured:false};
    try{const [reg,status]=await Promise.all([navigator.serviceWorker.ready,getJson('/api/push/status')]),sub=await reg.pushManager.getSubscription();return {active:!!sub&&!!status.delivery_ready,configured:!!status.delivery_ready,subscription:sub,status}}catch{return {active:false,configured:false}}
  }

  function setAlertUi(text,enabled){const s=document.getElementById('alertStatus'),b=document.getElementById('nsEnableAlerts');if(s&&text)s.textContent=text;if(b){b.textContent=enabled?'Varsler på':'Aktiver';b.classList.toggle('primary',!enabled)}}
  function setPushTestVisible(visible){
    const enable=document.getElementById('nsEnableAlerts');if(!enable)return;
    let button=document.getElementById('nsTestPush');
    if(!button){button=document.createElement('button');button.id='nsTestPush';button.type='button';button.className='btn nsPushTest';button.textContent='Test push';button.onclick=testRealPush;enable.insertAdjacentElement('afterend',button)}
    button.hidden=!visible;
  }
  async function testRealPush(){
    const button=document.getElementById('nsTestPush');if(button){button.disabled=true;button.textContent='Sender…'}
    try{
      const state=await currentPushState();
      if(!state.subscription||!state.configured)throw Error('Bakgrunnspush er ikke aktivert på denne enheten ennå.');
      const response=await fetch('/api/push/test',{method:'POST',cache:'no-store',headers:{'content-type':'application/json'},body:JSON.stringify({endpoint:state.subscription.endpoint})});
      const data=await response.json().catch(()=>({}));
      if(!response.ok)throw Error(data.detail||('HTTP '+response.status));
      setAlertUi('Testpush er sendt. Lukk/minimer PWA-en og kontroller at NordicSignal-varslet vises.',true);
    }catch(error){setAlertUi('Testpush feilet: '+String(error.message||error),true)}
    finally{if(button){button.disabled=false;button.textContent='Test push'}}
  }
  async function enableAlerts(){
    if(!('Notification' in window)||!('serviceWorker' in navigator)){setAlertUi('Denne nettleseren støtter ikke NordicSignal-varsler.',false);return}
    let permission=Notification.permission;if(permission!=='granted')permission=await Notification.requestPermission();
    if(permission!=='granted'){localStorage.removeItem(ALERT_ENABLED);setPushTestVisible(false);setAlertUi('Varsler er ikke tillatt. Du kan endre dette i iPhone/nettleserinnstillinger.',false);return}
    localStorage.setItem(ALERT_ENABLED,'1');await pollAlerts({baseline:true});
    let push={ready:false};try{push=await registerRealPush()}catch(error){console.warn('Web Push subscription failed',error)}
    setPushTestVisible(!!push.ready);
    setAlertUi(push.ready?'Ekte bakgrunnspush er aktivert. Bruk «Test push» for å kontrollere faktisk levering.':'Varsler er aktivert. Push-nøkler er ikke konfigurert på serveren ennå, så appen bruker foreløpig lokal polling når den kjører.',true);startAlertPolling();
  }
  function startAlertPolling(){if(alertTimer)clearInterval(alertTimer);if(localStorage.getItem(ALERT_ENABLED)!=='1')return;alertTimer=setInterval(()=>pollAlerts(),120000)}
  async function bindAlertButton(){const b=document.getElementById('nsEnableAlerts');if(b)b.onclick=enableAlerts;const on=localStorage.getItem(ALERT_ENABLED)==='1'&&typeof Notification!=='undefined'&&Notification.permission==='granted';if(on){const push=await currentPushState();setPushTestVisible(push.active);setAlertUi(push.active?'Bakgrunnspush er aktiv på denne enheten. Bruk «Test push» for leveringstest.':'Varsler er på. Lokal polling brukes til VAPID-push er konfigurert.',true);pollAlerts({baseline:false});startAlertPolling()}else setPushTestVisible(false)}

  async function mount(){if(migrateLegacyMobileRoutes())return;await registerServiceWorker();mountNav();await bindAlertButton();window.NordicSignalMobile={installApp,enableAlerts,pollAlerts,registerRealPush,currentPushState,testRealPush}}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
})();
