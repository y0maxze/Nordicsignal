(function(){
  const isMobile=()=>window.matchMedia('(max-width:900px)').matches;

  function activeKey(){
    const p=location.pathname;
    if(p.startsWith('/morning'))return 'morning';
    if(p.startsWith('/holdings'))return 'portfolio';
    if(p.startsWith('/stock')||p.startsWith('/intelligence')||p.startsWith('/instrument'))return 'search';
    if(new URLSearchParams(location.search).get('view')==='signals')return 'signals';
    return 'home';
  }

  function ensureStyles(){
    if(document.getElementById('nsCanonicalMobileNavStyle'))return;
    const s=document.createElement('style');
    s.id='nsCanonicalMobileNavStyle';
    s.textContent=`
      .nsMobileMoreMenu{display:none}
      @media(max-width:900px){
        html,body{overflow-x:hidden!important}
        body{padding-bottom:calc(76px + env(safe-area-inset-bottom))!important}
        .main{padding-bottom:calc(90px + env(safe-area-inset-bottom))!important}
        .nsMobileNav{display:grid!important;position:fixed!important;z-index:2147483000!important;left:0!important;right:0!important;bottom:0!important;width:100%!important;margin:0!important;grid-template-columns:repeat(6,minmax(0,1fr))!important;padding:6px 6px calc(6px + env(safe-area-inset-bottom))!important;background:var(--surface,#0f0f0f)!important;border:0!important;border-top:1px solid var(--line,#292929)!important;border-radius:0!important;box-shadow:0 -8px 24px rgba(0,0,0,.2)!important;overflow:visible!important;transform:none!important;-webkit-transform:none!important;backdrop-filter:none!important;-webkit-backdrop-filter:none!important;contain:none!important;will-change:auto!important}
        .nsMobileNav a,.nsMobileNav button{min-width:0!important;border:0!important;background:transparent!important;color:var(--m,#9c9c9c)!important;text-decoration:none!important;padding:8px 2px!important;text-align:center!important;font:700 8px Inter,system-ui,-apple-system,"Segoe UI",sans-serif!important;line-height:1.15!important}
        .nsMobileNav a.active{color:var(--t,#f5f5f5)!important;background:var(--surface-2,#151515)!important;border-radius:9px!important}
        .nsMobileNavIcon{display:block!important;font-size:15px!important;line-height:18px!important;margin-bottom:3px!important;color:inherit!important}
        .nsMobileMoreMenu{position:fixed!important;display:grid;z-index:2147483050!important;left:10px!important;right:10px!important;bottom:calc(70px + env(safe-area-inset-bottom))!important;padding:10px!important;background:var(--surface,#0f0f0f)!important;border:1px solid var(--line,#292929)!important;border-radius:14px!important;box-shadow:0 16px 42px rgba(0,0,0,.35)!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:6px!important}
        .nsMobileMoreMenu[hidden]{display:none!important}
        .nsMobileMoreMenu a{padding:11px 12px!important;border-radius:10px!important;text-decoration:none!important;background:var(--surface-2,#151515)!important;color:var(--t,#f5f5f5)!important;font-weight:700!important;font-size:12px!important}
      }
      @media(min-width:901px){.nsMobileNav,.nsMobileMoreMenu{display:none!important}}
    `;
    document.head.appendChild(s);
  }

  function mount(){
    ensureStyles();
    let nav=document.getElementById('nsMobileNav');
    if(!nav){nav=document.createElement('nav');nav.id='nsMobileNav';document.body.appendChild(nav)}
    nav.className='nsMobileNav';
    nav.setAttribute('aria-label','NordicSignal mobilnavigasjon');
    const key=activeKey(),cls=name=>key===name?' class="active"':'';
    nav.innerHTML=`<a href="/mobile"${cls('home')}><span class="nsMobileNavIcon">⌂</span>Hjem</a><a href="/morning"${cls('morning')}><span class="nsMobileNavIcon">☀</span>Før børs</a><a href="/app?view=signals"${cls('signals')}><span class="nsMobileNavIcon">↗</span>Signaler</a><a href="/holdings"${cls('portfolio')}><span class="nsMobileNavIcon">◇</span>Portefølje</a><a href="/stock"${cls('search')}><span class="nsMobileNavIcon">⌕</span>Søk</a><button id="nsMobileMoreToggle" type="button" aria-expanded="false"><span class="nsMobileNavIcon">•••</span>Mer</button>`;

    let menu=document.getElementById('nsMobileMoreMenu');
    if(!menu){menu=document.createElement('div');menu.id='nsMobileMoreMenu';menu.className='nsMobileMoreMenu';document.body.appendChild(menu)}
    menu.className='nsMobileMoreMenu';menu.hidden=true;
    menu.innerHTML='<a href="/alerts">Varsler</a><a href="/ipo-radar">IPO Radar</a><a href="/learning">Historikk</a><a href="/calendar">Kalender</a><a href="/readiness">Sjekkliste</a><a href="/development">System</a><a href="/legal">Vilkår & risiko</a>';

    const more=document.getElementById('nsMobileMoreToggle');
    more.onclick=()=>{const next=menu.hidden;menu.hidden=!next;more.setAttribute('aria-expanded',String(next))};
    document.addEventListener('click',event=>{if(menu.hidden)return;if(nav.contains(event.target)||menu.contains(event.target))return;menu.hidden=true;more.setAttribute('aria-expanded','false')},{passive:true});
    window.addEventListener('pagehide',()=>{menu.hidden=true},{once:true});
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
})();
