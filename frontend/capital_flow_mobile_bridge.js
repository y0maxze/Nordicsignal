(function(){
  const ENABLED='ns-mobile-alerts-v1';
  const SEEN='ns-capital-flow-alert-seen-v1';
  let timer=null;

  function mountLink(){
    const nav=document.getElementById('nsMobileNav');
    if(!nav)return false;
    if(nav.querySelector('a[href="/capital-flow"]'))return true;
    const links=[...nav.querySelectorAll('a')];
    const learning=links.find(a=>a.getAttribute('href')==='/learning');
    const target=learning||links[links.length-2];
    if(!target)return false;
    target.href='/capital-flow';
    target.innerHTML='<span class="nsMobileNavIcon">⇄</span>Kapitalflyt';
    target.classList.toggle('active',location.pathname.startsWith('/capital-flow'));
    return true;
  }

  function readSeen(){try{return new Set(JSON.parse(localStorage.getItem(SEEN)||'[]'))}catch{return new Set()}}
  function saveSeen(set){try{localStorage.setItem(SEEN,JSON.stringify([...set].slice(-300)))}catch{}}
  function id(row){return String(row.fingerprint||[row.event_type,row.ticker,row.event_at,row.title].join('|'));}
  async function show(row){
    const ticker=row.ticker||row.instrument_name||'NordicSignal';
    const direction=row.direction==='buy'?'Kjøp':row.direction==='sell'?'Salg':'Eierendring';
    const body=[direction,row.actor,row.evidence_level==='verified'?'verifisert':'rapportert'].filter(Boolean).join(' · ');
    const url=row.ticker?`/capital-flow?ticker=${encodeURIComponent(row.ticker)}`:'/capital-flow';
    try{const reg=await navigator.serviceWorker.ready;await reg.showNotification(`${ticker} · Ny kapitalbevegelse`,{body,tag:`capital-flow:${id(row)}`,data:{url}})}catch{try{new Notification(`${ticker} · Ny kapitalbevegelse`,{body,tag:`capital-flow:${id(row)}`})}catch{}}
  }
  async function poll({baseline=false}={}){
    if(localStorage.getItem(ENABLED)!=='1'||typeof Notification==='undefined'||Notification.permission!=='granted')return;
    try{
      const r=await fetch('/api/capital-flow?state=NEW&limit=40',{cache:'no-store'});if(!r.ok)return;
      const data=await r.json(),rows=(data.items||[]).filter(x=>x.alert_eligible);
      const seen=readSeen();
      if(baseline||seen.size===0){rows.forEach(x=>seen.add(id(x)));saveSeen(seen);return}
      const fresh=rows.filter(x=>!seen.has(id(x)));
      for(const row of fresh.slice(0,4)){seen.add(id(row));await show(row)}
      rows.forEach(x=>seen.add(id(x)));saveSeen(seen);
    }catch{}
  }
  function start(){
    let tries=0;const mount=()=>{if(!mountLink()&&tries++<20)setTimeout(mount,100)};mount();
    poll({baseline:false});if(timer)clearInterval(timer);timer=setInterval(()=>poll(),120000);
    document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'){mountLink();poll()}},{passive:true});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
