(function(){
  const esc=v=>String(v==null?'—':v).replace(/[&<>\"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));
  const fmt=(v,d=2)=>v==null?'—':Number(v).toLocaleString('no-NO',{maximumFractionDigits:d});
  const kr=v=>v==null?'—':Number(v).toLocaleString('no-NO',{maximumFractionDigits:2})+' kr';
  const percent=v=>v==null?'—':Number(v).toLocaleString('no-NO',{minimumFractionDigits:2,maximumFractionDigits:4})+'%';
  const ticker=(new URLSearchParams(location.search).get('ticker')||'LSG').toUpperCase().replace(/\.OL$/,'');
  let pressure=null,pressureTimer=null;

  function addStyles(){
    if(document.getElementById('nsStockExtrasStyles'))return;
    const s=document.createElement('style');s.id='nsStockExtrasStyles';s.textContent=`
      #pressureAlertBar{margin-top:14px;display:none;gap:10px;flex-wrap:wrap}.pressureAlert{border:1px solid #333;border-radius:10px;padding:10px 12px;min-width:250px;flex:1;background:#0d0d0d}.pressureAlert b{display:block;margin-bottom:3px}.pressureDot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;background:#999}.pressureAlert.long .pressureDot{background:#18c984}.pressureAlert.short .pressureDot{background:#ff6b7d}.pressureGrid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:14px}
      .insiderSummary{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:12px 0 16px}.insiderSummary .metric b{font-size:17px}.actorBadge,.sourceBadge{display:inline-block;padding:3px 7px;border-radius:999px;font-size:10px;font-weight:800;margin-left:6px}.ownershipCell small{display:block;margin-top:3px}.actorBadge.person{background:#151515;color:#ddd}.actorBadge.company{background:#17130b;color:#e7c16b}.sourceBadge.disclosed{background:#0d1712;color:#55dca8}.sourceBadge.estimated{background:#17130b;color:#e7c16b}
      @media(max-width:900px){.pressureGrid,.insiderSummary{grid-template-columns:repeat(2,1fr)}}@media(max-width:550px){.pressureGrid,.insiderSummary{grid-template-columns:1fr}}
    `;document.head.appendChild(s);
  }

  function alertCard(a){
    const cls='pressureAlert '+(a.type==='long'?'long':a.type==='short'?'short':'');
    const title=a.type==='long'?'LONG-varsel':a.type==='short'?'SHORT-varsel':'Volumvarsel';
    return `<div class="${cls}"><b><span class="pressureDot"></span>${title}</b><span>${esc(a.message)}</span></div>`;
  }

  function updateAlertBar(){
    const bar=document.getElementById('pressureAlertBar');if(!bar||!pressure)return;
    const important=(pressure.alerts||[]).filter(a=>a.type==='long'||a.type==='short');
    bar.innerHTML=important.map(alertCard).join('');bar.style.display=important.length?'flex':'none';
  }

  function pressurePanel(){
    if(!pressure)return '<section class="card"><div class="notice">Laster market pressure…</div></section>';
    const s=pressure.short||{},l=pressure.long_proxy||{};
    const alerts=(pressure.alerts||[]).map(alertCard).join('')||'<div class="notice">Ingen aktive LONG/SHORT-varsler akkurat nå.</div>';
    return `<section class="card"><h2>Market Pressure · ${esc(ticker)}</h2><div class="notice">LONG er en transparent proxy basert på kurs, volum og eventuell shortreduksjon. SHORT bygger på offentlig Finanstilsynet SSR. Dette er ikke Level 2-ordrebokdata.</div><div class="pressureGrid"><div class="metric"><span class="muted">LONG proxy</span><b class="${l.level==='high'||l.level==='elevated'?'positive':''}">${esc(String(l.level||'none').toUpperCase())}</b></div><div class="metric"><span class="muted">Offentlig short</span><b>${esc(s.short_percent_float==null?'—':fmt(s.short_percent_float)+'%')}</b></div><div class="metric"><span class="muted">Short-endring</span><b class="${s.short_change_pp!=null&&s.short_change_pp>0?'negative':s.short_change_pp!=null&&s.short_change_pp<0?'positive':''}">${esc(s.short_change_pp==null?'—':(s.short_change_pp>0?'+':'')+fmt(s.short_change_pp)+' pp')}</b></div><div class="metric"><span class="muted">Volum / 20d</span><b>${esc(pressure.volume_ratio==null?'—':fmt(pressure.volume_ratio,1)+'×')}</b></div></div><div style="margin-top:14px">${alerts}</div><div class="item"><b>Pressure proxy</b><div class="muted">${esc(pressure.pressure_text||'—')}</div></div><div class="item"><b>Databegrensning</b><div class="muted">${esc(pressure.order_book_note||'—')}</div></div></section>`;
  }

  function renderPressure(){
    document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x.dataset.tab==='pressure'));
    const c=document.getElementById('content');if(c)c.innerHTML=pressurePanel();
  }

  async function refreshPressure(){
    try{
      const r=await fetch('/api/market-pressure/'+encodeURIComponent(ticker),{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);
      pressure=await r.json();updateAlertBar();
      const active=document.querySelector('.tab.active');if(active&&active.dataset.tab==='pressure')renderPressure();
    }catch(e){console.warn('market pressure unavailable',e)}
  }

  function installPressure(){
    const tabs=document.querySelector('.tabs');
    if(tabs&&!tabs.querySelector('[data-tab="pressure"]')){const b=document.createElement('button');b.className='tab';b.dataset.tab='pressure';b.textContent='Market Pressure';b.onclick=renderPressure;tabs.appendChild(b)}
    const hero=document.querySelector('.hero');if(hero&&!document.getElementById('pressureAlertBar'))hero.insertAdjacentHTML('afterend','<div id="pressureAlertBar"></div>');
    refreshPressure();if(pressureTimer)clearInterval(pressureTimer);pressureTimer=setInterval(()=>{if(!document.hidden)refreshPressure()},60000);
  }

  function installInsider(){
    if(typeof window.insider!=='function')return;
    window.insider=function(){
      const d=(window.data&&window.data.insider)||{},a=d.items||[];
      const summary=`<div class="insiderSummary"><div class="metric"><span class="muted">Kjøp</span><b class="positive">${esc(d.buy_count||0)}</b></div><div class="metric"><span class="muted">Salg</span><b class="negative">${esc(d.sell_count||0)}</b></div><div class="metric"><span class="muted">Verifiserte handler</span><b>${esc(d.verified_detail_count||0)}</b></div><div class="metric"><span class="muted">Kilde</span><b style="font-size:12px">${esc(d.source||'Euronext / Oslo Børs')}</b></div></div>`;
      const note='<div class="notice">Kun offentlige og verifiserbare opplysninger vises. Eierandel merkes oppgitt når den står direkte i meldingen. NordicSignal gjetter ikke identitet eller beløp.</div>';
      if(!a.length)return `<section class="card"><h2>Insider · hvem kjøpte og solgte?</h2>${summary}${note}<div class="notice">Ingen detaljerte offentlige insiderhandler tilgjengelig akkurat nå.</div></section>`;
      const rows=a.map(x=>{const actor=x.person||x.entity||x.insider||x.holder||'Ikke oppgitt i kilden',actorType=x.actor_type==='company'?'company':x.actor_type==='person'?'person':'',actorLabel=actorType==='company'?'FORETAK':actorType==='person'?'PERSON':'',value=x.transaction_value!=null?x.transaction_value:(x.shares!=null&&x.price!=null?x.shares*x.price:null),ownSource=x.ownership_pct_source||'',ownBadge=ownSource==='disclosed'?'<span class="sourceBadge disclosed">OPPGITT</span>':ownSource?'<span class="sourceBadge estimated">ESTIMERT</span>':'',ownNote=ownSource==='estimated_from_latest_annual_share_count'?'<small>Basert på siste tilgjengelige aksjetall</small>':'';return `<tr><td>${esc(x.trade_date||x.date||'—')}</td><td><span class="pill ${x.transaction_type==='sell'?'sell':''}">${esc(x.transaction_type==='buy'?'KJØP':x.transaction_type==='sell'?'SALG':'ANNET')}</span></td><td><b>${esc(actor)}</b>${actorLabel?`<span class="actorBadge ${actorType}">${actorLabel}</span>`:''}</td><td>${esc(x.role||'—')}</td><td>${fmt(x.shares,0)}</td><td>${kr(x.price)}</td><td>${kr(value)}</td><td>${fmt(x.holding_after_shares,0)}</td><td class="ownershipCell"><b>${percent(x.ownership_pct)}</b>${ownBadge}${ownNote}</td><td>${x.url?`<a href="${esc(x.url)}" target="_blank" rel="noopener">Original</a>`:'—'}</td></tr>`}).join('');
      return `<section class="card"><h2>Insider · hvem kjøpte og solgte?</h2>${summary}${note}<div class="tablewrap"><table><thead><tr><th>Dato</th><th>Handling</th><th>Person / foretak</th><th>Rolle</th><th>Antall</th><th>Pris</th><th>Verdi</th><th>Eier etter</th><th>Eierandel</th><th>Kilde</th></tr></thead><tbody>${rows}</tbody></table></div></section>`;
    };
  }

  function installDeepLink(){
    const tab=(new URLSearchParams(location.search).get('tab')||'').toLowerCase(),allowed={overview:1,news:1,insider:1,reports:1,dividend:1,short:1,paper:1,backtest:1,pressure:1};if(!allowed[tab])return;
    let tries=0;const timer=setInterval(()=>{tries++;const button=document.querySelector('.tab[data-tab="'+tab+'"]'),content=document.getElementById('content');if(button&&content&&content.children.length){button.click();clearInterval(timer)}else if(tries>80)clearInterval(timer)},125);
  }

  addStyles();installInsider();installPressure();installDeepLink();
})();