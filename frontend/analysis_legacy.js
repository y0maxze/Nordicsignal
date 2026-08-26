const ANALYSIS_API = "";

function coverageLabel(x){
  const c=x?.coverage;
  if(!c) return "Coverage unavailable";
  return `${c.verified_points}/${c.total_points} points verified`;
}

function scoreBadge(x){
  if(x?.live_verified) return '<span class="badge">LIVE VERIFIED</span>';
  if(x?.partial_live) return '<span class="badge watch">PARTIAL LIVE</span>';
  return '<span class="badge risk">STORED</span>';
}

function scoreSourceText(x){
  if(x?.live_verified) return "All scored components have a live source.";
  if(x?.partial_live) return "Live market data is being used where verified; unavailable components are excluded rather than guessed.";
  return "Score is based on stored data.";
}

function injectAnalysisStyles(){
  if(document.getElementById("ns-analysis-styles")) return;
  const style=document.createElement("style");
  style.id="ns-analysis-styles";
  style.textContent=`
    .coverage-panel{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
    .coverage-panel .coverage-count{font-size:11px;color:var(--m)}
    .status-note{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:#0a1727;margin-top:12px}
    .status-note strong{font-size:12px}
    .metric b.muted{color:var(--m)}
    .freshness{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:14px}
  `;
  document.head.appendChild(style);
}

