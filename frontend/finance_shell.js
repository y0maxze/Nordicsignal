/* Shared presentation only. No API calls or model changes. */
(function(){
  function install(){
    if(document.getElementById('aksjerHeader'))return;
    const root=document.documentElement;
    root.classList.add('aksjerFinance');
    const path=location.pathname;
    const stock=path.startsWith('/stock');
    const morning=path.startsWith('/morning');
    const alerts=path.startsWith('/alerts')||path.startsWith('/notifications');
    const market=!stock&&!morning&&!alerts;
    const densityKey='aksjer-table-density';
    try{root.dataset.density=localStorage.getItem(densityKey)==='compact'?'compact':'normal'}catch{root.dataset.density='normal'}
    const header=document.createElement('header');header.id='aksjerHeader';
    header.innerHTML=`<div class="aksjerHeaderInner"><a class="aksjerBrand" href="/app" aria-label="Aksjer – til Marked"><img src="/aksjer-mark.svg" width="28" height="28" alt="">Aksjer</a><nav class="aksjerPrimary" aria-label="Hovedmeny"><a href="/app"${market?' aria-current="page"':''}>Marked</a><a href="/morning"${morning?' aria-current="page"':''}>Før børs</a></nav><div class="aksjerActions"><a id="aksjerAlerts" href="/alerts" aria-label="Åpne varsler"${alerts?' aria-current="page"':''}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></svg><span>Varsler</span></a><button class="nsThemeToggle" data-ns-theme-toggle type="button" aria-label="Bytt tema">☀︎</button><details id="aksjerMenu"><summary aria-label="Åpne meny"><svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M2 5h16M2 10h16M2 15h16"/></svg>Meny</summary><div class="aksjerMenuPanel"><p class="aksjerMenuLabel">Navigasjon</p><nav aria-label="Alle sider"><a href="/app">Marked <span>Rangering og aksjesøk</span></a><a href="/morning">Før børs <span>Prioriterte hendelser</span></a><a href="/alerts">Varsler <span>Registrerte signalhendelser</span></a><a href="/app?filter=ipo">Nye/IPO <span>Kommende og nylige noteringer</span></a></nav><p class="aksjerMenuLabel">Visning</p><button id="aksjerDensity" type="button" aria-pressed="false">Tettere markedstabell <span>Av</span></button><details class="aksjerDataInfo"><summary>Om data og signaler</summary><p>Kurs kan være forsinket eller lagret. Se tidspunkt og datastatus på aksjen.</p><p>Score er rangering, ikke en kjøpsanbefaling. Opportunity er en separat modell. Early Discovery og IPO er forskning uten score-effekt.</p><p>Eier/Insider viser verifiserte insideropplysninger. Ingen daglig komplett eierfeed er tilkoblet.</p></details></div></details></div></div>`;
    document.body.prepend(header);
    document.querySelectorAll('.nsUtilityBar,.nsGlobalHome,.top>.nsThemeToggle').forEach(el=>el.remove());
    if(window.NordicSignalTheme)window.NordicSignalTheme.apply(window.NordicSignalTheme.current());
    const menu=document.getElementById('aksjerMenu'),summary=menu.querySelector('summary');
    const syncMenu=()=>summary.setAttribute('aria-expanded',String(menu.open));
    syncMenu();menu.addEventListener('toggle',syncMenu);
    document.addEventListener('click',event=>{if(!menu.contains(event.target))menu.open=false});
    document.addEventListener('keydown',event=>{if(event.key==='Escape'&&menu.open){menu.open=false;summary.focus()}});
    menu.querySelectorAll('a').forEach(link=>link.addEventListener('click',()=>{menu.open=false}));
    const density=document.getElementById('aksjerDensity');
    function syncDensity(){const compact=root.dataset.density==='compact';density.setAttribute('aria-pressed',String(compact));density.querySelector('span').textContent=compact?'På':'Av'}
    syncDensity();density.addEventListener('click',()=>{root.dataset.density=root.dataset.density==='compact'?'normal':'compact';try{localStorage.setItem(densityKey,root.dataset.density)}catch{}syncDensity()});
    if(stock){
      const top=document.querySelector('main>.top');
      if(top){const rail=document.createElement('nav');rail.className='aksjerStockSections';rail.setAttribute('aria-label','Gå til del av analysen');rail.innerHTML=[['whyFollow','Oversikt'],['chartSection','Kurs'],['fundamentalSection','Regnskap'],['newsSection','Nyheter'],['insiderSection','Insider'],['nsSignalEvidence','Historikk'],['whatNow','Hva skjer nå?']].map(([id,label])=>`<a href="#${id}">${label}</a>`).join('');top.after(rail)}
    }
    const search=document.getElementById('search');if(search){search.placeholder='Søk aksje eller ticker';search.setAttribute('type','search')}
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
