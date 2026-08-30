(()=>{
  const esc=value=>String(value??'').replace(/[&<>\"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[char]));
  const fmt=value=>Number(value||0).toLocaleString('no-NO');
  const fmtPct=value=>value==null?'—':`${Number(value).toLocaleString('no-NO',{maximumFractionDigits:1})}%`;
  const pillClass=status=>status==='PASS'?'ready':'';

  function attach(check){
    const panel=document.getElementById('learningHealthPanel');
    if(!panel||panel.querySelector('[data-shadow-health]'))return false;
    const grid=panel.querySelector('.qualityGrid');
    if(!grid)return false;
    const status=String(check?.status||'FAIL');
    const card=document.createElement('div');
    card.className='qualityCheck';
    card.dataset.shadowHealth='1';
    card.innerHTML=`<span class="pill ${pillClass(status)}">${esc(status)}</span><b>Shadow collection</b><small>Siste dag ${esc(check?.latest_market_date||'—')} · ${fmt(check?.latest_tickers)} aksjer · ${fmtPct(check?.latest_universe_coverage_pct)} universdekning.<br>Features ${fmtPct(check?.feature_completeness_pct)} · OSEBX ${fmtPct(check?.market_context_coverage_pct)} · duplikatgrupper ${fmt(check?.duplicate_snapshot_groups)}.<br>Research quality: ${esc(check?.research_quality_status||'COLLECTING_DATA')}.</small>`;
    grid.appendChild(card);
    return true;
  }

  async function load(){
    try{
      const response=await fetch('/api/opportunity-learning-health',{cache:'no-store'});
      if(!response.ok)return;
      const data=await response.json();
      const check=data?.checks?.shadow_collection;
      if(!check)return;
      if(attach(check))return;
      const observer=new MutationObserver(()=>{if(attach(check))observer.disconnect()});
      observer.observe(document.body,{childList:true,subtree:true});
      setTimeout(()=>observer.disconnect(),5000);
    }catch(_error){}
  }
  load();
})();
