const ANALYSIS_API = "https://nordicsignal-api.onrender.com";

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
  if(x?.partial_live) return "Fundamentals, valuation and sentiment are live; insider activity is not included.";
  return "Score is based on stored data.";
}

async function loadScoreAnalysis(ticker){
  const box=document.getElementById("scoreAnalysis");
  if(!box) return;
  box.innerHTML='<div class="notice">Loading score verification…</div>';
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
    const shortPct=shortData.short_percent_float==null?"—":(Number(shortData.short_percent_float)*100).toFixed(2)+"%";
    const insiderItems=insider.items||[];
    const insiderSignal=insider.signal||"unavailable";
    const insiderClass=insiderSignal==="buying"?"g":insiderSignal==="selling"?"r":"y";

    box.innerHTML=`
      <div class="toolbar"><div><h2>Why this score?</h2><div class="sub">${scoreBadge(v)} · ${coverageLabel(v)}</div></div><div class="value">${v.score??'—'} / 100</div></div>
      <div class="notice"><strong>${esc(scoreSourceText(v))}</strong><br>The score remains on a 0–100 scale. Coverage tells you how much of the scoring model is currently verified by live data.${v.coverage?.verified_points<100?`<br><strong>${100-(v.coverage?.verified_points||0)} points are not yet verified.</strong>`:''}</div>
      <div class="grid">
        <section class="section"><h3>Model reasoning</h3>${reasons}</section>
        <section class="section"><h3>Score components</h3><div class="metrics">
          <div class="metric"><div class="label">Fundamentals</div><b>${v.components?.fundamentals??'—'}/40</b></div>
          <div class="metric"><div class="label">Insider</div><b>${v.components?.insider==null?'—':v.components.insider+'/25'}</b></div>
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
        </div><div class="sub" style="margin-top:12px">Insider source: ${esc(insider.source||"Unavailable")} · Short source: ${esc(shortData.source||"Unavailable")}</div></section>
      </div>
      ${insiderItems.length?`<section class="section" style="margin-top:17px"><div class="toolbar"><h3>Recent insider disclosures</h3><span class="sub">${insiderItems.length} found</span></div>${insiderItems.slice(0,5).map(item=>`<div class="signal"><strong class="${item.transaction_type==='buy'?'g':item.transaction_type==='sell'?'r':'y'}">${esc(item.transaction_type||'other')}</strong><div class="sub">${esc(item.title||'Primary insider disclosure')} · ${esc(item.trade_date||'Date unavailable')}</div>${item.shares?`<div class="small">${Number(item.shares).toLocaleString('no-NO')} shares${item.price?` · NOK ${Number(item.price).toLocaleString('no-NO')}`:''}</div>`:''}</div>`).join('')}</section>`:""}
      <div class="sub" style="margin-top:14px">Data freshness: ${v.updated_at?esc(new Date(v.updated_at).toLocaleString('no-NO')):'—'}</div>`;
  }catch(e){box.innerHTML='<div class="notice">Score analysis temporarily unavailable.</div>';console.error(e)}
}

const originalShowStock=window.showStock;
window.showStock=async function(t){
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
