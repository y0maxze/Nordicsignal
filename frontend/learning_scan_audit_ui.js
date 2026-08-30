(()=>{
  const esc=value=>String(value??'').replace(/[&<>\"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[char]));
  const fmt=value=>Number(value||0).toLocaleString('no-NO');
  const pct=value=>`${Number(value||0).toLocaleString('no-NO',{maximumFractionDigits:1})}%`;
  const names=list=>(list||[]).length?(list||[]).map(esc).join(', '):'Ingen';

  function render(data){
    const root=document.getElementById('content');
    if(!root||!data||document.getElementById('shadowScanAuditPanel'))return;
    const latest=data.latest_run||{};
    const repair=data.bounded_repair||{};
    const state=String(data.operational_status||'COLLECTING_DATA');
    const panel=document.createElement('section');
    panel.className='section';
    panel.id='shadowScanAuditPanel';
    panel.innerHTML=`
      <div class="sectionHead">
        <div><h2>Shadow scan audit</h2><div class="sub">Per-ticker kontroll av siste komplette Opportunity-scan med maksimalt én avgrenset repair.</div></div>
        <span class="pill ${state==='PASS'?'ready':'muted'}">${esc(state.replaceAll('_',' '))}</span>
      </div>
      <div class="qualityGrid">
        <div class="qualityCheck"><span class="eyebrow">Snapshot-dekning</span><b>${pct(latest.snapshot_coverage_pct)}</b><small>${fmt(latest.snapshot_present)} / ${fmt(latest.expected_tickers)} forventede tickere.</small></div>
        <div class="qualityCheck"><span class="eyebrow">Ikke kjørt</span><b>${fmt((data.missing_tickers||[]).length)}</b><small>${names(data.missing_tickers)}</small></div>
        <div class="qualityCheck"><span class="eyebrow">Scan/result-feil</span><b>${fmt((data.failed_tickers||[]).length)}</b><small>${names(data.failed_tickers)}</small></div>
        <div class="qualityCheck"><span class="eyebrow">Snapshot mangler</span><b>${fmt((data.snapshot_missing_tickers||[]).length)}</b><small>${names(data.snapshot_missing_tickers)}</small></div>
      </div>
      <div class="qualityGrid">
        <div class="qualityCheck"><span class="eyebrow">Bounded repair</span><b>${fmt(repair.successes)} / ${fmt(repair.attempts)} reparert</b><small>${fmt(repair.failures)} repair-forsøk feilet. Maks én live-retry per feilet ticker.</small></div>
      </div>
      <div class="notice">Siste audited run: <strong>${esc(latest.completed_at||latest.started_at||'ingen ennå')}</strong>. Vellykkede tickere kalkuleres aldri på nytt av repair-laget. Snapshot-repair lagrer bare det allerede beregnede resultatet. Dette påvirker ikke live-score, Opportunity-labels eller terskler.</div>`;
    const shadow=document.getElementById('shadowDatasetPanel');
    if(shadow)shadow.insertAdjacentElement('afterend',panel);else root.appendChild(panel);
  }

  async function load(){
    try{
      const response=await fetch('/api/opportunity-shadow/scan-audit',{cache:'no-store'});
      if(response.ok)render(await response.json());
    }catch(_error){}
  }
  load();
})();
