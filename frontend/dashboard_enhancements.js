(function(){
  const TYPE_ORDER=['Aksjer','Fond','ETF','Kontanter','Øvrig'];
  const esc=v=>String(v==null?'':v).replace(/[&<>\"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));
  const typeLabel=x=>x.asset_class||x.instrument_type||x.type||'Aksjer';
  const currentUniverse=()=>{
    try{return typeof universe!=='undefined'&&Array.isArray(universe)?universe:[]}catch{return []}
  };
  const fullName=t=>{
    const u=currentUniverse().find(x=>String(x.ticker||'').toUpperCase()===String(t||'').toUpperCase());
    return u?.name||t;
  };

  function addStyles(){
    if(document.getElementById('nsDashboardEnhancementStyles'))return;
    const s=document.createElement('style');
    s.id='nsDashboardEnhancementStyles';
    s.textContent=`
      .nsTypeBadge{display:inline-flex;align-items:center;padding:3px 7px;border:1px solid #343434;border-radius:999px;font-size:10px;font-weight:800;color:#cfcfcf;background:#151515;margin-left:7px}
      .nsSearchMeta{display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin-top:4px;color:#999;font-size:11px}
      .nsTraffic{display:flex;gap:14px;align-items:center;flex-wrap:wrap;padding:13px 16px;margin:0 0 17px;border:1px solid #292929;border-radius:12px;background:#0e0e0e}
      .nsTrafficTitle{font-weight:800;margin-right:4px}.nsLightItem{display:flex;align-items:center;gap:8px;color:#b7b7b7;font-size:11px}.nsLightItem b{color:#f2f2f2;font-size:11px}.nsLight{width:13px;height:13px;border-radius:50%;box-shadow:0 0 0 3px #171717,0 0 0 4px #333}.nsLight.green{background:#35d99b}.nsLight.yellow{background:#e7c16b}.nsLight.red{background:#ff7586}
      .nsSignalGroup{margin-top:14px}.nsSignalGroup:first-of-type{margin-top:8px}.nsSignalGroupTitle{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid #292929;margin-bottom:2px}.nsSignalGroupTitle b{font-size:12px}.nsSignalGroupTitle span{font-size:10px;color:#888}
      .nsSignalName{display:block;font-weight:800}.nsSignalTicker{font-size:10px;color:#888;margin-left:6px}.nsSignalEvent{margin-top:2px}
      .nsSearchHint{padding:12px;color:#999}.nsSearchError{color:#ff9cab}
    `;
    document.head.appendChild(s);
  }

  function isTracked(item){
    if(item.tracked)return true;
    const t=String(item.ticker||'').toUpperCase().replace(/\.OL$/,'');
    return currentUniverse().some(x=>String(x.ticker||'').toUpperCase()===t);
  }

  function openSearchItem(item){
    const ticker=String(item.ticker||item.symbol||'').toUpperCase().replace(/\.OL$/,'');
    const panel=document.getElementById('searchResults');
    if(panel)panel.style.display='none';
    if(isTracked(item)&&typeof showStock==='function'){
      showStock(ticker);
      return;
    }
    const symbol=item.market_symbol||item.symbol||item.ticker||ticker;
    const p=new URLSearchParams({symbol:String(symbol)});
    if(item.name)p.set('name',item.name);
    if(item.quote_type)p.set('type',item.quote_type);
    if(item.exchange||item.market)p.set('exchange',item.exchange||item.market);
    if(item.currency)p.set('currency',item.currency);
    location.href='/frontend/instrument.html?'+p.toString();
  }

  function installGlobalSearch(){
    const old=document.getElementById('search');
    if(!old||old.dataset.nsGlobalSearch==='1')return;
    const input=old.cloneNode(true);
    input.dataset.nsGlobalSearch='1';
    input.placeholder='Søk aksje, fond, ETF eller ticker…';
    old.replaceWith(input);
    const panel=document.getElementById('searchResults');
    const list=document.getElementById('searchResultsList');
    let timer=0,seq=0;
    input.addEventListener('input',()=>{
      const q=input.value.trim();
      clearTimeout(timer);
      if(!q){if(panel)panel.style.display='none';return;}
      timer=setTimeout(async()=>{
        const mine=++seq;
        if(list)list.innerHTML='<div class="nsSearchHint">Søker i aksjer, fond og ETF-er…</div>';
        if(panel)panel.style.display='block';
        try{
          const r=await fetch('/api/search?q='+encodeURIComponent(q)+'&limit=20',{cache:'no-store'});
          const d=await r.json().catch(()=>({}));
          if(!r.ok)throw new Error(d.message||d.detail||('HTTP '+r.status));
          if(mine!==seq)return;
          const rows=Array.isArray(d.items)?d.items:[];
          if(!rows.length){list.innerHTML='<div class="nsSearchHint">Ingen treff. Prøv hele navnet, ticker eller et annet fondnavn.</div>';return;}
          list.innerHTML=rows.map((x,i)=>{
            const type=typeLabel(x),symbol=x.market_symbol||x.symbol||x.ticker||'',exchange=x.exchange||x.market||'Marked ukjent';
            return `<div class="result" data-ns-search-index="${i}"><strong>${esc(x.name||symbol)}</strong><span class="nsTypeBadge">${esc(type)}</span><div class="nsSearchMeta"><span>${esc(symbol)}</span><span>·</span><span>${esc(exchange)}</span>${x.currency?`<span>·</span><span>${esc(x.currency)}</span>`:''}${x.tracked?'<span>· NordicSignal</span>':''}</div></div>`;
          }).join('');
          [...list.querySelectorAll('[data-ns-search-index]')].forEach(el=>el.onclick=()=>openSearchItem(rows[Number(el.dataset.nsSearchIndex)]));
        }catch(e){
          if(mine!==seq)return;
          list.innerHTML=`<div class="nsSearchHint nsSearchError">Søket er midlertidig utilgjengelig: ${esc(e.message)}</div>`;
        }
      },220);
    });
    document.addEventListener('click',e=>{if(panel&&!e.target.closest('.searchbox'))panel.style.display='none'});
  }

  function ensureTrafficLegend(){
    const app=document.getElementById('appview');
    if(!app||document.getElementById('nsTrafficLegend'))return;
    const cards=app.querySelector('.cards');
    if(!cards)return;
    const box=document.createElement('section');
    box.id='nsTrafficLegend';
    box.className='nsTraffic';
    box.innerHTML=`<span class="nsTrafficTitle">Signalguide</span><span class="nsLightItem"><i class="nsLight green"></i><span><b>KJØP / STRONG</b> · positivt signal</span></span><span class="nsLightItem"><i class="nsLight yellow"></i><span><b>WATCH / NEUTRAL</b> · følg med</span></span><span class="nsLightItem"><i class="nsLight red"></i><span><b>SELL / RISK</b> · negativt signal / høyere risiko</span></span>`;
    cards.insertAdjacentElement('afterend',box);
  }

  async function enhanceLatestSignals(){
    const sections=[...document.querySelectorAll('#appview .section')];
    const section=sections.find(s=>(s.querySelector('h2')?.textContent||'').trim()==='Latest Signals');
    if(!section||section.dataset.nsGrouped==='loading'||section.dataset.nsGrouped==='done')return;
    section.dataset.nsGrouped='loading';
    try{
      const r=await fetch('/api/radar',{cache:'no-store'});
      if(!r.ok)throw new Error('HTTP '+r.status);
      const d=await r.json();
      const items=Array.isArray(d.items)?d.items:[];
      const groups={};
      items.forEach(x=>{const k=typeLabel(x);(groups[k]||(groups[k]=[])).push(x)});
      const keys=Object.keys(groups).sort((a,b)=>{
        const ai=TYPE_ORDER.indexOf(a),bi=TYPE_ORDER.indexOf(b);
        return (ai<0?99:ai)-(bi<0?99:bi)||a.localeCompare(b,'no');
      });
      const body=keys.length?keys.map(k=>{
        const rows=groups[k];
        return `<div class="nsSignalGroup"><div class="nsSignalGroupTitle"><b>${esc(k)}</b><span>${rows.length} signal${rows.length===1?'':'er'}</span></div>${rows.map(x=>{
          const strength=String(x.strength||'').toLowerCase();
          const cls=strength==='risk'?'r':strength==='watch'?'y':'g';
          const name=x.name||fullName(x.ticker);
          return `<div class="signal"><strong class="${cls}"><span class="nsSignalName">${esc(name)}<span class="nsSignalTicker">${esc(x.ticker||'')}</span></span></strong><div class="sub nsSignalEvent">${esc(x.event||'Model signal')} · Score ${esc(x.score)}/100</div></div>`;
        }).join('')}</div>`;
      }).join(''):'<div class="nsSearchHint">Ingen aktive signaler akkurat nå.</div>';
      section.innerHTML='<h2>Latest Signals</h2><div class="sub">Sortert etter instrumenttype. Fond og ETF-er vises automatisk som egne grupper når signalmotoren dekker dem.</div>'+body;
      section.dataset.nsGrouped='done';
    }catch(e){
      section.dataset.nsGrouped='';
    }
  }

  let queued=false;
  function refreshEnhancements(){
    if(queued)return;queued=true;
    setTimeout(()=>{
      queued=false;
      installGlobalSearch();
      ensureTrafficLegend();
      enhanceLatestSignals();
    },60);
  }

  addStyles();
  refreshEnhancements();
  new MutationObserver(refreshEnhancements).observe(document.documentElement,{childList:true,subtree:true});
})();
