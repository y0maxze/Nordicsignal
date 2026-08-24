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

async function loadScoreAnalysis(ticker){
  const box=document.getElementById("scoreAnalysis");
  if(!box) return;
  box.innerHTML='<div class="notice">Loading score explanation…</div>';
  try{
    const [explanation, fundamentals, verification]=await Promise.all([
      fetch(ANALYSIS_API+"/api/score-explanation/"+encodeURIComponent(ticker)).then(r=>r.json()),
      fetch(ANALYSIS_API+"/api/fundamentals/"+encodeURIComponent(ticker)).then(r=>r.json()),
      fetch(ANALYSIS_API+"/api/verification").then(r=>r.json())
    ]);
    const v=(verification.items||[]).find(x=>x.ticker===ticker);
    const reasons=(explanation.reasons||[]).map(r=>`<div class="signal"><strong class="${r.type==='positive'?'g':'y'}">${r.type==='positive'?'✓':'⚠'} ${esc(r.text)}</strong></div>`).join('') || '<div class="notice">No additional explanation available yet.</div>';
    const d=fundamentals.data||{};
    const money=n=>n==null?'—':(Math.abs(n)>=1e9?(n/1e9).toFixed(2)+'B':Math.abs(n)>=1e6?(n/1e6).toFixed(0)+'M':Number(n).toLocaleString('no-NO'))+' NOK';
    const verified=v?.coverage?.verified_points ?? 0;
    const total=v?.coverage?.total_points ?? 100;
    box.innerHTML=`
      <div class="toolbar"><div><h2>Why this score?</h2><div class="sub">${scoreBadge(v)} · ${coverageLabel(v)}</div></div><div class="value">${v?.score ?? '—'} / ${verified}</div></div>
      <div class="notice">The verified score uses only data currently available to the model. Insider activity is excluded until a reliable live source is connected. ${verified<total?`<br><strong>${total-verified} points are not yet verified.</strong>`:''}</div>
      <div class="grid">
        <section class="section"><h3>Model reasoning</h3>${reasons}</section>
        <section class="section"><h3>Live fundamentals</h3>
          <div class="metrics">
            <div class="metric"><div class="label">Revenue</div><b>${money(d.revenue)}</b></div>
            <div class="metric"><div class="label">EBITDA</div><b>${money(d.ebitda)}</b></div>
            <div class="metric"><div class="label">Free cash flow</div><b>${money(d.free_cashflow)}</b></div>
            <div class="metric"><div class="label">Debt</div><b>${money(d.debt)}</b></div>
            <div class="metric"><div class="label">EPS</div><b>${d.eps==null?'—':Number(d.eps).toFixed(2)+' NOK'}</b></div>
            <div class="metric"><div class="label">Net income</div><b>${money(d.net_income)}</b></div>
            <div class="metric"><div class="label">Equity</div><b>${money(d.equity)}</b></div>
            <div class="metric"><div class="label">Operating cash flow</div><b>${money(d.operating_cashflow)}</b></div>
          </div>
        </section>
      </div>`;
  }catch(e){box.innerHTML='<div class="notice">Score analysis temporarily unavailable.</div>';console.error(e)}
}

const originalShowStock=window.showStock;
window.showStock=async function(t){
  await originalShowStock(t);
  const x=universe.find(a=>a.ticker===t);
  if(!x) return;
  const host=document.querySelector("#appview .section");
  if(!host) return;
  const metrics=host.querySelector(".metrics");
  const analysis=document.createElement("div");
  analysis.id="scoreAnalysis";
  analysis.style.marginTop="22px";
  if(metrics) metrics.insertAdjacentElement("afterend",analysis); else host.appendChild(analysis);
  loadScoreAnalysis(t);
};