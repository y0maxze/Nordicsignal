(()=>{
  const esc=v=>String(v??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));
  const names=list=>(list||[]).length?(list||[]).map(esc).join(', '):'Ingen';
  function render(data){
    const root=document.getElementById('content');
    if(!root||!data||document.getElementById('shadowFailureStreakPanel'))return;
    const persistent=data.persistent_tickers||[];
    const state=String(data.operational_status||'PASS');
    const details=persistent.length?persistent.map(item=>`${esc(item.ticker)} ${Number(item.consecutive_failures||0)}× (${esc(item.latest_outcome||'')})`).join(' · '):'Ingen gjentakende feil';
    const panel=document.createElement('section');
    panel.className='section';
    panel.id='shadowFailureStreakPanel';
    panel.innerHTML=`
      <div class="sectionHead">
        <div><h2>Vedvarende scan-feil</h2><div class="sub">Skiller tilfeldige provider-glipp fra tickere som feiler flere scans på rad.</div></div>
        <span class="pill ${state==='PASS'?'ready':'muted'}">${esc(state)}</span>
      </div>
      <div class="qualityGrid">
        <div class="qualityCheck"><span class="eyebrow">WARN · 2 på rad</span><b>${(data.warn_tickers||[]).length}</b><small>${names(data.warn_tickers)}</small></div>
        <div class="qualityCheck"><span class="eyebrow">FAIL · 3+ på rad</span><b>${(data.fail_tickers||[]).length}</b><small>${names(data.fail_tickers)}</small></div>
        <div class="qualityCheck"><span class="eyebrow">Transient · 1 feil</span><b>${(data.transient_tickers||[]).length}</b><small>${names(data.transient_tickers)}</small></div>
        <div class="qualityCheck"><span class="eyebrow">Historikk</span><b>${Number(data.completed_runs_evaluated||0)} scans</b><small>Suksess nullstiller streaken.</small></div>
      </div>
      <div class="notice">${details}. <strong>Ingen ticker deaktiveres automatisk.</strong></div>`;
    const audit=document.getElementById('shadowScanAuditPanel');
    if(audit)audit.insertAdjacentElement('afterend',panel);else root.appendChild(panel);
  }
  fetch('/api/opportunity-shadow/failure-streaks',{cache:'no-store'}).then(r=>r.ok?r.json():null).then(render).catch(()=>{});
})();
