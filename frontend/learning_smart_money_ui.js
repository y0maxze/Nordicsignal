(()=>{
  const esc=v=>String(v??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));
  const fmt=v=>Number(v||0).toLocaleString('no-NO');
  const pct=v=>v==null?'—':`${Number(v).toLocaleString('no-NO',{maximumFractionDigits:1})}%`;
  const num=v=>v==null?'—':Number(v).toLocaleString('no-NO',{maximumFractionDigits:2});
  function render(data){
    const root=document.getElementById('content'); if(!root||!data||document.getElementById('smartMoneyLearningPanel'))return;
    const counts=data.quality_counts||{}, by=data.by_quality||{};
    const rows=['HIGH','MEDIUM','LOW'].map(q=>{
      const h5=(by[q]||{})['5']||{}, h20=(by[q]||{})['20']||{};
      return `<tr><td><strong>${q}</strong></td><td>${fmt(counts[q]||0)}</td><td>${fmt(h5.n||0)}</td><td>${num(h5.mean_return_pct)}%</td><td>${pct(h5.positive_rate_pct)}</td><td>${num(h5.mean_excess_return_pct)}%</td><td>${fmt(h20.n||0)}</td><td>${num(h20.mean_excess_return_pct)}%</td></tr>`;
    }).join('');
    const panel=document.createElement('section'); panel.className='section'; panel.id='smartMoneyLearningPanel';
    panel.innerHTML=`<div class="sectionHead"><div><h2>Smart Money validation</h2><div class="sub">Forward-måling av frozen insiderkvalitet. HIGH betyr ikke automatisk kjøpssignal; vi må først se om gruppen faktisk slår LOW/MEDIUM over tid.</div></div><span class="pill muted">MEASUREMENT ONLY</span></div>
      <div class="qualityGrid"><div class="qualityCheck"><span class="eyebrow">HIGH snapshots</span><b>${fmt(counts.HIGH||0)}</b><small>Flere meningsfulle kjøpere / sterk rolle- og kapital-evidens.</small></div><div class="qualityCheck"><span class="eyebrow">MEDIUM snapshots</span><b>${fmt(counts.MEDIUM||0)}</b><small>Delvis Smart Money-konfluens.</small></div><div class="qualityCheck"><span class="eyebrow">LOW snapshots</span><b>${fmt(counts.LOW||0)}</b><small>Kvalifiserte, men svakere insiderforhold.</small></div><div class="qualityCheck"><span class="eyebrow">Manglende sidecar</span><b>${fmt(data.missing_smart_money_sidecar||0)}</b><small>Bør være 0 for snapshots fra aktiv modell etter denne deployen.</small></div></div>
      <div style="overflow:auto"><table><thead><tr><th>Kvalitet</th><th>Snapshots</th><th>5d n</th><th>5d snitt</th><th>5d positiv</th><th>5d OSEBX-alpha</th><th>20d n</th><th>20d OSEBX-alpha</th></tr></thead><tbody>${rows}</tbody></table></div>
      <div class="notice"><strong>Ingen automatisk tuning.</strong> Smart Money skal bare få større live-betydning dersom forward-data, uavhengighetsgate, markedsregime og statistisk usikkerhet støtter det.</div>`;
    const shadow=document.getElementById('shadowDatasetPanel'); if(shadow)shadow.insertAdjacentElement('afterend',panel); else root.appendChild(panel);
  }
  async function load(){try{const r=await fetch('/api/opportunity-shadow/smart-money-performance',{cache:'no-store'});if(r.ok)render(await r.json());}catch(_){}}
  load();
})();
