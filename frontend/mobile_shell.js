(function(){
  const isStandalone=()=>window.matchMedia('(display-mode: standalone)').matches||window.navigator.standalone===true;
  const isIOS=()=>/iphone|ipad|ipod/i.test(navigator.userAgent||'');
  const isMobile=()=>window.matchMedia('(max-width:900px)').matches;
  const ALERT_ENABLED='ns-mobile-alerts-v1';
  let deferredInstallPrompt=null,confirmedEndpoint=null;

  window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();deferredInstallPrompt=event});

  async function registerServiceWorker(){
    if(!('serviceWorker' in navigator))return null;
    try{return await navigator.serviceWorker.register('/sw.js',{scope:'/'})}
    catch(error){console.warn('Aksjer service worker registration failed',error);return null}
  }

  function migrateLegacyMobileRoutes(){
    if(!isMobile())return false;
    const path=location.pathname,view=new URLSearchParams(location.search).get('view');
    if((path==='/'||path==='/app'||path==='/index.html')&&view==='radar'){location.replace('/stock');return true}
    if(path==='/mobile'||path==='/mobile.html'){location.replace('/app');return true}
    return false;
  }

  function installInstructions(){
    let modal=document.getElementById('nsInstallModal');if(modal){modal.hidden=false;return}
    modal=document.createElement('div');modal.id='nsInstallModal';modal.className='nsMobileModal';
    modal.innerHTML=`<div class="nsMobileModalCard"><div class="nsMobileModalHead"><strong>Installer Aksjer</strong><button type="button" id="nsInstallClose">×</button></div>${isIOS()?'<p>På iPhone/iPad i Safari:</p><ol><li>Trykk <b>Del</b>.</li><li>Velg <b>Legg til på Hjem-skjerm</b>.</li><li>Trykk <b>Legg til</b>.</li></ol><p class="nsMobileMuted">Den installerte appen åpner den fokuserte mobiloversikten.</p>':'<p>Åpne nettlesermenyen og velg <b>Installer app</b> eller <b>Legg til på startskjerm</b>.</p>'}</div>`;
    document.body.appendChild(modal);document.getElementById('nsInstallClose').onclick=()=>modal.hidden=true;modal.onclick=e=>{if(e.target===modal)modal.hidden=true};
  }
  async function installApp(){if(deferredInstallPrompt){deferredInstallPrompt.prompt();try{await deferredInstallPrompt.userChoice}catch{}deferredInstallPrompt=null}else installInstructions()}

  function mountNav(){
    // Canonical mobile navigation is owned by mobile_nav.js.
    // Keep this runtime focused on install/push behavior.
  }

  async function getJson(path){const r=await fetch(path,{cache:'no-store',signal:AbortSignal.timeout(15000)});if(!r.ok||r.redirected)throw Error('Data utilgjengelig');return r.json()}
  async function serviceWorkerReady(){
    let timer;
    try{return await Promise.race([navigator.serviceWorker.ready,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Service worker utilgjengelig')),15000)})])}
    finally{clearTimeout(timer)}
  }

  function base64Key(value){
    const padding='='.repeat((4-value.length%4)%4),base64=(value+padding).replace(/-/g,'+').replace(/_/g,'/'),raw=atob(base64),out=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)out[i]=raw.charCodeAt(i);return out;
  }
  async function registerRealPush(){
    if(!('PushManager' in window)||!('serviceWorker' in navigator))return {ready:false,reason:'unsupported'};
    let keyInfo;try{keyInfo=await getJson('/api/push/public-key')}catch{return {ready:false,reason:'backend_unavailable'}}
    if(!keyInfo.configured||!keyInfo.public_key)return {ready:false,reason:'not_configured'};
    const reg=await serviceWorkerReady();
    let sub=await reg.pushManager.getSubscription();
    if(!sub)sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:base64Key(keyInfo.public_key)});
    const json=sub.toJSON();
    const response=await fetch('/api/push/subscribe',{method:'POST',cache:'no-store',signal:AbortSignal.timeout(15000),headers:{'content-type':'application/json'},body:JSON.stringify({endpoint:json.endpoint,keys:json.keys,user_agent:navigator.userAgent})});
    if(!response.ok||response.redirected)throw Error('Registrering av push mislyktes');
    const result=await response.json();
    if(result.status!=='ok'||result.delivery_ready!==true)return {ready:false,reason:'not_configured'};
    confirmedEndpoint=sub.endpoint;
    return {ready:true,subscription:sub};
  }
  async function currentPushState(){
    if(!('serviceWorker' in navigator)||!('PushManager' in window))return {active:false,configured:false};
    try{const [reg,status]=await Promise.all([serviceWorkerReady(),getJson('/api/push/status')]),sub=await reg.pushManager.getSubscription();return {active:!!sub&&sub.endpoint===confirmedEndpoint&&status.delivery_ready===true,configured:!!status.delivery_ready,subscription:sub,status}}catch{return {active:false,configured:false}}
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
      if(!state.active)throw Error('Bakgrunnspush er ikke aktivert på denne enheten ennå.');
      const response=await fetch('/api/push/test',{method:'POST',cache:'no-store',signal:AbortSignal.timeout(15000),headers:{'content-type':'application/json'},body:JSON.stringify({endpoint:state.subscription.endpoint})});
      const data=await response.json().catch(()=>({}));
      if(!response.ok||response.redirected||data.status!=='ok')throw Error('Push-test ble ikke bekreftet av serveren');
      setAlertUi('Push-tjenesten har akseptert testen. Kontroller på telefonen om varslet kom fram.',true);
    }catch(error){confirmedEndpoint=null;setPushTestVisible(false);setAlertUi('Testpush feilet: '+String(error.message||error),false)}
    finally{if(button){button.disabled=false;button.textContent='Test push'}}
  }
  async function enableAlerts(){
    if(isIOS()&&!isStandalone()){setAlertUi('Legg Aksjer til på Hjem-skjerm i Safari og åpne appen der for å aktivere push.',false);return}
    if(!('Notification' in window)||!('serviceWorker' in navigator)||!('PushManager' in window)){setAlertUi('Denne nettleseren støtter ikke Aksjer-varsler.',false);return}
    const button=document.getElementById('nsEnableAlerts');if(button)button.disabled=true;
    confirmedEndpoint=null;localStorage.removeItem(ALERT_ENABLED);setPushTestVisible(false);
    try{
      let permission=Notification.permission;if(permission!=='granted')permission=await Notification.requestPermission();
      if(permission!=='granted'){setAlertUi('Varsler er ikke tillatt. Endre tillatelsen i nettleserinnstillingene.',false);return}
      const push=await registerRealPush();
      if(!push.ready){setAlertUi('Push er ikke aktivert. Serveroppsettet eller nettleserstøtten er ikke klart.',false);return}
      localStorage.setItem(ALERT_ENABLED,'1');setPushTestVisible(true);
      setAlertUi('Push-abonnement er registrert. Bruk «Test push» og bekreft mottak på telefonen.',true);
    }catch{setAlertUi('Push kunne ikke registreres. Kontroller tilkobling og innlogging, og prøv igjen.',false)}
    finally{if(button)button.disabled=false}
  }
  async function bindAlertButton(){
    const button=document.getElementById('nsEnableAlerts');
    // A saved legacy preference must never start portfolio requests or polling.
    if(!button)return;
    button.onclick=enableAlerts;setPushTestVisible(false);
    setAlertUi('Push er ikke bekreftet registrert i denne økten. Aktiver for å registrere og teste.',false);
  }

  async function mount(){if(migrateLegacyMobileRoutes())return;await registerServiceWorker();mountNav();if(!['/app','/','/index.html','/stock','/stock/','/stock.html','/morning','/morning.html'].includes(location.pathname))await bindAlertButton();window.NordicSignalMobile={installApp,enableAlerts,registerRealPush,currentPushState,testRealPush}}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
})();
