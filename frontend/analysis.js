(function(){
  function cleanTicker(value){return String(value||'').trim().toUpperCase().replace(/\.OL$/,'')}
  window.showStock=function(ticker){
    const t=cleanTicker(ticker);if(!t)return;
    location.href='/stock?ticker='+encodeURIComponent(t);
  };

  function cleanNavigation(){
    const labels={Dashboard:'Min oversikt','Insider Activity':'Insider','Short Radar':'Short',Markets:'Markeder'};
    document.querySelectorAll('#nav a[data-page]').forEach(a=>{const key=a.dataset.page;if(labels[key])a.textContent=labels[key]});
    const byHref={'/stock':'Stock Intelligence','/paper':'Paper Trading','/news':'Nyheter','/calendar':'Kalender'};
    document.querySelectorAll('#nav a[href]').forEach(a=>{const href=a.getAttribute('href');if(byHref[href])a.textContent=byHref[href]});
    const logo=document.querySelector('.side .logo');
    if(logo&&!logo.dataset.homeReady){logo.dataset.homeReady='1';logo.style.cursor='pointer';logo.title='Til Min oversikt';logo.tabIndex=0;logo.setAttribute('role','link');const go=()=>{const d=document.querySelector('#nav a[data-page="Dashboard"]');if(d)d.click();else location.href='/app'};logo.onclick=go;logo.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go()}}}
  }

  cleanNavigation();
  function load(src){return new Promise((resolve,reject)=>{const s=document.createElement('script');s.src=src;s.async=true;s.onload=resolve;s.onerror=reject;document.body.appendChild(s)})}

  // Home dashboard is the critical path. Load it first instead of making the user
  // wait for Stock Radar/Insider enhancements that are only needed after navigation.
  load('/portfolio_dashboard.js').catch(console.error).finally(()=>{
    const loadSecondary=()=>load('/dashboard_enhancements.js')
      .catch(console.error)
      .finally(()=>load('/dashboard_performance.js').catch(console.error))
      .finally(()=>load('/insider_clean_ui.js').catch(console.error));
    if('requestIdleCallback' in window)requestIdleCallback(loadSecondary,{timeout:900});
    else setTimeout(loadSecondary,120);
  });
})();
