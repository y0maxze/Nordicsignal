(function(){
  const isStandalone=()=>window.matchMedia('(display-mode: standalone)').matches||window.navigator.standalone===true;
  const isIOS=()=>/iphone|ipad|ipod/i.test(navigator.userAgent||'');
  let deferredInstallPrompt=null;

  window.addEventListener('beforeinstallprompt',event=>{
    event.preventDefault();
    deferredInstallPrompt=event;
    const install=document.getElementById('nsMobileInstall');
    if(install)install.hidden=false;
  });

  function registerServiceWorker(){
    if(!('serviceWorker' in navigator))return;
    navigator.serviceWorker.register('/sw.js',{scope:'/'}).catch(error=>console.warn('NordicSignal service worker registration failed',error));
  }

  function routeRequestedView(){
    if(location.pathname!=='/app'&&location.pathname!=='/'&&location.pathname!=='/index.html')return;
    const view=new URLSearchParams(location.search).get('view');
    const fn={
      insider:'renderInsider',
      short:'renderShort',
      markets:'renderMarkets',
      radar:'renderRadar',
      watchlist:'renderWatchlist'
    }[view];
    if(!fn)return;
    let attempts=0;
    const run=()=>{
      attempts+=1;
      if(typeof window[fn]==='function'){
        window[fn]();
        return;
      }
      if(attempts<30)setTimeout(run,100);
    };
    setTimeout(run,50);
  }

  function installInstructions(){
    let modal=document.getElementById('nsInstallModal');
    if(modal){modal.hidden=false;return}
    modal=document.createElement('div');
    modal.id='nsInstallModal';
    modal.className='nsMobileModal';
    const ios=isIOS();
    modal.innerHTML=`<div class="nsMobileModalCard"><div class="nsMobileModalHead"><strong>Installer NordicSignal</strong><button type="button" aria-label="Lukk" id="nsInstallClose">×</button></div>${ios?'<p>På iPhone/iPad i Safari:</p><ol><li>Trykk <b>Del</b>-knappen i Safari.</li><li>Velg <b>Legg til på Hjem-skjerm</b>.</li><li>Trykk <b>Legg til</b>.</li></ol><p class="nsMobileMuted">NordicSignal åpnes deretter som en egen app fra hjemskjermen.</p>':'<p>Åpne nettlesermenyen og velg <b>Installer app</b> eller <b>Legg til på startskjerm</b>.</p>'}</div>`;
    document.body.appendChild(modal);
    document.getElementById('nsInstallClose').onclick=()=>{modal.hidden=true};
    modal.onclick=event=>{if(event.target===modal)modal.hidden=true};
  }

  async function installApp(){
    if(deferredInstallPrompt){
      deferredInstallPrompt.prompt();
      try{await deferredInstallPrompt.userChoice}catch{}
      deferredInstallPrompt=null;
      return;
    }
    installInstructions();
  }

  function mount(){
    if(document.getElementById('nsMobileNav'))return;
    const style=document.createElement('style');
    style.id='nsMobileShellStyle';
    style.textContent=`
      .nsMobileNav,.nsMobileMoreBackdrop,.nsMobileModal{display:none}
      @media(max-width:900px){
        body{padding-bottom:74px!important}
        .main{padding-bottom:92px!important}
        .section,.card{max-width:100%;overflow:hidden}
        .table{display:block;overflow-x:auto;-webkit-overflow-scrolling:touch;white-space:nowrap}
        .nsMobileNav{display:grid;position:fixed;z-index:2147483000;left:10px;right:10px;bottom:max(10px,env(safe-area-inset-bottom));grid-template-columns:repeat(5,1fr);background:rgba(13,13,13,.96);border:1px solid #2b2b2b;border-radius:14px;box-shadow:0 18px 50px rgba(0,0,0,.55);backdrop-filter:blur(14px);overflow:hidden}
        .nsMobileNav a,.nsMobileNav button{appearance:none;border:0;background:transparent;color:#aaa!important;text-decoration:none!important;padding:11px 4px 10px;font:650 10px Inter,system-ui,-apple-system,"Segoe UI",sans-serif;text-align:center;cursor:pointer}
        .nsMobileNav a.active{color:#fff!important;background:#171717}
        .nsMobileNavIcon{display:block;font-size:16px;line-height:18px;margin-bottom:3px;color:#eaeaea}
        .nsMobileMoreBackdrop{position:fixed;display:flex;visibility:hidden;opacity:0;inset:0;z-index:2147483001;background:rgba(0,0,0,.72);align-items:flex-end;transition:opacity .15s ease}
        .nsMobileMoreBackdrop.open{visibility:visible;opacity:1}
        .nsMobileSheet{width:100%;max-height:78vh;overflow:auto;background:#0d0d0d;border:1px solid #303030;border-radius:18px 18px 0 0;padding:16px 16px calc(20px + env(safe-area-inset-bottom));transform:translateY(12px);transition:transform .15s ease}
        .nsMobileMoreBackdrop.open .nsMobileSheet{transform:translateY(0)}
        .nsMobileSheetHead{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}.nsMobileSheetHead strong{font-size:17px}.nsMobileSheetHead button{border:1px solid #303030;background:#141414;color:#fff;border-radius:8px;padding:7px 10px}
        .nsMobileGrid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.nsMobileGrid a,.nsMobileGrid button{display:block;text-align:left;background:#111;border:1px solid #272727;border-radius:10px;padding:12px;color:#eee!important;text-decoration:none!important;font:650 12px Inter,system-ui,-apple-system,"Segoe UI",sans-serif}
        .nsMobileGrid .wide{grid-column:1/-1}.nsMobileMuted{color:#8f8f8f;font-size:11px;line-height:1.5}
        .nsMobileModal{position:fixed;display:flex;z-index:2147483646;inset:0;background:rgba(0,0,0,.82);align-items:center;justify-content:center;padding:16px}.nsMobileModal[hidden]{display:none}.nsMobileModalCard{width:min(460px,100%);background:#0d0d0d;border:1px solid #303030;border-radius:14px;padding:18px;color:#f4f4f4}.nsMobileModalHead{display:flex;justify-content:space-between;align-items:center}.nsMobileModalHead strong{font-size:18px}.nsMobileModalHead button{font-size:24px;line-height:24px;border:0;background:transparent;color:#ddd}.nsMobileModalCard p,.nsMobileModalCard li{color:#c4c4c4;line-height:1.6}.nsMobileModalCard ol{padding-left:22px}
      }
    `;
    document.head.appendChild(style);

    const current=location.pathname;
    const params=new URLSearchParams(location.search);
    const view=params.get('view');
    const nav=document.createElement('nav');
    nav.id='nsMobileNav';nav.className='nsMobileNav';nav.setAttribute('aria-label','NordicSignal mobilnavigasjon');
    nav.innerHTML=`<a href="/app" class="${(current==='/'||current==='/app'||current==='/index.html')&&!view?'active':''}"><span class="nsMobileNavIcon">⌂</span>Oversikt</a><a href="/holdings" class="${current.includes('holding')?'active':''}"><span class="nsMobileNavIcon">▦</span>Beholdning</a><a href="/app?view=insider" class="${view==='insider'?'active':''}"><span class="nsMobileNavIcon">◎</span>Insider</a><a href="/news" class="${current.includes('news')?'active':''}"><span class="nsMobileNavIcon">◫</span>Nyheter</a><button type="button" id="nsMobileMore"><span class="nsMobileNavIcon">•••</span>Mer</button>`;
    document.body.appendChild(nav);

    const more=document.createElement('div');
    more.id='nsMobileMoreBackdrop';more.className='nsMobileMoreBackdrop';
    more.innerHTML=`<div class="nsMobileSheet"><div class="nsMobileSheetHead"><strong>NordicSignal</strong><button type="button" id="nsMobileMoreClose">Lukk</button></div><div class="nsMobileGrid"><a href="/stock">Stock Intelligence</a><a href="/readiness">Investment Check</a><a href="/app?view=radar">Stock Radar</a><a href="/app?view=watchlist">Watchlist</a><a href="/app?view=short">Short</a><a href="/app?view=markets">Markeder</a><a href="/paper">Paper Trading</a><a href="/calendar">Kalender</a><a href="/development">Development</a><a href="/legal">Vilkår & risiko</a><button type="button" class="wide" id="nsMobileInstall" ${isStandalone()?'hidden':''}>Installer NordicSignal på mobilen</button></div><p class="nsMobileMuted">Live markedsdata og API-kall lagres ikke offline. App-skallet kan åpnes fra hjemskjermen, mens ferske data hentes fra NordicSignal når du er på nett.</p></div>`;
    document.body.appendChild(more);
    const toggle=open=>more.classList.toggle('open',open);
    document.getElementById('nsMobileMore').onclick=()=>toggle(true);
    document.getElementById('nsMobileMoreClose').onclick=()=>toggle(false);
    more.onclick=event=>{if(event.target===more)toggle(false)};
    const install=document.getElementById('nsMobileInstall');
    if(install)install.onclick=installApp;
  }

  registerServiceWorker();
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>{mount();routeRequestedView()},{once:true});
  else{mount();routeRequestedView()}
})();
