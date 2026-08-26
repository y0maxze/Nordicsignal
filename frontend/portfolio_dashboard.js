(function(){
  const esc=v=>String(v==null?'':v).replace(/[&<>\"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));
  const nok=v=>v==null?'—':Number(v).toLocaleString('no-NO',{maximumFractionDigits:0})+' kr';
  const pct=v=>v==null?'—':(Number(v)>=0?'+':'')+Number(v).toLocaleString('no-NO',{maximumFractionDigits:2})+'%';

  function styles(){
    if(document.getElementById('nsPortfolioHomeStyles'))return;
    const s=document.createElement('style');s.id='nsPortfolioHomeStyles';s.textContent=`
      .nsHomeWrap{margin-top:22px}.nsHomeCards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:16px}
      .nsHomeCard,.nsHomePanel{background:#101010;border:1px solid #282828;border-radius:12px}.nsHomeCard{padding:17px 18px}.nsHomeCard .k{color:#8d8d8d;font-size:11px}.nsHomeCard .v{font-size:24px;font-weight:850;margin-top:5px;letter-spacing:-.02em}.nsHomeCard .m{color:#777;font-size:10px;margin-top:5px}
      .nsHomeGrid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(330px,.75fr);gap:16px}.nsHomePanel{padding:18px}.nsHomeHead{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:12px}.nsHomeHead h2{margin:0;font-size:17px}.nsHomeHead p{margin:4px 0 0;color:#858585;font-size:11px}.nsHomeLink{color:#d8d8d8;font-size:11px;text-decoration:none;border:1px solid #303030;border-radius:8px;padding:7px 9px;white-space:nowrap}.nsHomeLink:hover{border-color:#555;color:#fff}
      .nsHoldingRow{display:grid;grid-template-columns:minmax(160px,1.4fr) .85fr .7fr .55fr;gap:12px;align-items:center;padding:13px 2px;border-top:1px solid #242424;cursor:pointer}.nsHoldingRow:first-of-type{border-top:0}.nsHoldingRow:hover .nsHoldingName{color:#35d49a}.nsHoldingName{font-weight:800}.nsTicker{display:block;color:#747474;font-size:10px;margin-top:3px}.nsRight{text-align:right}.nsPos{color:#35d49a}.nsNeg{color:#fb7185}.nsWeight{height:4px;background:#242424;border-radius:99px;margin-top:6px;overflow:hidden}.nsWeight i{display:block;height:100%;background:#717171;border-radius:99px}
      .nsEvent{display:block;padding:13px 0;border-top:1px solid #242424;text-decoration:none;color:#eee}.nsEvent:first-of-type{border-top:0}.nsEvent:hover .nsEventTitle{color:#fff}.nsEventTop{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.nsEventTicker{font-size:10px;font-weight:850;color:#bdbdbd}.nsEventBadge{font-size:9px;font-weight:900;letter-spacing:.03em;padding:3px 6px;border-radius:999px;border:1px solid #393939;color:#aaa}.nsEventBadge.report{color:#e7c16b;border-color:#554923;background:#17150c}.nsEventBadge.buy{color:#35d49a;border-color:#24503f;background:#0d1814}.nsEventBadge.sell{color:#fb7185;border-color:#5b2b34;background:#1b0f12}.nsEventBadge.important{color:#ffcb73;border-color:#624824;background:#1c160d}.nsEventTitle{font-weight:750;font-size:12px;margin-top:7px;line-height:1.35}.nsEventMeta{color:#777;font-size:10px;margin-top:4px}.nsEmptyHome{padding:28px 18px;text-align:center;color:#888}.nsEmptyHome b{display:block;color:#eee;font-size:16px;margin-bottom:7px}.nsHomeSkeleton{padding:24px;color:#888;background:#101010;border:1px solid #282828;border-radius:12px}
      @media(max-width:1050px){.nsHomeCards{grid-template-columns:repeat(2,1fr)}.nsHomeGrid{grid-template-columns:1fr}}
      @media(max-width:650px){.nsHomeCards{grid-template-columns:1fr}.nsHoldingRow{grid-template-columns:1fr .8fr .65fr}.nsHoldingRow>:nth-child(4){display:none}.nsHomePanel{padding:15px}}
    `;document.head.appendChild(s);
  }

  function eventLabel(x){
    if(x.kind==='report')return ['RAPPORT','report'];
    if(x.kind==='insider'&&x.direction==='buy')return ['INSIDER KJØP','buy'];
    if(x.kind==='insider'&&x.direction==='sell')return ['INSIDER SALG','sell'];
    if(x.kind==='insider')return ['INSIDER',''];
    if(x.kind==='dividend')return ['UTBYTTE',''];
    return [String(x.category||'HENDELSE').toUpperCase(),''];
  }
  function eventHref(x){
    const tab=x.kind==='report'?'reports':x.kind==='insider'?'insider':x.kind==='dividend'?'dividend':'news';
    return '/stock?ticker='+encodeURIComponent(x.ticker||'')+'&tab='+tab;
  }
  function dateLabel(x){
    if(!x.occurred_at)return 'Dato ikke oppgitt';
    try{return new Date(x.occurred_at).toLocaleDateString('no-NO',{day:'2-digit',month:'short',year:'numeric'})}catch{return x.occurred_at}
  }

  function holdingRows(items){
    const sorted=[...items].sort((a,b)=>Number(b.market_value||0)-Number(a.market_value||0)).slice(0,8);
    if(!sorted.length)return '<div class="nsEmptyHome"><b>Ingen aksjer i beholdningen ennå</b>Legg inn aksjene dine, så blir forsiden automatisk tilpasset dem.</div>';
    return sorted.map(x=>{
      const pnl=x.unrealized_pnl,cls=pnl==null?'':Number(pnl)>=0?'nsPos':'nsNeg',weight=Math.max(0,Math.min(100,Number(x.portfolio_weight_pct||0)));
      return `<div class="nsHoldingRow" data-ns-holding="${esc(x.ticker)}"><div><span class="nsHoldingName">${esc(x.company_name||x.ticker)}</span><span class="nsTicker">${esc(x.ticker)} · ${esc(x.account_type||'')}</span></div><div class="nsRight"><b>${nok(x.market_value)}</b><div class="nsWeight"><i style="width:${weight}%"></i></div></div><div class="nsRight ${cls}"><b>${nok(pnl)}</b><span class="nsTicker">${pct(x.unrealized_pnl_pct)}</span></div><div class="nsRight"><b>${Number(x.portfolio_weight_pct||0).toLocaleString('no-NO',{maximumFractionDigits:1})}%</b><span class="nsTicker">vekt</span></div></div>`
    }).join('');
  }

  function eventRows(items){
    const list=(items||[]).slice(0,10);
    if(!list.length)return '<div class="nsEmptyHome"><b>Ingen viktige hendelser akkurat nå</b>Når en aksje i beholdningen får rapport, insiderhandel eller viktig børsmelding, vises den her.</div>';
    return list.map(x=>{const [label,cls]=eventLabel(x),important=x.importance==='high'?'<span class="nsEventBadge important">VIKTIG</span>':'';return `<a class="nsEvent" href="${eventHref(x)}"><div class="nsEventTop"><span class="nsEventTicker">${esc(x.ticker)}</span><span class="nsEventBadge ${cls}">${esc(label)}</span>${important}</div><div class="nsEventTitle">${esc(x.title)}</div><div class="nsEventMeta">${esc(x.company||x.ticker)} · ${esc(dateLabel(x))}</div></a>`}).join('');
  }

  async function renderPortfolioHome(){
    styles();
    if(typeof setTitle==='function')setTitle('Min oversikt','Beholdning og viktige hendelser på ett sted');
    const view=document.getElementById('appview');if(!view)return;
    view.innerHTML='<div class="nsHomeWrap"><div class="nsHomeSkeleton">Laster beholdning og hendelser…</div></div>';
    try{
      const [hRes,eRes]=await Promise.all([
        fetch('/api/holdings',{cache:'no-store'}),
        fetch('/api/holdings/events?limit=16',{cache:'no-store'})
      ]);
      const holdings=await hRes.json().catch(()=>({})),events=await eRes.json().catch(()=>({}));
      if(!hRes.ok)throw Error(holdings.detail||'Beholdning kunne ikke hentes');
      const summary=holdings.summary||{},items=holdings.items||[],eventItems=eRes.ok?(events.items||[]):[];
      const pnl=summary.unrealized_pnl,pnlCls=pnl==null?'':Number(pnl)>=0?'nsPos':'nsNeg';
      view.innerHTML=`<div class="nsHomeWrap"><section class="nsHomeCards"><div class="nsHomeCard"><div class="k">Porteføljeverdi</div><div class="v">${nok(summary.market_value)}</div><div class="m">${esc(summary.position_count||0)} posisjoner</div></div><div class="nsHomeCard"><div class="k">Urealisert resultat</div><div class="v ${pnlCls}">${nok(pnl)}</div><div class="m ${pnlCls}">${pct(summary.unrealized_pnl_pct)}</div></div><div class="nsHomeCard"><div class="k">Viktige hendelser</div><div class="v">${esc(events.high_priority_count||0)}</div><div class="m">Rapport / insider / større melding</div></div><div class="nsHomeCard"><div class="k">Aksjer med pris</div><div class="v">${esc(summary.priced_count||0)} / ${esc(summary.position_count||0)}</div><div class="m">Live markedsverdi der kurs finnes</div></div></section><div class="nsHomeGrid"><section class="nsHomePanel"><div class="nsHomeHead"><div><h2>Min beholdning</h2><p>Største posisjoner først</p></div><a class="nsHomeLink" href="/frontend/holdings.html">Administrer beholdning</a></div>${holdingRows(items)}</section><section class="nsHomePanel"><div class="nsHomeHead"><div><h2>Mine hendelser</h2><p>Kun aksjer du faktisk eier</p></div></div>${eventRows(eventItems)}</section></div></div>`;
      view.querySelectorAll('[data-ns-holding]').forEach(el=>el.onclick=()=>{const t=el.dataset.nsHolding;if(typeof showStock==='function')showStock(t);else location.href='/stock?ticker='+encodeURIComponent(t)});
    }catch(e){
      console.error(e);view.innerHTML='<div class="nsHomeWrap"><div class="nsHomeSkeleton">Min oversikt kunne ikke lastes akkurat nå. De andre NordicSignal-sidene fungerer fortsatt som før.</div></div>';
    }
  }

  function install(){
    styles();
    const dashboardLink=document.querySelector('#nav a[data-page="Dashboard"]');if(dashboardLink)dashboardLink.textContent='Min oversikt';
    window.renderDashboard=renderPortfolioHome;
    // init() may have rendered the legacy dashboard before this deferred script loaded.
    const active=document.querySelector('#nav a.active');if(!active||active.dataset.page==='Dashboard')renderPortfolioHome();
  }
  install();
})();
