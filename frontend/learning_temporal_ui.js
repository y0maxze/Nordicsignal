(()=>{
  const esc=v=>String(v??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));
  const fmt=v=>Number(v||0).toLocaleString('no-NO');
  const fmt1=v=>v==null?'—':Number(v).toLocaleString('no-NO',{maximumFractionDigits:1});
  const pill=s=>s==='PASS'?'ready':'';
  function card(h,item){
    const status=String(item?.status||'COLLECTING_DATA');
    return `<div class="qualityCheck"><span class="pill ${pill(status)}">${esc(status.replaceAll('_',' '))}</span><b>${h}d · ${fmt(item?.observations)} obs</b><small>${fmt(item?.unique_event_days)} unike signaldager · ${fmt(item?.calendar_span_days)} kalenderdager spenn.<br>Største enkeltdag ${fmt1(item?.largest_single_day_share_pct)} % · største 7-dagersklynge ${fmt1(item?.largest_cluster_window_share_pct)} %.</small></div>`;
  }
  function render(data){
    const gate=data?.temporal_independence_gate,root=document.getElementById('content');
    if(!gate||!root||document.getElementById('temporalIndependencePanel'))return;
    const status=String(gate.status||'COLLECTING_DATA'),h=gate.horizons||{},criteria=gate.criteria||{},panel=document.createElement('section');
    panel.className='section';panel.id='temporalIndependencePanel';
    panel.innerHTML=`<div class="sectionHead"><div><h2>Temporal independence</h2><div class="sub">Kontrollerer at mange signaler fra samme børsuke eller markedsrally ikke telles som like mange uavhengige bevis.</div></div><span class="pill ${pill(status)}">${esc(status)}</span></div><div class="qualityGrid">${[5,10,20].map(x=>card(x,h[String(x)]||{})).join('')}</div><div class="notice">Krav per horisont: minst <strong>${fmt(criteria.minimum_unique_event_days||8)}</strong> unike signaldager over minst <strong>${fmt(criteria.minimum_calendar_span_days||30)}</strong> kalenderdager. Maks ${fmt1(criteria.maximum_single_event_day_share_pct||25)} % fra én dag og maks ${fmt1(criteria.maximum_cluster_window_share_pct||50)} % i et ${fmt(criteria.cluster_window_calendar_days||7)}-dagersvindu. <strong>Ingen score eller live-terskel endres.</strong></div>`;
    const wf=document.getElementById('walkForwardPanel'),stat=document.getElementById('statisticalConfidencePanel');
    if(wf)wf.insertAdjacentElement('afterend',panel);else if(stat)stat.insertAdjacentElement('afterend',panel);else root.prepend(panel);
  }
  fetch('/api/opportunity-performance?limit=100',{cache:'no-store'}).then(r=>r.ok?r.json():null).then(render).catch(()=>{});
})();
