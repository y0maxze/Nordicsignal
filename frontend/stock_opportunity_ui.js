(function(){
  const ticker=(new URLSearchParams(location.search).get('ticker')||'').toUpperCase().replace(/\.OL$/,'');
  const esc=v=>String(v==null?'—':v).replace(/[&<>\"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));
  const fmt=(v,d=1)=>v==null?'—':Number(v).toLocaleString('no-NO',{maximumFractionDigits:d});
  const kr=v=>{if(v==null)return '—';const n=Number(v),a=Math.abs(n);if(a>=1e9)return fmt(n/1e9,2)+' mrd. kr';if(a>=1e6)return fmt(n/1e6,2)+' mill. kr';if(a>=1e3)return fmt(n/1e3,1)+'k kr';return fmt(n,0)+' kr'};

  function styles(){
    if(document.getElementById('nsOpportunityStyles'))return;
    const s=document.createElement('style');s.id='nsOpportunityStyles';s.textContent=`
      .nsOpportunity{margin-top:14px}.nsOpportunityHead{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap}.nsOpportunityLabel{font-size:18px;font-weight:850}.nsOpportunityGrid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:12px}.nsOpportunityMetric{background:#0a1727;border:1px solid var(--line);border-radius:10px;padding:12px}.nsOpportunityMetric span{display:block;color:var(--m);font-size:10px}.nsOpportunityMetric b{display:block;margin-top:5px;font-size:17px}.nsOpportunityReasons{margin-top:12px;display:grid;gap:6px}.nsOpportunityReason{background:#0a1727;border-radius:8px;padding:8px 10px;color:var(--m)}.nsOppHigh{color:var(--g)}.nsOppWatch{color:#e7c16b}.nsOppLow{color:var(--m)}@media(max-width:800px){.nsOpportunityGrid{grid-template-columns:repeat(2,1fr)}}@media(max-width:520px){.nsOpportunityGrid{grid-template-columns:1fr}}
    `;document.head.appendChild(s);
  }

  function labelText(label){
    return ({EARLY_OPPORTUNITY_HIGH:'HIGH',EARLY_OPPORTUNITY:'EARLY',WATCH_CONFLUENCE:'WATCH',REVERSAL_CANDIDATE:'REVERSAL CANDIDATE',NO_OPPORTUNITY:'INGEN AKTIV MULIGHET',INSUFFICIENT_DATA:'FOR LITE DATA'})[label]||String(label||'—').replaceAll('_',' ');
  }
  function labelClass(label){
    if(label==='EARLY_OPPORTUNITY_HIGH'||label==='EARLY_OPPORTUNITY')return 'nsOppHigh';
    if(label==='WATCH_CONFLUENCE'||label==='REVERSAL_CANDIDATE')return 'nsOppWatch';
    return 'nsOppLow';
  }
  function insiderText(c,signal){
    const coverage=signal?.evidence_coverage;
    if(coverage==='unavailable')return 'Utilgjengelig';
    if(coverage==='no_recent_detail')return 'Ingen nylig verifisert detalj';
    const buyers=Number(c.independent_buyers||0);
    return `${esc(c.insider_label||'NONE')}${buyers?` · ${buyers} kjøper${buyers===1?'':'e'}`:''}`;
  }

  function render(d){
    const root=document.getElementById('nsEarlyOpportunity');if(!root)return;
    const o=d?.opportunity||{},c=o.components||{},ins=d?.insider_signal_v2||{},reasons=o.reasons||[];
    const volume=c.volume_ratio==null?'Ingen bullish bekreftelse':fmt(c.volume_ratio,2)+'× bullish volum';
    root.innerHTML=`<div class="nsOpportunityHead"><div><div class="muted">SEPARAT EVIDENSSIGNAL · PÅVIRKER IKKE 0–100-SCORE</div><div class="nsOpportunityLabel ${labelClass(o.label)}">Early Opportunity: ${esc(labelText(o.label))}</div></div><div><b>${o.score==null?'—':esc(fmt(o.score,0))}/100</b><div class="muted">Confidence: ${esc(o.confidence||'—')}</div></div></div><div class="nsOpportunityGrid"><div class="nsOpportunityMetric"><span>Reversal</span><b>${esc(c.reversal_score==null?'—':fmt(c.reversal_score,0)+'/100')}</b><div class="muted">${esc(c.reversal_regime||'—')}</div></div><div class="nsOpportunityMetric"><span>Bullish volum</span><b>${esc(volume)}</b><div class="muted">Kun grønn handelsdag teller som bekreftelse</div></div><div class="nsOpportunityMetric"><span>Insider-evidens</span><b>${insiderText(c,ins)}</b><div class="muted">${esc(ins.evidence_source||'—')}</div></div><div class="nsOpportunityMetric"><span>Verifisert kjøpsverdi</span><b>${esc(kr(c.buy_value_nok))}</b><div class="muted">Brukes bare når transaksjonsdata er pålitelige</div></div></div>${reasons.length?`<div class="nsOpportunityReasons">${reasons.map(x=>`<div class="nsOpportunityReason">${esc(x)}</div>`).join('')}</div>`:'<div class="notice" style="margin-top:12px">Ingen sterk confluence akkurat nå.</div>'}<div class="muted" style="margin-top:10px">Dette er et separat, eksperimentelt evidenssignal. Det er ikke en kjøpsanbefaling og endrer ikke NordicSignal totalscore.</div>`;
  }

  async function load(){
    if(!ticker)return;
    const root=document.getElementById('nsEarlyOpportunity');if(!root)return;
    try{
      const r=await fetch('/api/opportunity/'+encodeURIComponent(ticker),{cache:'no-store'}),d=await r.json().catch(()=>({}));
      if(!r.ok)throw Error(d.detail||('HTTP '+r.status));
      render(d);
    }catch(e){root.innerHTML=`<div class="notice">Early Opportunity er midlertidig utilgjengelig: ${esc(e.message)}</div>`}
  }

  function attach(){
    if(!ticker)return;
    styles();
    const hero=document.querySelector('.hero');
    if(!hero)return;
    if(!document.getElementById('nsEarlyOpportunity'))hero.insertAdjacentHTML('afterend','<section id="nsEarlyOpportunity" class="card nsOpportunity"><div class="notice">Laster Early Opportunity…</div></section>');
    load();
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',attach,{once:true});else attach();
})();
