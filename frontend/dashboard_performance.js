(function(){
  async function sameOriginGet(path){
    const r=await fetch(path,{cache:'no-store'});
    if(!r.ok)throw Error(path+' failed ('+r.status+')');
    return r.json();
  }

  async function mapLimit(items,limit,mapper){
    const source=Array.isArray(items)?items:[],out=new Array(source.length);
    let next=0;
    async function worker(){
      while(true){
        const i=next++;
        if(i>=source.length)return;
        out[i]=await mapper(source[i],i);
      }
    }
    const workers=Array.from({length:Math.min(Math.max(1,limit),source.length)},()=>worker());
    await Promise.all(workers);
    return out;
  }

  function shortPressure(d,p){
    const level=String(d?.short_alert_level||'').toLowerCase();
    if(level==='high')return ['High','r'];
    if(level==='elevated')return ['Elevated','y'];
    if(level==='easing')return ['Easing','g'];
    if(p==null)return ['No public position',''];
    if(Number(p)>=3)return ['High','r'];
    if(Number(p)>=1)return ['Elevated','y'];
    return ['Low','g'];
  }

  function escLocal(v){return typeof esc==='function'?esc(v):String(v??'—').replace(/[&<>\"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]))}
  function n0(v){return v==null?'—':Number(v).toLocaleString('no-NO',{maximumFractionDigits:0})}
  function compactMoney(v,currency){
    if(v==null)return '—';
    const n=Number(v),abs=Math.abs(n),prefix=n<0?'−':'';
    let amount;
    if(abs>=1e9)amount=(abs/1e9).toLocaleString('no-NO',{maximumFractionDigits:2})+' mrd.';
    else if(abs>=1e6)amount=(abs/1e6).toLocaleString('no-NO',{maximumFractionDigits:2})+' mill.';
    else if(abs>=1e3)amount=(abs/1e3).toLocaleString('no-NO',{maximumFractionDigits:1})+'k';
    else amount=abs.toLocaleString('no-NO',{maximumFractionDigits:0});
    return prefix+amount+' '+(currency||'');
  }
  function dateOnly(v){return v?String(v).slice(0,10):'—'}
  function pulseValue(p){
    const values=p?.values||[];
    if(!values.length)return '—';
    return values.map(x=>{
      const buy=x.buy||0,sell=x.sell||0;
      if(buy&&sell)return compactMoney(buy,x.currency)+' kjøp / '+compactMoney(sell,x.currency)+' salg';
      if(buy)return compactMoney(buy,x.currency);
      if(sell)return compactMoney(sell,x.currency);
      return '—';
    }).join(' · ');
  }
  function pulseTone(p){return p?.tone==='positive'?'g':p?.tone==='negative'?'r':'y'}
  function companyCell(p){
    const name=escLocal(p?.company||p?.ticker||'Ukjent selskap'),ticker=String(p?.ticker||'').trim();
    if(ticker)return `<strong class="stock" onclick="showStock('${escLocal(ticker)}')">${name}</strong><div class="sub">${escLocal(ticker)}</div>`;
    return `<strong>${name}</strong><div class="sub">Ticker ikke identifisert i feed</div>`;
  }
  function activityLabel(x){
    const map={share_purchase:'ORDINÆRT KJØP',share_sale:'ORDINÆRT SALG',internal_transfer:'INTERN OVERFØRING',rights_or_derivatives:'RETTIGHETER / OPSJON',employee_program:'ANSATTPROGRAM',award:'TILDELING',details_pending:'DETALJER VENTER',other_disclosure:'ANNEN MELDING'};
    return map[x?.activity_type]||'ANNEN MELDING';
  }
  function activityTone(x){
    if(x?.signal_eligible&&x?.direction==='buy')return 'g';
    if(x?.signal_eligible&&x?.direction==='sell')return 'r';
    return 'y';
  }
  function actorName(x){return x?.person||x?.entity||x?.insider||(x?.details_pending?'Venter på detaljdata':'Ikke oppgitt')}
  function actualValue(x){
    if(x?.display_value==null)return '—';
    return compactMoney(x.display_value,x.currency)+(x.value_basis==='reported_transaction_price'?'<div class="small">rapportert kurs</div>':'');
  }

  let insiderPulseTimer=null;
  let insiderDays=14;

  function insiderShell(){
    return `<section class="cards" id="insiderStats"><div class="card"><div class="label">Ordinære handler</div><div class="value">—</div><div class="sub">verifiserte kjøp/salg</div></div><div class="card"><div class="label">Klyngekjøp</div><div class="value g">—</div><div class="sub">flere kjøpere i samme selskap</div></div><div class="card"><div class="label">Innsidersalg</div><div class="value r">—</div><div class="sub">ordinære salg</div></div><div class="card"><div class="label">Insidermeldinger</div><div class="value y">—</div><div class="sub">offisielle meldinger funnet</div></div></section><section class="section" style="margin-bottom:17px"><div class="toolbar"><div><h2 style="margin:0">Insider Pulse</h2><div class="sub">Hele Oslo Børs · Euronext Newspoint · oppdateres automatisk</div></div><div class="controls"><button class="btn ${insiderDays===7?'active':''}" data-insider-days="7">7d</button><button class="btn ${insiderDays===14?'active':''}" data-insider-days="14">14d</button><button class="btn ${insiderDays===30?'active':''}" data-insider-days="30">30d</button><button class="btn" id="insiderRefreshBtn">Oppdater</button></div></div><div class="notice">NordicSignal bruker Euronext-listen som bekreftelse på at en primærinsiderhendelse finnes. Kjøp/salg blir først signal når navn, retning og transaksjonsdata er verifisert. Blokkerte detaljsider vises som «Detaljer venter» i stedet for å forsvinne.</div><div id="insiderPulseHost"><div class="notice">Laster ferske innsidermeldinger fra hele Oslo Børs…</div></div></section><section class="section"><div class="toolbar"><div><h2 style="margin:0">Siste insidermeldinger</h2><div class="sub">Verifiserte handler og offisielle hendelser som venter på detaljberikelse</div></div></div><div id="insiderActivityHost"><div class="notice">Laster…</div></div></section>`;
  }

  function bindInsiderControls(){
    document.querySelectorAll('[data-insider-days]').forEach(btn=>btn.onclick=()=>{
      insiderDays=Number(btn.dataset.insiderDays)||14;
      renderInsider();
    });
    const refresh=document.getElementById('insiderRefreshBtn');
    if(refresh)refresh.onclick=()=>loadInsiderMarket(true);
  }

  function renderInsiderStats(d){
    const stats=document.getElementById('insiderStats');if(!stats)return;
    const pulses=d.pulses||[],items=d.items||[];
    const clusters=pulses.filter(x=>x.flags?.includes('cluster_buying')).length;
    const sells=items.filter(x=>x.signal_eligible&&x.direction==='sell').length;
    const disclosures=Number(d.disclosure_count??items.length??0);
    const pending=Number(d.pending_detail_count||0);
    stats.innerHTML=`<div class="card"><div class="label">Ordinære handler</div><div class="value">${escLocal(d.eligible_trade_count||0)}</div><div class="sub">verifiserte kjøp/salg</div></div><div class="card"><div class="label">Klyngekjøp</div><div class="value g">${clusters}</div><div class="sub">flere kjøpere i samme selskap</div></div><div class="card"><div class="label">Innsidersalg</div><div class="value r">${sells}</div><div class="sub">ordinære salg</div></div><div class="card"><div class="label">Insidermeldinger</div><div class="value y">${escLocal(disclosures)}</div><div class="sub">${pending?escLocal(pending)+' venter på detaljer':'alle funn behandlet'}</div></div>`;
  }

  function renderPulseTable(d){
    const host=document.getElementById('insiderPulseHost');if(!host)return;
    const rows=(d.pulses||[]).filter(x=>x.buy_count||x.sell_count).slice(0,30);
    if(!rows.length){
      const pending=Number(d.pending_detail_count||0);
      host.innerHTML=pending?`<div class="notice">${escLocal(pending)} offisielle primærinsidermeldinger er funnet. Transaksjonsdetaljene berikes nå og vises i listen under.</div>`:'<div class="notice">Ingen ordinære verifiserte insiderkjøp eller -salg funnet i valgt periode.</div>';
      return;
    }
    host.innerHTML=`<table class="table"><thead><tr><th>Selskap</th><th>Signal</th><th>Aktører</th><th>Kjøp / salg</th><th>Rapportert verdi</th><th>Siste</th></tr></thead><tbody>${rows.map(p=>`<tr><td>${companyCell(p)}</td><td><strong class="${pulseTone(p)}">${escLocal(p.signal_label||'AKTIVITET')}</strong>${p.flags?.includes('large_buy')?'<div class="small g">stort rapportert kjøp</div>':''}</td><td>${(p.actors||[]).slice(0,3).map(escLocal).join('<br>')||'—'}${(p.actors||[]).length>3?`<div class="small">+${p.actors.length-3} flere</div>`:''}</td><td><span class="g">${escLocal(p.buy_count||0)} kjøp</span><br><span class="r">${escLocal(p.sell_count||0)} salg</span></td><td>${escLocal(pulseValue(p))}</td><td>${escLocal(dateOnly(p.latest_date))}${p.url?`<div><a href="${escLocal(p.url)}" target="_blank" rel="noopener" class="small">Original</a></div>`:''}</td></tr>`).join('')}</tbody></table>`;
  }

  function renderActivityTable(d){
    const host=document.getElementById('insiderActivityHost');if(!host)return;
    const items=(d.items||[]).slice(0,60);
    if(!items.length){host.innerHTML='<div class="notice">Ingen ferske insidermeldinger funnet.</div>';return}
    host.innerHTML=`<table class="table"><thead><tr><th>Dato</th><th>Selskap</th><th>Aktør</th><th>Type</th><th>Antall</th><th>Pris</th><th>Verdi</th><th>Kilde</th></tr></thead><tbody>${items.map(x=>`<tr><td>${escLocal(dateOnly(x.trade_date||x.date||x.published_at))}</td><td>${x.ticker?`<strong class="stock" onclick="showStock('${escLocal(x.ticker)}')">${escLocal(x.company||x.ticker)}</strong><div class="sub">${escLocal(x.ticker)}</div>`:`<strong>${escLocal(x.company||'Ukjent')}</strong>`}</td><td><strong>${escLocal(actorName(x))}</strong><div class="sub">${escLocal(x.role||'—')}</div></td><td><span class="${activityTone(x)}"><strong>${escLocal(activityLabel(x))}</strong></span>${x.details_pending?'<div class="small">offisiell Euronext-hendelse · berikelse venter</div>':!x.signal_eligible?'<div class="small">ikke brukt som handelssignal</div>':''}</td><td>${escLocal(n0(x.shares))}</td><td>${x.price==null?'—':escLocal(Number(x.price).toLocaleString('no-NO',{maximumFractionDigits:4})+' '+(x.currency||''))}</td><td>${actualValue(x)}</td><td>${x.url?`<a href="${escLocal(x.url)}" target="_blank" rel="noopener">Euronext</a>`:'—'}</td></tr>`).join('')}</tbody></table>`;
  }

  async function loadInsiderMarket(force){
    const pulse=document.getElementById('insiderPulseHost');
    try{
      const d=await sameOriginGet('/api/insider-market?limit=80&days='+encodeURIComponent(insiderDays)+(force?'&refresh=true':''));
      renderInsiderStats(d);renderPulseTable(d);renderActivityTable(d);
    }catch(e){
      if(pulse)pulse.innerHTML='<div class="notice">Insider Pulse er midlertidig utilgjengelig. Eksisterende Stock Intelligence-data påvirkes ikke.</div>';
      const activity=document.getElementById('insiderActivityHost');if(activity)activity.innerHTML='<div class="notice">Kunne ikke hente markedsfeed akkurat nå.</div>';
      console.warn('insider market feed unavailable',e);
    }
  }

  window.renderInsider=async function(){
    setTitle('Insider Pulse','Market-wide primary-insider activity from Euronext Oslo Børs');
    appview.innerHTML=insiderShell();bindInsiderControls();
    await loadInsiderMarket(false);
    if(insiderPulseTimer)clearInterval(insiderPulseTimer);
    insiderPulseTimer=setInterval(()=>{
      const title=document.getElementById('title');
      if(!document.hidden&&title&&title.textContent==='Insider Pulse')loadInsiderMarket(false);
    },120000);
  };

  window.renderShort=async function(){
    setTitle('Short Radar','Public net short positions from Finanstilsynet');
    appview.innerHTML='<section class="section"><h2>Short Radar</h2><div class="notice">Loading the official Short Sale Register…</div><div id="shortTable"></div></section>';
    const out=await mapLimit(universe,5,async x=>{
      try{return {x,d:await sameOriginGet('/api/short/'+encodeURIComponent(x.ticker))}}
      catch{return {x,d:{status:'unavailable'}}}
    });
    const host=document.getElementById('shortTable');if(!host)return;
    host.innerHTML=`<table class="table"><thead><tr><th>Company</th><th>Short % float</th><th>Short shares</th><th>Pressure</th><th>Latest</th></tr></thead><tbody>${out.map(o=>{const d=o.d||{},p=d.short_percent_float,[pressure,cls]=shortPressure(d,p);return `<tr><td><strong class="stock" onclick="showStock('${escLocal(o.x.ticker)}')">${escLocal(o.x.name)}</strong><div class="sub">${escLocal(o.x.ticker)}</div></td><td>${p==null?'—':Number(p).toFixed(2)+'%'}</td><td>${d.shares==null?'—':Number(d.shares).toLocaleString('no-NO')}</td><td class="${cls}">${pressure}</td><td>${escLocal(d.latest_date||'—')}</td></tr>`}).join('')}</tbody></table>`;
  };
})();
