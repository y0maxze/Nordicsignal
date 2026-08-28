(function(){
  const ticker=(new URLSearchParams(location.search).get('ticker')||'').toUpperCase().replace(/\.OL$/,'');
  const esc=v=>String(v??'—').replace(/[&<>\"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));
  const pct=v=>v==null?'—':(Number(v)>0?'+':'')+Number(v).toLocaleString('no-NO',{maximumFractionDigits:2})+'%';
  const hit=v=>v==null?'—':Number(v).toLocaleString('no-NO',{maximumFractionDigits:1})+'%';
  const sampleLabel=n=>Number(n||0)<20?'for lite grunnlag':Number(n||0)<50?'tidlig historikk':'bedre historikk';

  function styles(){
    if(document.getElementById('nsEvidenceStyles'))return;
    const s=document.createElement('style');s.id='nsEvidenceStyles';s.textContent=`
      .nsEvidence{margin-bottom:14px}.nsEvidenceHead{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap}.nsEvidenceGrid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:14px 0}.nsEvidenceMetric{background:#0a1727;border:1px solid var(--line);border-radius:10px;padding:12px}.nsEvidenceMetric span{display:block;color:var(--m);font-size:10px}.nsEvidenceMetric b{display:block;font-size:18px;margin-top:5px}.nsEvidenceMeta{font-size:10px;color:var(--m);margin-top:5px}.nsEvidenceTable{width:100%;border-collapse:collapse}.nsEvidenceTable th,.nsEvidenceTable td{padding:9px 7px;border-bottom:1px solid var(--line);text-align:left}.nsEvidenceTable th{font-size:10px;color:var(--m)}.nsEvidenceGood{color:var(--g)}.nsEvidenceBad{color:var(--r)}.nsEvidenceWarn{color:#e7c16b}@media(max-width:700px){.nsEvidenceGrid{grid-template-columns:1fr}.nsEvidenceTable{font-size:11px}}
    `;document.head.appendChild(s);
  }

  function metric(h,label){
    const x=h||{},n=Number(x.directional_n??x.n??0),rate=x.directional_hit_rate_pct;
    const cls=n<20?'nsEvidenceWarn':rate>=60?'nsEvidenceGood':rate<45?'nsEvidenceBad':'nsEvidenceWarn';
    return `<div class="nsEvidenceMetric"><span>${esc(label)}</span><b class="${cls}">${hit(rate)} treff</b><div class="nsEvidenceMeta">Median ${pct(x.median_return_pct)} · N=${esc(n)} · ${esc(sampleLabel(n))}</div></div>`;
  }

  function render(d){
    const root=document.getElementById('nsSignalEvidence');if(!root)return;
    const sum=d?.summary||{},overall=sum.overall||{},h=overall.horizons||{},groups=sum.by_event||[];
    const maturity=sum.maturity==='useful_history'?'Mer historikk':sum.maturity==='early'?'Tidlig historikk':'Lite datagrunnlag';
    root.innerHTML=`<div class="nsEvidenceHead"><div><h2 style="margin:0">NordicSignal signal-evidens · ${esc(ticker)}</h2><div class="muted">Historisk replay av samme trend-/aktivitetsregler som brukes i Latest Signals.</div></div><button class="btn" id="nsEvidenceRefresh">Oppdater historikk</button></div><div class="notice" style="margin-top:12px"><b>${esc(maturity)} · ${esc(sum.sample_count||0)} signalhendelser</b><br>Treffrate betyr at kursretningen etter signalet samsvarte med signalretningen. N under 20 behandles som for lite datagrunnlag og får aldri sterk grønn markering. Dette er backtest, ikke garanti for fremtidig avkastning.</div><div class="nsEvidenceGrid">${metric(h['5'],'5 børsdager')}${metric(h['20'],'20 børsdager')}${metric(h['60'],'60 børsdager')}</div>${groups.length?`<div class="tablewrap"><table class="nsEvidenceTable"><thead><tr><th>Signaltype</th><th>N</th><th>5d treff</th><th>20d treff</th><th>60d treff</th><th>20d median</th></tr></thead><tbody>${groups.slice(0,8).map(g=>{const gh=g.horizons||{};return `<tr><td><b>${esc(g.event)}</b><div class="muted">${esc(sampleLabel(g.sample_count))}</div></td><td>${esc(g.sample_count)}</td><td>${hit(gh['5']?.directional_hit_rate_pct)} · N=${esc(gh['5']?.directional_n??0)}</td><td>${hit(gh['20']?.directional_hit_rate_pct)} · N=${esc(gh['20']?.directional_n??0)}</td><td>${hit(gh['60']?.directional_hit_rate_pct)} · N=${esc(gh['60']?.directional_n??0)}</td><td>${pct(gh['20']?.median_return_pct)}</td></tr>`}).join('')}</tbody></table></div>`:''}<div class="muted" style="margin-top:10px">Kilde: ${esc(d.source)} · ${esc(d.period_years)} års dagshistorikk · ${esc(d.method)}</div>`;
    const b=document.getElementById('nsEvidenceRefresh');if(b)b.onclick=()=>load(true);
  }

  async function load(refresh=false){
    const root=document.getElementById('nsSignalEvidence');if(!root||!ticker)return;
    root.innerHTML='<div class="notice">Beregner historisk signal-evidens…</div>';
    try{
      const r=await fetch('/api/signal-evidence/'+encodeURIComponent(ticker)+'?years=2'+(refresh?'&refresh=true':''),{cache:'no-store'}),d=await r.json().catch(()=>({}));
      if(!r.ok)throw Error(d.detail||('HTTP '+r.status));render(d);
    }catch(e){root.innerHTML=`<div class="notice">Signal-evidens er midlertidig utilgjengelig: ${esc(e.message)}</div>`}
  }

  function attach(){
    if(!ticker||typeof window.backtest!=='function'||window.backtest.__nsEvidenceWrapped)return;
    styles();const original=window.backtest;
    function wrapped(){const result=original.apply(this,arguments);setTimeout(()=>{const c=document.getElementById('content');if(!c)return;if(!document.getElementById('nsSignalEvidence'))c.insertAdjacentHTML('afterbegin','<section id="nsSignalEvidence" class="card nsEvidence"><div class="notice">Laster signal-evidens…</div></section>');load(false)},0);return result}
    wrapped.__nsEvidenceWrapped=true;window.backtest=wrapped;
  }
  attach();setTimeout(attach,150);
})();
