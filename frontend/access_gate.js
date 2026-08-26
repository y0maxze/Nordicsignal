(function(){
  const POLICY_VERSION='NS-RISK-2026-08-26-1';
  const KEY='nordicsignal_policy_acceptance';
  const path=location.pathname.replace(/\/+$/,'')||'/';
  if(path==='/legal'||path==='/legal.html')return;

  function accepted(){
    try{const row=JSON.parse(localStorage.getItem(KEY)||'null');return row&&row.version===POLICY_VERSION&&row.accepted===true}catch{return false}
  }
  if(accepted())return;

  function mount(){
    if(document.getElementById('nsRiskGate'))return;
    const style=document.createElement('style');
    style.id='nsRiskGateStyle';
    style.textContent=`
      .nsRiskGate{position:fixed;inset:0;z-index:2147483647;background:rgba(0,0,0,.88);backdrop-filter:blur(7px);display:flex;align-items:center;justify-content:center;padding:20px;font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif}
      .nsRiskGateCard{width:min(620px,100%);background:#0d0d0d;border:1px solid #343434;border-radius:14px;padding:24px;color:#f4f4f4;box-shadow:0 30px 90px rgba(0,0,0,.7)}
      .nsRiskGateLogo{font-weight:850;font-size:19px;letter-spacing:-.04em}.nsRiskGateLogo span{color:#18c984}.nsRiskGateCard h2{font-size:23px;margin:18px 0 8px}.nsRiskGateCard p{color:#aaa;line-height:1.55;margin:8px 0}.nsRiskGateWarn{border:1px solid #4b3b24;background:#15110b;border-radius:10px;padding:12px 13px;margin:16px 0;color:#d9c7a3!important}.nsRiskGateCheck{display:flex;gap:10px;align-items:flex-start;border:1px solid #2d2d2d;background:#090909;border-radius:10px;padding:13px;margin-top:14px;cursor:pointer}.nsRiskGateCheck input{margin-top:3px;accent-color:#f2f2f2}.nsRiskGateCheck span{font-size:12px;line-height:1.5;color:#d4d4d4}.nsRiskGateActions{display:flex;gap:8px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-top:17px}.nsRiskGateLink{color:#aaa;text-decoration:underline;text-underline-offset:3px;font-size:11px}.nsRiskGateBtn{border:1px solid #ededed;background:#ededed;color:#090909;border-radius:9px;padding:10px 14px;font-weight:760;cursor:pointer}.nsRiskGateBtn:disabled{opacity:.35;cursor:not-allowed}.nsRiskGateMeta{color:#666;font-size:9px;margin-top:13px}
    `;
    document.head.appendChild(style);
    const gate=document.createElement('div');gate.id='nsRiskGate';gate.className='nsRiskGate';
    gate.innerHTML=`<div class="nsRiskGateCard" role="dialog" aria-modal="true" aria-labelledby="nsRiskTitle"><div class="nsRiskGateLogo">Nordic<span>Signal</span></div><h2 id="nsRiskTitle">Før du bruker NordicSignal</h2><p>NordicSignal analyserer markedsdata, nyheter og modeller, men gir ikke personlig investeringsrådgivning og kan ikke garantere at data eller analyser er riktige.</p><p class="nsRiskGateWarn"><b>Investering innebærer risiko.</b> Du kan tape deler av eller hele beløpet du investerer. Score, AI-brief, Investment Readiness og backtester er beslutningsstøtte — ikke en garanti eller ordre om å kjøpe eller selge.</p><label class="nsRiskGateCheck"><input id="nsRiskAccept" type="checkbox"><span>Jeg har lest og forstått risikoen, forstår at jeg selv er ansvarlig for investeringsbeslutninger, og godtar NordicSignals vilkår og ansvarsbegrensning.</span></label><div class="nsRiskGateActions"><a class="nsRiskGateLink" href="/legal" target="_blank" rel="noopener">Les full policy og vilkår</a><button id="nsRiskContinue" class="nsRiskGateBtn" disabled>Godta og fortsett</button></div><div class="nsRiskGateMeta">Policy ${POLICY_VERSION}. Du blir bedt om å godta på nytt dersom policyversjonen endres.</div></div>`;
    document.body.appendChild(gate);
    const checkbox=document.getElementById('nsRiskAccept'),button=document.getElementById('nsRiskContinue');
    const oldOverflow=document.documentElement.style.overflow;document.documentElement.style.overflow='hidden';
    checkbox.onchange=()=>{button.disabled=!checkbox.checked};
    button.onclick=()=>{
      if(!checkbox.checked)return;
      try{localStorage.setItem(KEY,JSON.stringify({version:POLICY_VERSION,accepted:true,accepted_at:new Date().toISOString()}))}catch{}
      gate.remove();document.documentElement.style.overflow=oldOverflow;
    };
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
})();
