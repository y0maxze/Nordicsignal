(()=>{
  const esc=value=>String(value??'').replace(/[&<>\"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[char]));
  const fmt=value=>Number(value||0).toLocaleString('no-NO');
  const labelName=value=>String(value||'—').replaceAll('_',' ');

  function render(data){
    const root=document.getElementById('content');
    if(!root||!data||document.getElementById('shadowDatasetPanel'))return;
    const labels=data.label_counts||{};
    const context=data.market_context||{};
    const returns=data.forward_returns||{};
    const h20=returns['20']||{};
    const total=Number(data.active_model_snapshots||0);
    const classified=Number(context.classified||0);
    const coverage=total?classified/total*100:0;
    const labelEntries=Object.entries(labels).sort((a,b)=>Number(b[1]||0)-Number(a[1]||0));
    const labelText=labelEntries.length?labelEntries.map(([label,n])=>`${labelName(label)} ${fmt(n)}`).join(' · '):'Ingen snapshots ennå';
    const panel=document.createElement('section');
    panel.className='section';
    panel.id='shadowDatasetPanel';
    panel.innerHTML=`
      <div class="sectionHead">
        <div>
          <h2>Shadow calibration dataset</h2>
          <div class="sub">Representativ forskningslogg for fremtidige counterfactual terskeltester. Alle vellykkede daglige aksjescans kan inngå, også når live-signalet er NO OPPORTUNITY.</div>
        </div>
        <span class="pill muted">RESEARCH ONLY</span>
      </div>
      <div class="qualityGrid">
        <div class="qualityCheck"><span class="eyebrow">Snapshots</span><b>${fmt(total)}</b><small>${fmt(data.active_model_tickers)} aksjer · én first-observed snapshot per aksje og markedsdag.</small></div>
        <div class="qualityCheck"><span class="eyebrow">Signalspredning</span><b>${fmt(labelEntries.length)} nivåer</b><small>${esc(labelText)}</small></div>
        <div class="qualityCheck"><span class="eyebrow">OSEBX-kontekst</span><b>${coverage.toLocaleString('no-NO',{maximumFractionDigits:0})}%</b><small>${fmt(classified)}/${fmt(context.total)} snapshots klassifisert mot markedsregime.</small></div>
        <div class="qualityCheck"><span class="eyebrow">20d forward</span><b>${fmt(h20.n)} / ${fmt(h20.alpha_n)}</b><small>Rå forward-returer / returer med OSEBX-alpha.</small></div>
      </div>
      <div class="notice">Periode: <strong>${esc(data.first_market_date||'—')}</strong> → <strong>${esc(data.last_market_date||'—')}</strong>. Signalfeature-verdiene fryses ved første observasjon og overskrives ikke. Datasettet påvirker ikke live-score, Opportunity-labels, push-varsler eller terskler.</div>`;

    const walk=document.getElementById('walkForwardPanel');
    if(walk)walk.insertAdjacentElement('afterend',panel);
    else root.appendChild(panel);
  }

  async function load(){
    try{
      const response=await fetch('/api/opportunity-shadow/status',{cache:'no-store'});
      if(response.ok)render(await response.json());
    }catch(_error){}
  }

  load();
})();
