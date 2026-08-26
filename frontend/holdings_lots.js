(function(){
  const expanded=new Set();
  let activeAddId=null;

  function addStyles(){
    if(document.getElementById('nsHoldingLotsStyles'))return;
    const s=document.createElement('style');s.id='nsHoldingLotsStyles';s.textContent=`
      .lotToggle{white-space:nowrap}.lotToggle b{font-size:15px;margin-right:5px}.lotDetail td{padding:0!important;border-bottom:1px solid #2a2a2a!important}.lotPanel{background:#0a0a0a;padding:16px 18px 18px;border-top:1px solid #242424}.lotHead{display:flex;justify-content:space-between;gap:14px;align-items:center;flex-wrap:wrap;margin-bottom:12px}.lotHead h3{margin:0;font-size:14px}.lotSummary{display:flex;gap:18px;flex-wrap:wrap;color:#aaa;font-size:11px}.lotSummary b{color:#eee;margin-left:4px}.lotTable{width:100%;border-collapse:collapse;min-width:760px}.lotTable th,.lotTable td{padding:10px 8px!important;border-bottom:1px solid #222!important;text-align:left}.lotTable th{font-size:10px;color:#888;font-weight:650}.lotGain{font-weight:800}.lotStatus{font-weight:850;font-variant-numeric:tabular-nums}.lotLegacy{color:#888;font-size:10px;margin-top:3px}.lotForm{display:grid;grid-template-columns:1fr .8fr .9fr 1.2fr auto;gap:8px;align-items:end;margin-top:13px;padding:12px;border:1px solid #292929;border-radius:9px;background:#0d0d0d}.lotForm label{display:block;color:#888;font-size:10px;margin-bottom:5px}.lotForm input{width:100%;background:#080808;border:1px solid #303030;color:#fff;border-radius:7px;padding:9px}.lotInit{display:flex;gap:8px;align-items:end;flex-wrap:wrap;margin-top:12px;padding:12px;border:1px dashed #303030;border-radius:9px}.lotInit .fieldMini{min-width:170px}.fieldMini label{display:block;color:#888;font-size:10px;margin-bottom:5px}.fieldMini input{background:#080808;border:1px solid #303030;color:#fff;border-radius:7px;padding:9px}.lotEmpty{color:#999;font-size:12px}.lotActions{display:flex;gap:7px;flex-wrap:wrap}.lotDelete{padding:5px 7px!important;font-size:10px!important}.lotToday{color:#888;font-size:10px}.lotUnpriced{color:#888}.lotMainResult{font-variant-numeric:tabular-nums}@media(max-width:850px){.lotForm{grid-template-columns:1fr 1fr}.lotForm .lotNote{grid-column:1/-1}.lotForm .btn{width:100%}}
    `;document.head.appendChild(s);
  }

  function lotDate(x){return x.purchase_date||'Dato ikke registrert'}
  function lotResult(x){
    if(x.unrealized_pnl==null)return '<span class="lotUnpriced">—</span>';
    const sign=Number(x.unrealized_pnl)>=0?'+':'';
    return `<span class="lotStatus ${cls(x.unrealized_pnl)}">${sign}${kr(x.unrealized_pnl)}</span><div class="${cls(x.unrealized_pnl_pct)}">${Number(x.unrealized_pnl_pct)>=0?'+':''}${pct(x.unrealized_pnl_pct)}</div>`;
  }
  function purchaseTable(x){
    const lots=x.purchase_lots||[];
    if(!lots.length)return `<div class="lotEmpty">Denne posisjonen er foreløpig lagret som én total. Du kan registrere kjøpsdatoen på den eksisterende beholdningen, eller legge til et nytt kjøp.</div>${initializeForm(x)}${addForm(x)}`;
    const rows=lots.map(l=>`<tr><td>${esc(lotDate(l))}${l.is_legacy?'<div class="lotLegacy">Tidligere beholdning</div>':''}</td><td>${num(l.shares)}</td><td>${kr(l.price_nok)}</td><td>${kr(l.cost_basis)}</td><td>${kr(l.current_price)}</td><td>${lotResult(l)}</td><td>${l.note?esc(l.note):'—'}</td><td><button class="btn danger lotDelete" onclick="deletePurchaseLot(${Number(l.id)},${Number(x.id)})">Slett</button></td></tr>`).join('');
    return `<div class="tablewrap"><table class="lotTable"><thead><tr><th>Kjøpsdato</th><th>Antall</th><th>Kjøpspris</th><th>Investert</th><th>Dagens kurs</th><th>+ / − siden kjøp</th><th>Notat</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>${activeAddId===Number(x.id)?addForm(x):''}`;
  }
  function initializeForm(x){return `<div class="lotInit"><div class="fieldMini"><label>Kjøpsdato for eksisterende ${num(x.shares)} aksjer</label><input id="lotInitDate${Number(x.id)}" type="date" max="${todayISO()}"></div><button class="btn" onclick="initializePurchaseLots(${Number(x.id)})">Registrer eksisterende kjøp</button></div>`}
  function addForm(x){return `<div class="lotForm"><div><label>Kjøpsdato</label><input id="lotDate${Number(x.id)}" type="date" max="${todayISO()}" value="${todayISO()}"></div><div><label>Antall</label><input id="lotShares${Number(x.id)}" type="number" min="0.000001" step="any" placeholder="f.eks. 20"></div><div><label>Pris per aksje · NOK</label><input id="lotPrice${Number(x.id)}" type="number" min="0.000001" step="any" placeholder="f.eks. 22"></div><div class="lotNote"><label>Notat · valgfritt</label><input id="lotNote${Number(x.id)}" maxlength="240" placeholder="f.eks. kjøp etter Q2"></div><button class="btn primary" onclick="savePurchaseLot(${Number(x.id)})">Legg til kjøp</button></div>`}
  function detailRow(x){
    const lots=x.purchase_lots||[],s=x.purchase_summary||{};
    return `<tr class="lotDetail"><td colspan="10"><div class="lotPanel"><div class="lotHead"><div><h3>${esc(x.instrument_name||x.company_name||x.ticker)} · kjøpsoversikt</h3><div class="lotSummary"><span>Totalt antall <b>${num(x.shares)}</b></span><span>Snittpris <b>${kr(x.average_cost)}</b></span><span>Investert <b>${kr(x.invested)}</b></span><span>Samlet resultat <b class="${cls(x.unrealized_pnl)}">${x.unrealized_pnl==null?'—':(Number(x.unrealized_pnl)>=0?'+':'')+kr(x.unrealized_pnl)} ${x.unrealized_pnl_pct==null?'':`(${Number(x.unrealized_pnl_pct)>=0?'+':''}${pct(x.unrealized_pnl_pct)})`}</b></span></div></div><div class="lotActions"><button class="btn compact" onclick="toggleAddPurchase(${Number(x.id)})">+ Legg til kjøp</button><button class="btn compact" onclick="togglePurchaseLots(${Number(x.id)})">Lukk</button></div></div>${purchaseTable(x)}</div></td></tr>`;
  }

  const original=window.renderHoldingsTable;
  window.renderHoldingsTable=function(items){
    addStyles();
    const filtered=assetFilter&&assetFilter!=='Kontanter'?items.filter(x=>(x.asset_class||'Aksjer')===assetFilter):assetFilter==='Kontanter'?[]:items;
    $('assetFilterNote').innerHTML=assetFilter?`<span class="pill">Filter: ${esc(assetFilter)}</span>`:'';
    if(!filtered.length){$('tableHost').innerHTML=assetFilter?`<div class="empty">Ingen ${esc(assetFilter.toLowerCase())} i beholdningen.</div>`:'<div class="empty">Ingen beholdninger registrert.</div>';return}
    const body=filtered.map(x=>{
      const link=stockLink(x),title=esc(x.instrument_name||x.company_name||x.ticker),tickerText=esc(x.market_symbol||x.ticker),native=x.native_currency&&x.native_currency!=='NOK'?`<div class="native">${num(x.current_price_native)} ${esc(x.native_currency)} · FX ${num(x.fx_to_nok)}</div>`:'',open=expanded.has(Number(x.id)),count=Number(x.purchase_lot_count||0);
      const main=`<tr><td>${link?`<a class="ticker" href="/stock?ticker=${encodeURIComponent(link)}">${title}</a>`:`<span class="ticker">${title}</span>`}<div class="small">${tickerText}${x.instrument_exchange?' · '+esc(x.instrument_exchange):''}</div>${x.quote_error?'<div class="quoteWarn">Livekurs utilgjengelig</div>':''}</td><td><span class="pill typeBadge">${esc(x.asset_class||'Aksjer')}</span></td><td>${esc(x.broker)}<div class="small">${esc(x.account_type)}</div></td><td>${num(x.shares)}</td><td>${kr(x.average_cost)}</td><td>${kr(x.current_price)}${native}</td><td>${kr(x.market_value)}</td><td class="lotMainResult ${cls(x.unrealized_pnl)}">${x.unrealized_pnl==null?'—':(Number(x.unrealized_pnl)>=0?'+':'')+kr(x.unrealized_pnl)}<div>${x.unrealized_pnl_pct==null?'—':(Number(x.unrealized_pnl_pct)>=0?'+':'')+pct(x.unrealized_pnl_pct)}</div></td><td>${pct(x.portfolio_weight_pct)}</td><td><div class="actions" style="margin:0"><button class="btn compact lotToggle" onclick="togglePurchaseLots(${Number(x.id)})"><b>${open?'−':'+'}</b> Kjøp${count?` (${count})`:''}</button>${count?'' : `<button class="btn edit compact" onclick="editHoldingById(${Number(x.id)})">Rediger</button>`}<button class="btn danger compact" onclick="delHolding(${Number(x.id)})">Slett</button></div></td></tr>`;
      return main+(open?detailRow(x):'');
    }).join('');
    $('tableHost').innerHTML=`<div class="tablewrap"><table class="table"><thead><tr><th>Instrument</th><th>Type</th><th>Megler/konto</th><th>Antall</th><th>Snitt NOK</th><th>Kurs NOK</th><th>Verdi</th><th>Resultat</th><th>Andel</th><th></th></tr></thead><tbody>${body}</tbody></table></div>`;
  };

  window.togglePurchaseLots=function(id){id=Number(id);if(expanded.has(id)){expanded.delete(id);if(activeAddId===id)activeAddId=null}else expanded.add(id);if(lastSnapshot)renderHoldingsTable(lastSnapshot.items||[])};
  window.toggleAddPurchase=function(id){id=Number(id);expanded.add(id);activeAddId=activeAddId===id?null:id;if(lastSnapshot)renderHoldingsTable(lastSnapshot.items||[])};
  window.initializePurchaseLots=async function(id){const input=$('lotInitDate'+Number(id)),purchase_date=input?.value;if(!purchase_date){alert('Velg kjøpsdato først.');return}try{await request(`/holdings/${Number(id)}/purchases/initialize`,{method:'POST',body:JSON.stringify({purchase_date})});expanded.add(Number(id));await loadHoldings()}catch(e){alert(e.message)}};
  window.savePurchaseLot=async function(id){id=Number(id);const purchase_date=$('lotDate'+id)?.value,shares=Number($('lotShares'+id)?.value),price_nok=Number($('lotPrice'+id)?.value),note=$('lotNote'+id)?.value?.trim()||null;if(!purchase_date||!Number.isFinite(shares)||shares<=0||!Number.isFinite(price_nok)||price_nok<=0){alert('Fyll inn kjøpsdato, antall og kjøpspris.');return}try{await request(`/holdings/${id}/purchases`,{method:'POST',body:JSON.stringify({purchase_date,shares,price_nok,note})});expanded.add(id);activeAddId=null;await loadHoldings()}catch(e){alert(e.message)}};
  window.deletePurchaseLot=async function(purchaseId,holdingId){if(!confirm('Slette denne kjøpslinjen? Total antall og snittpris beregnes på nytt.'))return;try{await request(`/holdings/purchases/${Number(purchaseId)}`,{method:'DELETE'});expanded.add(Number(holdingId));await loadHoldings()}catch(e){alert(e.message)}};

  // The inline page starts its first load before this enhancement arrives. Refresh
  // once so existing positions immediately receive purchase-lot data and controls.
  if(typeof loadHoldings==='function')loadHoldings();
})();