async function loadScoreAnalysis(ticker){
  const box=document.getElementById("scoreAnalysis");
  if(!box) return;
  box.innerHTML='<div class="notice">Loading live score verification…</div>';
  try{
    const [explanation, fundamentals, verification, insider, shortData]=await Promise.all([
      fetch(ANALYSIS_API+"/api/score-explanation/"+encodeURIComponent(ticker)).then(r=>r.json()),
      fetch(ANALYSIS_API+"/api/fundamentals/"+encodeURIComponent(ticker)).then(r=>r.json()),
      fetch(ANALYSIS_API+"/api/verification").then(r=>r.json()),
      fetch(ANALYSIS_API+"/api/insider/"+encodeURIComponent(ticker)).then(r=>r.json()),
      fetch(ANALYSIS_API+"/api/short/"+encodeURIComponent(ticker)).then(r=>r.json())
    ]);

    const v=(verification.items||[]).find(x=>x.ticker===ticker)||{};
    const reasons=(explanation.reasons||[]).map(r=>`<div class="signal"><strong class="${r.type==='positive'?'g':'y'}">${r.type==='positive'?'✓':'⚠'} ${esc(r.text)}</strong></div>`).join('') || '<div class="notice">No additional model explanation is available yet.</div>';
    const d=fundamentals.data||{};
    const money=n=>{if(n==null||!Number.isFinite(Number(n)))return "—";const value=Number(n),abs=Math.abs(value);return (abs>=1e9?(value/1e9).toFixed(2)+"B":abs>=1e6?(value/1e6).toFixed(0)+"M":value.toLocaleString("no-NO",{maximumFractionDigits:2}))+" NOK"};
    const shortPct=shortData.short_percent_float==null?"—":Number(shortData.short_percent_float).toFixed(2)+"%";
    const insiderItems=insider.items||[];
    const insiderSignal=insider.signal||"unavailable";
    const insiderClass=insiderSignal==="buying"?"g":insiderSignal==="selling"?"r":"y";
    const verifiedDetails=insider.verified_detail_count??insiderItems.filter(x=>x.verified_detail).length;
    const verified=v.live_verified===true;
    const partial=v.partial_live===true;
    const verifiedPoints=v.coverage?.verified_points??0;
    const totalPoints=v.coverage?.total_points??100;

    box.innerHTML=`
      <div class="toolbar"><div><h2>Why this score?</h2><div class="coverage-panel">${scoreBadge(v)}<span class="coverage-count">${coverageLabel(v)}</span></div></div><div class="value">${v.score??'—'} / 100</div></div>
      <div class="status-note"><strong>${verified?'Fully live verified':partial?'Partial live':'Stored data'}</strong><span class="sub">${verifiedPoints}/${totalPoints} scoring points verified</span>${partial?'<span class="sub">Unavailable components are not guessed.</span>':''}</div>
      <div class="notice"><strong>${esc(scoreSourceText(v))}</strong><br>The score remains on a 0–100 scale. Coverage tells you how much of the scoring model is currently verified by live data.${verifiedPoints<totalPoints?`<br><strong>${totalPoints-verifiedPoints} points are not yet verified.</strong>`:''}</div>
      <div class="grid">
        <section class="section"><h3>Model reasoning</h3>${reasons}</section>
        <section class="section"><h3>Score components</h3><div class="metrics">
          <div class="metric"><div class="label">Fundamentals</div><b>${v.components?.fundamentals??'—'}/40</b></div>
          <div class="metric"><div class="label">Insider</div><b class="${v.components?.insider==null?'muted':''}">${v.components?.insider==null?'Unavailable':v.components.insider+'/25'}</b></div>
          <div class="metric"><div class="label">Valuation</div><b>${v.components?.valuation??'—'}/20</b></div>
          <div class="metric"><div class="label">Sentiment</div><b>${v.components?.sentiment??'—'}/15</b></div>
        </div></section>
      </div>
      <div class="grid" style="margin-top:17px">
        <section class="section"><h3>Live fundamentals</h3><div class="metrics">
          <div class="metric"><div class="label">Revenue</div><b>${money(d.revenue)}</b></div>
          <div class="metric"><div class="label">EBITDA</div><b>${money(d.ebitda)}</b></div>
          <div class="metric"><div class="label">Free cash flow</div><b>${money(d.free_cashflow)}</b></div>
          <div class="metric"><div class="label">Debt</div><b>${money(d.debt)}</b></div>
          <div class="metric"><div class="label">EPS</div><b>${d.eps==null?'—':Number(d.eps).toFixed(2)+' NOK'}</b></div>
          <div class="metric"><div class="label">Net income</div><b>${money(d.net_income)}</b></div>
          <div class="metric"><div class="label">Equity</div><b>${money(d.equity)}</b></div>
          <div class="metric"><div class="label">Operating cash flow</div><b>${money(d.operating_cashflow)}</b></div>
        </div></section>
        <section class="section"><h3>Market pressure</h3><div class="metrics">
          <div class="metric"><div class="label">Insider signal</div><b class="${insiderClass}">${esc(insiderSignal)}</b></div>
          <div class="metric"><div class="label">Recent buys</div><b>${insider.buy_count??'—'}</b></div>
          <div class="metric"><div class="label">Recent sells</div><b>${insider.sell_count??'—'}</b></div>
          <div class="metric"><div class="label">Public short %</div><b>${shortPct}</b></div>
        </div><div class="sub" style="margin-top:12px">${verifiedDetails} insider disclosures have verified trade details. Source: ${esc(insider.source||"Unavailable")}</div></section>
      </div>
      ${insiderItems.length?`<section class="section" style="margin-top:17px"><div class="toolbar"><h3>Recent insider disclosures</h3><span class="sub">${insiderItems.length} found</span></div>${insiderItems.slice(0,8).map(item=>{const dir=item.direction||item.transaction_type||'unknown';const cls=dir==='buy'?'g':dir==='sell'?'r':'y';const detail=[item.insider,item.shares!=null?Number(item.shares).toLocaleString('no-NO')+' shares':null].filter(Boolean).join(' · ');return `<div class="signal"><strong class="${cls}">${esc(dir)}</strong><div class="sub">${esc(item.title||'Primary insider disclosure')} · ${esc(item.date||item.trade_date||'Date unavailable')}</div>${detail?`<div class="small">${esc(detail)}</div>`:''}${item.summary?`<div class="small" style="margin-top:4px">${esc(item.summary)}</div>`:''}</div>`}).join('')}</section>`:""}
      <div class="freshness"><span class="sub">Data freshness: ${v.updated_at?esc(new Date(v.updated_at).toLocaleString('no-NO')):'—'}</span><span class="sub">Source state: ${verified?'LIVE':partial?'PARTIAL LIVE':'STORED'}</span></div>`;
  }catch(e){box.innerHTML='<div class="notice">Score analysis temporarily unavailable.</div>';console.error(e)}
}

const originalShowStock=window.showStock;
window.showStock=async function(t){
  injectAnalysisStyles();
  await originalShowStock(t);
  const x=universe.find(a=>a.ticker===t);
  if(!x)return;
  const host=document.querySelector("#appview .section");
  if(!host)return;
  document.getElementById("scoreAnalysis")?.remove();
  const analysis=document.createElement("div");
  analysis.id="scoreAnalysis";
  analysis.style.marginTop="22px";
  host.appendChild(analysis);
  loadScoreAnalysis(t);
};

injectAnalysisStyles();
