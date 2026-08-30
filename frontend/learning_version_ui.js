(()=>{
  const esc=value=>String(value??'').replace(/[&<>\"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[char]));
  const fmt=value=>Number(value||0).toLocaleString('no-NO');

  function render(data){
    const v=data&&data.versioning;
    if(!v||!v.active_model)return;
    const root=document.getElementById('content');
    if(!root||document.getElementById('modelVersionPanel'))return;
    const active=v.active_model||{};
    const all=data.aggregate_all_versions||{};
    const panel=document.createElement('section');
    panel.className='section';
    panel.id='modelVersionPanel';
    panel.innerHTML=`
      <div class="sectionHead">
        <div>
          <h2>Modellversjon</h2>
          <div class="sub">Kalibrering bruker kun events fra den aktive, verifiserte signalmotoren. Gamle modellversjoner beholdes kun for revisjon.</div>
        </div>
        <span class="pill ready">ACTIVE MODEL ISOLATED</span>
      </div>
      <div class="qualityGrid">
        <div class="qualityCheck"><span class="eyebrow">Signalversjon</span><b>${esc(active.signal_version||'—')}</b><small>Fingerprint ${esc(active.signal_fingerprint||'—')}</small></div>
        <div class="qualityCheck"><span class="eyebrow">Aktiv sample</span><b>${fmt(v.active_model_events)} events</b><small>Kun disse teller mot readiness og kalibrering.</small></div>
        <div class="qualityCheck"><span class="eyebrow">Legacy</span><b>${fmt(v.legacy_unverified_events)} events</b><small>Beholdes for audit, men teller ikke i aktiv modell.</small></div>
        <div class="qualityCheck"><span class="eyebrow">Learning policy</span><b>${esc(active.learning_policy_version||'—')}</b><small>Fingerprint ${esc(active.learning_policy_fingerprint||'—')}</small></div>
      </div>
      <div class="notice">Aktiv modell-ID: <strong>${esc(active.signal_model_id||'—')}</strong>. Totalt på tvers av alle modellversjoner: ${fmt(all.events)} events. Hvis signalreglene endres, får den nye motoren automatisk en ny fingerprint og et separat forward-sample.</div>`;
    root.prepend(panel);
  }

  async function load(){
    try{
      const response=await fetch('/api/opportunity-performance?limit=100',{cache:'no-store'});
      if(!response.ok)return;
      render(await response.json());
    }catch(_error){}
  }
  load();
})();
