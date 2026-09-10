(function(){
  const ENABLED='ns-mobile-alerts-v1';
  const SEEN='ns-capital-flow-alert-seen-v1';
  let timer=null;

  function mountCapitalFlowNav(){
    const nav=document.getElementById('nsMobileNav');
    if(!nav)return false;
    let link=nav.querySelector('a[href="/capital-flow"]');
    if(!link){
      link=nav.querySelector('a[href="/learning"]');
      if(link){
        link.href='/capital-flow';
        link.innerHTML='<span class="nsMobileNavIcon">⇄</span>Kapitalflyt';
      }else{
        const news=nav.querySelector('a[href="/news"]');
        link=document.createElement('a');
        link.href='/capital-flow';
        link.innerHTML='<span class="nsMobileNavIcon">⇄</span>Kapitalflyt';
        if(news)nav.insertBefore(link,news);else nav.appendChild(link);
      }
    }
    link.classList.toggle('active',location.pathname.startsWith('/capital-flow'));
    return true;
  }

  function readSeen(){try{return new Set(JSON.parse(localStorage.getItem(SEEN)||'[]'))}catch{return new Set()}}
  function saveSeen(set){try{localStorage.setItem(SEEN,JSON.stringify([...set].slice(-300)))}catch{}}
  function eventId(row){return String(row.fingerprint||[row.event_type,row.ticker,row.event_at,row.title].join('|'))}
  async function show(row){
    const ticker=row.ticker||row.instrument_name||'NordicSignal';
    const direction=row.direction==='buy'?'Kjøp':row.direction==='sell'?'Salg':'Eierendring';
    const body=[direction,row.actor,row.evidence_level==='verified'?'verifisert':'rapportert'].filter(Boolean).join(' · ');
    const url=row.ticker?`/capital-flow?ticker=${encodeURIComponent(row.ticker)}`:'/capital-flow';
    try{const reg=await navigator.serviceWorker.ready;await reg.showNotification(`${ticker} · Ny kapitalbevegelse`,{body,tag:`capital-flow:${eventId(row)}`,data:{url}})}catch{try{new Notification(`${ticker} · Ny kapitalbevegelse`,{body,tag:`capital-flow:${eventId(row)}`})}catch{}}
  }
  async function poll({baseline=false}={}){
    if(localStorage.getItem(ENABLED)!=='1'||typeof Notification==='undefined'||Notification.permission!=='granted')return;
    try{
      const response=await fetch('/api/capital-flow?state=NEW&limit=40',{cache:'no-store'});
      if(!response.ok)return;
      const data=await response.json();
      const rows=(data.items||[]).filter(row=>row.alert_eligible);
      const seen=readSeen();
      if(baseline||seen.size===0){rows.forEach(row=>seen.add(eventId(row)));saveSeen(seen);return}
      for(const row of rows.filter(row=>!seen.has(eventId(row))).slice(0,4)){seen.add(eventId(row));await show(row)}
      rows.forEach(row=>seen.add(eventId(row)));saveSeen(seen);
    }catch{}
  }
  function start(){
    let tries=0;
    const mount=()=>{if(!mountCapitalFlowNav()&&tries++<20)setTimeout(mount,100)};
    setTimeout(mount,0);
    poll();
    timer=setInterval(()=>poll(),120000);
    document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'){mountCapitalFlowNav();poll()}},{passive:true});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
