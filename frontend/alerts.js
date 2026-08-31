(()=>{
  const list=document.getElementById('alertList'),summary=document.getElementById('summary'),unread=document.getElementById('unreadCount'),filters=document.getElementById('filters'),markAll=document.getElementById('markAll');
  let active='ALL',items=[];
  const esc=v=>String(v??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));
  const typeName=t=>({INSIDER:'Insider',OPPORTUNITY:'Opportunity',ACTIVITY:'Aktivitet',TREND:'Trend',SIGNAL:'Signal',SHORT:'Short',OTHER:'Annet'}[t]||t||'Varsel');
  function ago(value){const d=new Date(value);if(Number.isNaN(d.getTime()))return '';const sec=Math.max(0,(Date.now()-d.getTime())/1000);if(sec<60)return 'nå';if(sec<3600)return `${Math.floor(sec/60)} min siden`;if(sec<86400)return `${Math.floor(sec/3600)} t siden`;if(sec<604800)return `${Math.floor(sec/86400)} d siden`;return d.toLocaleDateString('no-NO',{day:'numeric',month:'short'});}
  function render(){
    const visible=active==='ALL'?items:items.filter(x=>x.alert_type===active);
    if(!visible.length){list.innerHTML='<div class="empty">Ingen varsler i denne kategorien ennå.</div>';return}
    list.innerHTML=visible.map(x=>`<a class="alertCard ${x.read_at?'':'unread'}" href="${esc(x.url||'/alerts')}" data-id="${Number(x.id)}"><div class="alertTop"><span class="dot"></span><span class="type">${esc(typeName(x.alert_type))}</span><span class="time">${esc(ago(x.source_created_at))}</span></div><h2 class="alertTitle">${esc(x.title)}</h2><p class="alertBody">${esc(x.body)}</p>${x.ticker?`<span class="ticker">${esc(x.ticker)}</span>`:''}</a>`).join('');
    list.querySelectorAll('.alertCard').forEach(card=>card.addEventListener('click',()=>{fetch(`/api/alerts/${card.dataset.id}/read`,{method:'POST',cache:'no-store',keepalive:true}).catch(()=>{})}));
  }
  async function load(){
    try{const r=await fetch('/api/alerts?limit=200',{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);const data=await r.json();items=data.items||[];unread.textContent=String(data.unread||0);summary.textContent=`${data.total||0} varsler · ${data.unread||0} ulest`;render()}
    catch(e){list.innerHTML='<div class="error">Kunne ikke hente varselhistorikken akkurat nå.</div>';summary.textContent='Tilkoblingsfeil'}
  }
  filters.addEventListener('click',e=>{const b=e.target.closest('[data-type]');if(!b)return;active=b.dataset.type;filters.querySelectorAll('.filter').forEach(x=>x.classList.toggle('active',x===b));render()});
  markAll.addEventListener('click',async()=>{markAll.disabled=true;try{await fetch('/api/alerts/read-all',{method:'POST',cache:'no-store'});items=items.map(x=>({...x,read_at:x.read_at||new Date().toISOString()}));unread.textContent='0';summary.textContent=`${items.length} varsler · 0 ulest`;render()}finally{markAll.disabled=false}});
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')load()});
  load();
})();
