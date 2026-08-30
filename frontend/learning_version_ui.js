(()=>{
  const esc=value=>String(value??'').replace(/[&<>\"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[char]));
  const fmt=value=>Number(value||0).toLocaleString('no-NO');
  const fmt1=value=>value==null?'—':Number(value).toLocaleString('no-NO',{maximumFractionDigits:1});
  const fmtPct=value=>value==null?'—':`${Number(value)>=0?'+':''}${Number(value).toLocaleString('no-NO',{maximumFractionDigits:1})}%`;
  const pillClass=status=>status==='PASS'||status==='HEALTHY'?'ready':status==='NOT_APPLICABLE'?'muted':'';

  function renderVersion(data){
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

  function confidenceCard(horizon,item){
    const raw=item?.raw_return||{};
    const alpha=item?.market_adjusted_alpha||{};
    const rawWilson=raw.positive_rate_wilson_95||{};
    const rawMedian=raw.median_ci_95||{};
    const alphaWilson=alpha.positive_rate_wilson_95||{};
    const alphaMedian=alpha.median_ci_95||{};
    const status=String(item?.status||'COLLECTING_DATA');
    return `<div class="qualityCheck">
      <span class="pill ${pillClass(status)}">${esc(status.replaceAll('_',' '))}</span>
      <b>${esc(horizon)}d · n=${fmt(raw.n)}</b>
      <small>Rå: positivrate nedre 95 % ${fmtPct(rawWilson.lower_pct)} · median nedre 95 % ${fmtPct(rawMedian.lower)}.<br>OSEBX-alpha: positivrate nedre 95 % ${fmtPct(alphaWilson.lower_pct)} · median nedre 95 % ${fmtPct(alphaMedian.lower)}.</small>
    </div>`;
  }

  function renderStatistical(data){
    const gate=data&&data.statistical_confidence_gate;
    const root=document.getElementById('content');
    if(!gate||!root||document.getElementById('statisticalConfidencePanel'))return;
    const status=String(gate.status||'COLLECTING_DATA');
    const horizons=gate.horizons||{};
    const required=gate.required_horizons||[5,10,20];
    const panel=document.createElement('section');
    panel.className='section';
    panel.id='statisticalConfidencePanel';
    panel.innerHTML=`
      <div class="sectionHead">
        <div><h2>Statistisk sikkerhet</h2><div class="sub">95 % usikkerhetsgate for aktiv modell. Både råavkastning og OSEBX-alpha må vise robust positiv retning.</div></div>
        <span class="pill ${pillClass(status)}">${esc(status)}</span>
      </div>
      <div class="qualityGrid">${required.map(h=>confidenceCard(h,horizons[String(h)]||{})).join('')}</div>
      <div class="notice">Krav: minst <strong>${fmt(gate.minimum_passing_horizons||2)} av ${fmt(required.length)}</strong> horisonter må passere. Wilson 95 %-grensens positive rate må være over 50 %, og nedre 95 %-grense for median må være over 0 %, for både aksjen og markedsjustert alpha. <strong>Ingen terskler endres automatisk.</strong></div>`;
    const health=document.getElementById('learningHealthPanel');
    const version=document.getElementById('modelVersionPanel');
    if(health)health.insertAdjacentElement('afterend',panel);else if(version)version.insertAdjacentElement('afterend',panel);else root.prepend(panel);
  }

  function checkCard(title,check,detail){
    const status=String(check?.status||'FAIL');
    return `<div class="qualityCheck"><span class="pill ${pillClass(status)}">${esc(status.replaceAll('_',' '))}</span><b>${esc(title)}</b><small>${detail}</small></div>`;
  }

  function renderHealth(data){
    const root=document.getElementById('content');
    if(!root||!data||document.getElementById('learningHealthPanel'))return;
    const checks=data.checks||{};
    const scheduler=checks.scheduler||{};
    const discovery=checks.discovery||{};
    const versioning=checks.model_versioning||{};
    const context=checks.market_context||{};
    const adjustment=checks.market_adjustment||{};
    const overall=String(data.learning_pipeline_status||'DEGRADED');
    const panel=document.createElement('section');
    panel.className='section';
    panel.id='learningHealthPanel';
    panel.innerHTML=`
      <div class="sectionHead">
        <div><h2>Learning Pipeline Health</h2><div class="sub">Driftskontroll av datainnsamlingen. Dette påvirker ikke signaler eller terskler.</div></div>
        <span class="pill ${pillClass(overall)}">${esc(overall)}</span>
      </div>
      <div class="qualityGrid">
        ${checkCard('Scheduler',scheduler,`Cron heartbeat ${fmt1(scheduler.heartbeat_age_minutes)} min siden · ${fmt(scheduler.external_trigger_count)} triggere.`)}
        ${checkCard('Discovery',discovery,`${fmt(discovery.cached_candidates)} kandidater · cache ${fmt1(discovery.cache_age_minutes)} min · ${discovery.refreshing?'refresh kjører':'idle'}.`)}
        ${checkCard('Modellstempling',versioning,`${fmt(versioning.active_model_events)} aktive · ${fmt(versioning.legacy_unverified_events)} legacy · ${fmt(versioning.unversioned_events)} uten versjon.`)}
        ${checkCard('OSEBX-kontekst',context,`${fmt(context.overdue_missing_context)} forsinkede av ${fmt(context.total_events)} events · grace ${fmt(context.grace_minutes)} min.`)}
        ${checkCard('OSEBX-adjustering',adjustment,`${fmt(adjustment.overdue_missing_market_adjustments)} forsinkede av ${fmt(adjustment.settled_stock_returns)} ferdige forward-returer · grace ${fmt(adjustment.grace_minutes)} min.`)}
      </div>
      <div class="notice">${overall==='HEALTHY'?'Pipeline-komponentene rapporterer normalt.':'Én eller flere pipeline-komponenter trenger oppfølging. Se statuskortene over.'} Endpoint: <strong>/api/opportunity-learning-health</strong>.</div>`;
    const versionPanel=document.getElementById('modelVersionPanel');
    if(versionPanel)versionPanel.insertAdjacentElement('afterend',panel);else root.prepend(panel);
  }

  async function load(){
    const [performance,health]=await Promise.allSettled([
      fetch('/api/opportunity-performance?limit=100',{cache:'no-store'}).then(r=>r.ok?r.json():null),
      fetch('/api/opportunity-learning-health',{cache:'no-store'}).then(r=>r.ok?r.json():null),
    ]);
    if(performance.status==='fulfilled'&&performance.value){renderVersion(performance.value);renderStatistical(performance.value)}
    if(health.status==='fulfilled'&&health.value)renderHealth(health.value);
  }
  load();
})();
