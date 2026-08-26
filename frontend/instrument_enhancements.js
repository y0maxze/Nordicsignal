(function(){
  let analytics=null,analyticsPromise=null;
  const getInstrument=()=>{try{return instrument||{}}catch{return {}}};
  const getSymbol=()=>{try{return symbol||''}catch{return ''}};
  const isFund=()=>{const x=getInstrument();return String(x.quote_type||'').toUpperCase()==='MUTUALFUND'||x.asset_class==='Fond'};
  const fmt=(v,d=2)=>v==null||!Number.isFinite(Number(v))?'—':Number(v).toLocaleString('no-NO',{maximumFractionDigits:d});
  const pct=v=>v==null||!Number.isFinite(Number(v))?'—':`${Number(v)>=0?'+':''}${fmt(v,2)}%`;
  const cls=v=>v==null?'':Number(v)>=0?'positive':'negative';
  const html=v=>String(v==null?'':v).replace(/[&<>\"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));

  function styles(){
    if(document.getElementById('nsInstrumentEnhancementStyles'))return;
    const s=document.createElement('style');s.id='nsInstrumentEnhancementStyles';s.textContent=`
      .nsAnalytics{margin-top:14px}.nsAnalyticsGrid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:12px}.nsAnalyticsBox{background:#101010;border:1px solid #252525;border-radius:10px;padding:13px}.nsAnalyticsBox span{display:block;color:#999;font-size:11px;margin-bottom:6px}.nsAnalyticsBox b{font-size:18px}.nsQuickAmounts{display:flex;gap:7px;flex-wrap:wrap;margin:9px 0 0}.nsQuickAmounts button{padding:6px 9px}.nsFundEstimate{margin-top:10px;padding:10px 12px;border:1px solid #292929;border-radius:9px;background:#0b0b0b;color:#aaa}.nsFundEstimate b{color:#f3f3f3}.nsFundCallout{border-left:3px solid #35d99b}.nsPaperHolding{margin-top:10px;color:#aaa;font-size:12px}@media(max-width:900px){.nsAnalyticsGrid{grid-template-columns:repeat(2,1fr)}}@media(max-width:550px){.nsAnalyticsGrid{grid-template-columns:1fr}}
    `;document.head.appendChild(s);
  }

  async function loadAnalytics(){
    if(analytics)return analytics;
    if(analyticsPromise)return analyticsPromise;
    const s=getSymbol();if(!s)return null;
    analyticsPromise=fetch('/api/instrument/'+encodeURIComponent(s)+'/analytics',{cache:'no-store'}).then(async r=>{const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||('HTTP '+r.status));analytics=d;return d}).catch(e=>{console.warn('instrument analytics unavailable',e);return null});
    return analyticsPromise;
  }

  function setHeroForFund(a){
    if(!isFund()||!a)return;
    const x=getInstrument();
    const labels=[...document.querySelectorAll('.hero .metric .muted')];
    const values=[...document.querySelectorAll('.hero .metric b')];
    const rows=[['1 måned',a.return_1m_pct],['3 måneder',a.return_3m_pct],['År hittil',a.return_ytd_pct],['1 år',a.return_1y_pct],['Volatilitet 1 år',a.volatility_1y_pct]];
    rows.forEach((r,i)=>{if(labels[i])labels[i].textContent=r[0];if(values[i]){values[i].textContent=i===4?(r[1]==null?'—':fmt(r[1],2)+'%'):pct(r[1]);values[i].className=i===4?'':cls(r[1])}});
    const status=document.getElementById('status');
    if(status)status.innerHTML=`Data: <b>SISTE TILGJENGELIGE NAV/KURS</b> · Fond · kilde ${html(x.source||'Yahoo Finance')}. Fond handles normalt til ukjent kurs, så dette er ikke en sanntids børskurs.`;
    const meta=document.getElementById('priceMeta');
    if(meta)meta.textContent='Siste rapporterte NAV/kurs · fondsordre avregnes normalt senere til ukjent kurs';
  }

  function analyticsPanel(a){
    if(!a)return '<div class="notice">Utvidet historisk analyse er midlertidig utilgjengelig.</div>';
    const x=getInstrument(),fund=isFund();
    return `<section class="card nsAnalytics"><div class="toolbar"><div><h2 style="margin:0">${fund?'Fondanalyse':'Historisk analyse'}</h2><div class="muted">Beregnet direkte fra ${html(x.name||getSymbol())} sin egen pris/NAV-historikk. Dette er beskrivende statistikk, ikke et kjøpssignal.</div></div></div><div class="nsAnalyticsGrid"><div class="nsAnalyticsBox"><span>3 år annualisert</span><b class="${cls(a.cagr_3y_pct)}">${pct(a.cagr_3y_pct)}</b></div><div class="nsAnalyticsBox"><span>5 år annualisert</span><b class="${cls(a.cagr_5y_pct)}">${pct(a.cagr_5y_pct)}</b></div><div class="nsAnalyticsBox"><span>Maks fall siste år</span><b class="negative">${a.max_drawdown_1y_pct==null?'—':fmt(a.max_drawdown_1y_pct,2)+'%'}</b></div><div class="nsAnalyticsBox"><span>50 / 200 dagers trend</span><b>${a.above_sma_200==null?'—':a.above_sma_200?'Over 200d snitt':'Under 200d snitt'}</b></div></div><div class="nsAnalyticsGrid"><div class="nsAnalyticsBox"><span>52 uker høy</span><b>${fmt(a.high_52w,2)} ${html(x.currency||'')}</b></div><div class="nsAnalyticsBox"><span>52 uker lav</span><b>${fmt(a.low_52w,2)} ${html(x.currency||'')}</b></div><div class="nsAnalyticsBox"><span>50d snitt</span><b>${fmt(a.sma_50,2)} ${html(x.currency||'')}</b></div><div class="nsAnalyticsBox"><span>200d snitt</span><b>${fmt(a.sma_200,2)} ${html(x.currency||'')}</b></div></div></section>`;
  }

  async function enhanceOverview(){
    const a=await loadAnalytics();
    setHeroForFund(a);
    const content=document.getElementById('content');if(!content)return;
    const old=document.getElementById('nsInstrumentAnalytics');if(old)old.remove();
    const box=document.createElement('div');box.id='nsInstrumentAnalytics';box.innerHTML=analyticsPanel(a);content.appendChild(box);
  }

  async function renderFundPaper(){
    if(!isFund())return false;
    const x=getInstrument(),content=document.getElementById('content');if(!content)return true;
    const currency=x.currency||'NOK',price=Number(x.price);
    content.innerHTML=`<section class="card"><h2>Paper Trade · ${html(x.name||getSymbol())}</h2><div class="notice nsFundCallout"><b>Fondordre i beløp.</b> Som hos vanlige fondsplattformer oppgir du hvor mye penger du vil kjøpe eller selge for, ikke et kjent antall fondsandeler. En ekte fondsordre handles normalt til ukjent kurs. NordicSignal bruker derfor siste viste NAV/kurs til å beregne et <b>estimert</b> antall andeler i denne simuleringen.</div><form id="nsFundPaperForm" class="form"><label>Side<select id="nsFundSide"><option value="buy">Kjøp</option><option value="sell">Selg</option></select></label><label>Beløp · ${html(currency)}<input id="nsFundAmount" type="number" min="1" step="any" value="10000" required></label><label>NAV/kurs brukt i estimat<input id="nsFundNav" type="number" value="${Number.isFinite(price)?price:''}" readonly></label><label>Gebyr · ${html(currency)}<input id="nsFundFee" type="number" min="0" step="any" value="0"></label><button class="btn" type="submit">Registrer paperordre</button></form><div class="nsQuickAmounts"><button class="btn" type="button" data-amt="1000">1 000</button><button class="btn" type="button" data-amt="5000">5 000</button><button class="btn" type="button" data-amt="10000">10 000</button><button class="btn" type="button" data-amt="25000">25 000</button><button class="btn" type="button" data-amt="50000">50 000</button></div><div id="nsFundEstimate" class="nsFundEstimate"></div><div id="nsPaperHolding" class="nsPaperHolding"></div><div id="nsFundPaperStatus" class="muted" style="margin-top:10px"></div></section>`;
    const amount=document.getElementById('nsFundAmount'),estimate=document.getElementById('nsFundEstimate');
    const refreshEstimate=()=>{const a=Number(amount.value),p=Number(x.price);estimate.innerHTML=a>0&&p>0?`Estimert beholdningsendring: <b>${fmt(a/p,6)} andeler</b> ved NAV/kurs ${fmt(p,2)} ${html(currency)}. Endelig andelstall i en ekte fondsordre er ukjent når ordren legges.`:'Oppgi et gyldig beløp.'};
    amount.oninput=refreshEstimate;refreshEstimate();
    document.querySelectorAll('[data-amt]').forEach(b=>b.onclick=()=>{amount.value=b.dataset.amt;refreshEstimate()});
    try{const r=await fetch('/api/paper/portfolio',{cache:'no-store'}),d=await r.json();const pos=(d.positions||[]).find(p=>String(p.ticker||'').toUpperCase()===getSymbol().toUpperCase());const h=document.getElementById('nsPaperHolding');if(pos)h.textContent=`Nåværende paperbeholdning: ${fmt(pos.shares,6)} andeler · verdi ${fmt(pos.value,2)} ${currency}`;else h.textContent='Ingen paperbeholdning i dette fondet ennå.'}catch{}
    document.getElementById('nsFundPaperForm').onsubmit=async e=>{e.preventDefault();const status=document.getElementById('nsFundPaperStatus'),amt=Number(amount.value),fee=Number(document.getElementById('nsFundFee').value||0);if(!(amt>0)||!(price>0)){status.textContent='Beløp eller NAV/kurs er ugyldig.';return}status.textContent='Registrerer…';try{const r=await fetch('/api/paper/instrument-order',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({symbol:getSymbol(),side:document.getElementById('nsFundSide').value,amount:amt,price:price,fee:fee,currency:currency,instrument_name:x.name||getSymbol()})});const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||('HTTP '+r.status));status.textContent=`Paperordre registrert: ${fmt(d.order_amount,2)} ${currency} · ca. ${fmt(d.estimated_units,6)} andeler.`}catch(err){status.textContent='Kunne ikke registrere: '+err.message}};
    return true;
  }

  function hideIrrelevantFundTabs(){
    if(!isFund())return;
    ['insider','short'].forEach(t=>{const b=document.querySelector(`.tab[data-tab="${t}"]`);if(b){b.title='Denne datatypen er normalt ikke relevant/tilgjengelig for tradisjonelle fond';b.style.opacity='.55'}});
    const d=document.querySelector('.tab[data-tab="dividend"]');if(d)d.textContent='Utdelinger';
  }

  styles();
  try{
    const baseRender=render;
    render=async function(tab){
      if(tab==='paper'&&isFund()){tabs(tab);await renderFundPaper();return;}
      await baseRender(tab);
      hideIrrelevantFundTabs();
      if(tab==='overview')await enhanceOverview();
    };
  }catch(e){console.warn('instrument enhancement render patch unavailable',e)}
})();
