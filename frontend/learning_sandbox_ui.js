(()=>{
  const esc=value=>String(value??'').replace(/[&<>\"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[char]));
  const fmt=value=>Number(value||0).toLocaleString('no-NO');
  const fmtPct=value=>value==null?'—':`${Number(value).toLocaleString('no-NO',{maximumFractionDigits:1})}%`;
  const short=value=>value?String(value).slice(0,12):'—';
  const pillClass=status=>status==='OPEN_RESEARCH_ONLY'?'ready':'muted';

  function metric(item){
    const raw=item?.raw_return||{};
    const alpha=item?.market_adjusted_alpha||{};
    return `n=${fmt(raw.n)} · median ${fmtPct(raw.median_pct)} · alpha ${fmtPct(alpha.median_pct)} · positiv ${fmtPct(raw.positive_rate_pct)}`;
  }

  function provenanceCards(data){
    const p=data.research_provenance||{};
    return `<div class="qualityGrid">
      <div class="qualityCheck"><span class="eyebrow">Audit-versjon</span><b>${esc(p.version||'—')}</b><small>Modell ${esc(short(p.signal_model_id))}</small></div>
      <div class="qualityCheck"><span class="eyebrow">Kandidat-fingerprint</span><b>${esc(short(p.candidate_set_fingerprint))}</b><small>Endres hvis det pre-registrerte kandidatsettet endres.</small></div>
      <div class="qualityCheck"><span class="eyebrow">Dataset-fingerprint</span><b>${esc(short(p.dataset_fingerprint))}</b><small>${p.reproducible?`${fmt(p.snapshot_count)} snapshots · ${fmt(p.return_count)} outcomes`:'Låst til quality gate PASS.'}</small></div>
      <div class="qualityCheck"><span class="eyebrow">Report-fingerprint</span><b>${esc(short(p.report_fingerprint))}</b><small>${p.reproducible?'Reproduserbar research-identitet.':'Ikke utstedt mens sandbox er låst.'}</small></div>
    </div>`;
  }

  function render(data){
    const root=document.getElementById('content');
    if(!root||!data||document.getElementById('counterfactualSandboxPanel'))return;
    const status=String(data.status||'LOCKED');
    const panel=document.createElement('section');
    panel.className='section';
    panel.id='counterfactualSandboxPanel';
    let body='';
    if(status==='OPEN_RESEARCH_ONLY'){
      const rows=(data.results||[]).map(result=>{
        const candidate=result.candidate||{};
        const holdout=result.holdout||{};
        return `<div class="qualityCheck"><span class="eyebrow">${esc(candidate.name||candidate.id||'Kandidat')}</span><b>${fmt(result.holdout_selected)} holdout-snapshots</b><small>${esc(candidate.description||'')}<br>5d: ${esc(metric(holdout['5']))}<br>10d: ${esc(metric(holdout['10']))}<br>20d: ${esc(metric(holdout['20']))}</small></div>`;
      }).join('');
      body=`${provenanceCards(data)}<div class="qualityGrid">${rows}</div><div class="notice">Development til <strong>${esc(data.development_end||'—')}</strong> · holdout fra <strong>${esc(data.holdout_start||'—')}</strong>. Full SHA-256 audit-identitet ligger i API-responsen. Ingen automatisk rangering, anbefaling eller terskelendring.</div>`;
    }else{
      const gate=data.quality_gate||{};
      body=`${provenanceCards(data)}<div class="qualityGrid"><div class="qualityCheck"><span class="eyebrow">Lås</span><b>Shadow quality må PASS</b><small>${fmt(gate.market_days)} / ${fmt(gate.thresholds?.minimum_market_days||40)} markedsdager samlet. Sandbox leser ikke forskningsradene før gaten åpner.</small></div><div class="qualityCheck"><span class="eyebrow">Kandidatsett</span><b>${fmt((data.candidates||[]).length)} pre-registrerte</b><small>Ingen frie runtime-parametre og ingen søk etter historisk beste terskel.</small></div></div><div class="notice">Counterfactual sandbox er låst. Kandidat-fingerprint kan auditeres nå; dataset/report-fingerprint utstedes først når quality-gaten åpner.</div>`;
    }
    panel.innerHTML=`<div class="sectionHead"><div><h2>Counterfactual research sandbox</h2><div class="sub">Låst forskningsmiljø for forhåndsdefinerte terskelvarianter med senere kronologisk holdout.</div></div><span class="pill ${pillClass(status)}">${esc(status.replaceAll('_',' '))}</span></div>${body}`;
    const shadow=document.getElementById('shadowDatasetPanel');
    if(shadow)shadow.insertAdjacentElement('afterend',panel);else root.appendChild(panel);
  }

  async function load(){
    try{
      const response=await fetch('/api/opportunity-shadow/sandbox',{cache:'no-store'});
      if(response.ok)render(await response.json());
    }catch(_error){}
  }
  load();
})();
