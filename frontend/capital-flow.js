(function(){
  const list=document.getElementById('cfList');
  const live=document.getElementById('cfLive');
  const search=document.getElementById('cfSearch');
  const refresh=document.getElementById('cfRefresh');
  let state='NEW',type='ALL',all=[];

  const esc=value=>String(value??'').replace(/[&<>"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch]));
  const fmtDate=value=>{if(!value)return 'Ukjent tid';try{return new Intl.DateTimeFormat('nb-NO',{dateStyle:'medium',timeStyle:'short'}).format(new Date(value))}catch{return String(value)}};
  const fmtNum=value=>{const n=Number(value);return Number.isFinite(n)?new Intl.NumberFormat('nb-NO',{maximumFractionDigits:2}).format(n):null};
  const fmtMoney=value=>{const n=Number(value);if(!Number.isFinite(n))return null;if(Math.abs(n)>=1e9)return `${(n/1e9).toFixed(2)} mrd. kr`;if(Math.abs(n)>=1e6)return `${(n/1e6).toFixed(2)} mill. kr`;return `${new Intl.NumberFormat('nb-NO',{maximumFractionDigits:0}).format(n)} kr`};
  const typeLabel=k=>({PRIMARY_INSIDER:'Primærinnsider',INSTITUTIONAL_FLOW:'Fond/institusjon',LARGE_HOLDING:'Flagging/stor eier',FOREIGN_OWNERSHIP:'Utenlandsk eierskap',BLOCK_TRADE:'Blokkhandel',OWNERSHIP_CHANGE:'Eierendring'})[k]||k||'Kapitalflyt';
  const stateLabel=k=>({NEW:'NYTT',ACTIVE:'PÅGÅENDE',HISTORICAL:'HISTORISK'})[k]||k;

  function selected(root,key,value){root.querySelectorAll('.cfChip').forEach(el=>el.classList.toggle('active',el.dataset[key]===value))}
  function render(){
    const needle=(search.value||'').trim().toLowerCase();
    const rows=all.filter(x=>(type==='ALL'||x.event_type===type)&&(!needle||[x.ticker,x.instrument_name,x.actor,x.title,x.summary,x.source].some(v=>String(v||'').toLowerCase().includes(needle))));
    document.getElementById('cfShown').textContent=String(rows.length);
    if(!rows.length){list.innerHTML='<div class="cfPanel cfEmpty">Ingen kapitalbevegelser i dette filteret ennå.</div>';return}
    list.innerHTML=rows.map(x=>{
      const direction=String(x.direction||'neutral').toLowerCase();
      const dtext=direction==='buy'?'KJØP':direction==='sell'?'SALG':'ENDRING';
      const evidence=x.evidence_level==='verified'?'Verifisert':'Rapportert';
      const shares=fmtNum(x.shares),price=fmtNum(x.price),money=fmtMoney(x.value_nok);
      const detail=[x.actor,shares?`${shares} aksjer`:null,price?`${price} kr/aksje`:null,money].filter(Boolean).join(' · ');
      const source=x.source_url?`<a class="cfSourceLink" href="${esc(x.source_url)}" target="_blank" rel="noopener noreferrer">${esc(x.source||'Kilde')}</a>`:esc(x.source||'Kilde');
      return `<article class="cfPanel cfItem">
        <div>
          <div class="cfTop"><span class="cfBadge ${String(x.state||'').toLowerCase()}">${stateLabel(x.state)}</span><span class="cfBadge ${esc(x.evidence_level)}">${evidence}</span><span class="cfBadge">${esc(typeLabel(x.event_type))}</span>${x.ticker?`<a class="cfTicker" href="/stock?ticker=${encodeURIComponent(x.ticker)}">${esc(x.ticker)}</a>`:''}</div>
          <div class="cfTitle">${esc(x.title)}</div>
          <div class="cfSummary">${esc(detail||x.summary||'Kapital-/eierendring registrert.')}</div>
          <div class="cfMeta"><span>${fmtDate(x.event_at)}</span><span>${source}</span>${x.instrument_name?`<span>${esc(x.instrument_name)}</span>`:''}</div>
        </div>
        <div class="cfDirection ${direction}">${dtext}</div>
      </article>`
    }).join('');
  }

  async function load(force=false){
    live.textContent=force?'Oppdaterer kilder…':'Laster kapitalflyt…';
    refresh.disabled=true;
    try{
      const qs=new URLSearchParams({limit:'250',state});
      if(force)qs.set('refresh','true');
      const res=await fetch(`/api/capital-flow?${qs}`,{cache:'no-store'});
      if(!res.ok)throw new Error(`HTTP ${res.status}`);
      const data=await res.json();all=Array.isArray(data.items)?data.items:[];
      const counts=data.counts||{};
      document.getElementById('cfNew').textContent=counts.NEW??0;
      document.getElementById('cfActive').textContent=counts.ACTIVE??0;
      document.getElementById('cfHistorical').textContent=counts.HISTORICAL??0;
      live.textContent=`Oppdatert ${fmtDate(data.generated_at)} · ${all.length} hendelser lastet`;
      render();
    }catch(err){
      all=[];render();live.textContent=`Kunne ikke hente kapitalflyt: ${err.message}`;
    }finally{refresh.disabled=false}
  }

  document.getElementById('cfStates').addEventListener('click',e=>{const b=e.target.closest('[data-state]');if(!b)return;state=b.dataset.state;selected(e.currentTarget,'state',state);load(false)});
  document.getElementById('cfTypes').addEventListener('click',e=>{const b=e.target.closest('[data-type]');if(!b)return;type=b.dataset.type;selected(e.currentTarget,'type',type);render()});
  search.addEventListener('input',render);
  refresh.addEventListener('click',()=>load(true));
  const incoming=new URLSearchParams(location.search).get('ticker');if(incoming)search.value=incoming;
  load(false);
})();
