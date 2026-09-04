(function(){
  const path=location.pathname;

  function addStyles(){
    if(document.getElementById('nsUiShellStyles'))return;
    const s=document.createElement('style');s.id='nsUiShellStyles';s.textContent=`
      .nsOpportunityMetric,.nsOpportunityReason,.nsEvidenceMetric{background:var(--surface-2,#151515)!important;border-color:var(--line,#292929)!important}.nsReadyBrief{color:var(--t,#f5f5f5)!important}.nsOppWatch,.nsEvidenceWarn{color:var(--y,#e6b94b)!important}
      .nsMobileNav .nsMobileMoreToggle{border:0;background:transparent;color:var(--m,#9c9c9c);padding:10px 2px 9px;text-align:center;font:700 9px Inter,system-ui,-apple-system,"Segoe UI",sans-serif;cursor:pointer}.nsMobileNav .nsMobileMoreToggle .nsMobileNavIcon{display:block;font-size:16px;line-height:18px;margin-bottom:3px;color:var(--t,#eaeaea)}
      .nsMobileMoreMenu{position:fixed;z-index:2147483050;left:12px;right:12px;bottom:88px;padding:10px;background:var(--surface,#0f0f0f);border:1px solid var(--line,#292929);border-radius:16px;box-shadow:var(--shadow,0 18px 42px rgba(0,0,0,.45));display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}.nsMobileMoreMenu[hidden]{display:none}.nsMobileMoreMenu a{padding:11px 12px;border-radius:10px;text-decoration:none!important;background:var(--surface-2,#151515);color:var(--t,#f5f5f5)!important;font-weight:700;font-size:12px}
      @media(max-width:900px){.nsMobileNav{grid-template-columns:repeat(5,1fr)!important}.nsMobileNav a,.nsMobileNav .nsMobileMoreToggle{font-size:9px!important}.nsAlertShortcut{bottom:96px!important}.top{align-items:center!important}.top>.nsThemeToggle{display:inline-grid!important;place-items:center!important}}
      @media(min-width:901px){.nsMobileMoreMenu{display:none!important}}
    `;document.head.appendChild(s);
  }

  function themeButton(slot){return `<button class="nsThemeToggle" data-ns-theme-toggle data-slot="${slot}" type="button" aria-label="Bytt tema">☀︎</button>`;}

  function installGlobalNav(){
    const side=document.querySelector('.side');const nav=side&&side.querySelector('nav');if(!side||!nav||nav.dataset.nsSimplified==='1')return;
    nav.dataset.nsSimplified='1';nav.innerHTML=`<a href="/app" data-ns-nav="home">Hjem</a><a href="/app?view=signals" data-ns-nav="signals">Signaler</a><a href="/holdings" data-ns-nav="portfolio">Portefølje</a><a href="/stock" data-ns-nav="search">Søk</a><button class="nsMoreToggle" type="button" aria-expanded="false">Mer</button><div class="nsMoreMenu" hidden><a href="/alerts">Varsler</a><a href="/learning">Historikk</a><a href="/calendar">Kalender</a><a href="/readiness">Sjekkliste</a><a href="/development">System</a><a href="/legal">Vilkår & risiko</a></div>`;
    if(!side.querySelector('.nsSideFooter'))side.insertAdjacentHTML('beforeend',`<div class="nsSideFooter"><span>NordicSignal</span>${themeButton('side')}</div>`);
    const more=nav.querySelector('.nsMoreToggle'),menu=nav.querySelector('.nsMoreMenu');more&&more.addEventListener('click',()=>{const open=more.getAttribute('aria-expanded')==='true';more.setAttribute('aria-expanded',String(!open));menu.hidden=open;});
    const active=path.startsWith('/holdings')?'portfolio':path.startsWith('/stock')||path.startsWith('/intelligence')||path.startsWith('/instrument')?'search':location.search.includes('view=signals')?'signals':'home';nav.querySelector(`[data-ns-nav="${active}"]`)?.classList.add('active');
  }

  function installTopTheme(){
    if(document.querySelector('[data-slot="top"]'))return;const top=document.querySelector('.top');if(top)top.insertAdjacentHTML('beforeend',themeButton('top'));else document.body.insertAdjacentHTML('afterbegin',`<div class="nsFloatingTheme">${themeButton('top')}</div>`);
  }

  function installMobileNav(){
    const nav=document.getElementById('nsMobileNav');if(!nav||nav.dataset.nsSimplified==='1')return;nav.dataset.nsSimplified='1';
    nav.innerHTML=`<a href="/mobile"><span class="nsMobileNavIcon">⌂</span>Hjem</a><a href="/app?view=signals"><span class="nsMobileNavIcon">↗</span>Signaler</a><a href="/holdings"><span class="nsMobileNavIcon">◇</span>Portefølje</a><a href="/stock"><span class="nsMobileNavIcon">⌕</span>Søk</a><button class="nsMobileMoreToggle" type="button"><span class="nsMobileNavIcon">•••</span>Mer</button>`;
    if(!document.getElementById('nsMobileMoreMenu'))document.body.insertAdjacentHTML('beforeend','<div id="nsMobileMoreMenu" class="nsMobileMoreMenu" hidden><a href="/alerts">Varsler</a><a href="/learning">Historikk</a><a href="/calendar">Kalender</a><a href="/readiness">Sjekkliste</a><a href="/development">System</a><a href="/legal">Vilkår & risiko</a></div>');
    const btn=nav.querySelector('.nsMobileMoreToggle'),menu=document.getElementById('nsMobileMoreMenu');btn&&btn.addEventListener('click',()=>{menu.hidden=!menu.hidden;});
  }

  function activateSignalsView(){
    if(path!=='/app'&&path!=='/'&&path!=='/dashboard')return;if(new URLSearchParams(location.search).get('view')!=='signals')return;
    let tries=0;const run=()=>{if(typeof window.renderRadar==='function'){window.renderRadar();return true;}if(tries++<20)setTimeout(run,100);return false;};run();setTimeout(()=>{if(typeof window.renderRadar==='function')window.renderRadar();},900);
  }

  const TOOL_ORDER=['overview','opportunity','readiness','pressure','insider','news','reports','dividend','short','evidence','backtest','paper'];
  const TOOL_LABELS={overview:'Oversikt',opportunity:'Signal',readiness:'Analyse',pressure:'Marked',insider:'Insider',news:'Nyheter',reports:'Rapporter',dividend:'Utbytte',short:'Short',evidence:'Historikk',backtest:'Backtest',paper:'Paper'};
  function organizeStockTools(){
    if(!path.startsWith('/stock'))return;const tabs=document.querySelector('.tabs');if(!tabs)return;tabs.classList.add('nsToolRail');
    if(!document.querySelector('.nsToolHeader'))tabs.insertAdjacentHTML('beforebegin','<div class="nsToolHeader"><div><span class="muted">VERKTØY</span><h2>Analyser valgt aksje</h2></div><span class="muted">Velg verktøy uten å forlate aksjen</span></div>');
    [...tabs.querySelectorAll('[data-tab]')].forEach(btn=>{const key=btn.dataset.tab;if(TOOL_LABELS[key])btn.textContent=TOOL_LABELS[key];});TOOL_ORDER.forEach(key=>{const btn=tabs.querySelector(`[data-tab="${key}"]`);if(btn)tabs.appendChild(btn);});
    const title=document.querySelector('.top .muted');if(title)title.textContent='NORDICSIGNAL · AKSJE';const name=document.getElementById('name')?.textContent;if(name&&name!=='Loading…')document.title=name+' · NordicSignal';
  }

  function stockObserver(){if(!path.startsWith('/stock'))return;organizeStockTools();const tabs=document.querySelector('.tabs');if(!tabs)return;new MutationObserver(()=>organizeStockTools()).observe(tabs,{childList:true,subtree:false});}

  function renamePlainLanguage(){
    const map={'Market Dashboard':'Oversikt','Live signal-driven stock intelligence':'Det viktigste først. Åpne en aksje for alle verktøy.','Stock Radar':'Signaler','Watchlist':'Følger','Insider Activity':'Insider','Short Radar':'Short','Stock Intelligence':'Aksjeanalyse','Signal Performance':'Historikk','Investment Check':'Sjekkliste'};
    document.querySelectorAll('h1,h2,.sub,.label').forEach(el=>{const text=el.textContent.trim();if(map[text])el.textContent=map[text];});
  }

  function install(){addStyles();installGlobalNav();installTopTheme();activateSignalsView();stockObserver();renamePlainLanguage();setTimeout(installMobileNav,50);}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install);else install();setTimeout(installMobileNav,300);setTimeout(organizeStockTools,250);setTimeout(organizeStockTools,900);setTimeout(renamePlainLanguage,350);
})();
