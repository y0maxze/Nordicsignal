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

  function insiderAction(item){
    const side=String(item?.transaction_type||item?.direction||'').toLowerCase();
    if(side==='buy')return ['KJØP','g'];
    if(side==='sell')return ['SALG','r'];
    return ['ANNET','y'];
  }

  window.renderInsider=async function(){
    setTitle('Insider Activity','Recent primary-insider disclosures from Euronext Oslo Børs');
    appview.innerHTML='<section class="section"><h2>Insider Activity</h2><div class="notice">Loading live regulatory disclosures…</div><div id="insiderTable"></div></section>';
    const out=await mapLimit(universe,5,async x=>{
      try{return {x,d:await sameOriginGet('/api/insider/'+encodeURIComponent(x.ticker))}}
      catch{return {x,d:{items:[],status:'unavailable'}}}
    });
    const host=document.getElementById('insiderTable');if(!host)return;
    host.innerHTML=`<table class="table"><thead><tr><th>Company</th><th>Person / foretak</th><th>Rolle</th><th>Handling</th><th>Siste melding</th><th>Kilde</th></tr></thead><tbody>${out.map(o=>{const d=o.d||{},item=(d.items||[])[0],actor=item?(item.person||item.entity||item.insider||'Ikke oppgitt'):'—',[action,cls]=insiderAction(item);return `<tr><td><strong class="stock" onclick="showStock('${esc(o.x.ticker)}')">${esc(o.x.name)}</strong><div class="sub">${esc(o.x.ticker)}</div></td><td><strong>${esc(actor)}</strong></td><td>${esc(item?.role||'—')}</td><td class="${cls}">${item?esc(action):'—'}</td><td>${item?esc(item.title||'Primary insider disclosure'):'No recent public disclosure found'}${item?.trade_date||item?.date?`<div class="sub">${esc(item.trade_date||item.date)}</div>`:''}</td><td><span class="small">${esc(d.source||'Unavailable')}</span></td></tr>`}).join('')}</tbody></table>`;
  };

  window.renderShort=async function(){
    setTitle('Short Radar','Public net short positions from Finanstilsynet');
    appview.innerHTML='<section class="section"><h2>Short Radar</h2><div class="notice">Loading the official Short Sale Register…</div><div id="shortTable"></div></section>';
    const out=await mapLimit(universe,5,async x=>{
      try{return {x,d:await sameOriginGet('/api/short/'+encodeURIComponent(x.ticker))}}
      catch{return {x,d:{status:'unavailable'}}}
    });
    const host=document.getElementById('shortTable');if(!host)return;
    host.innerHTML=`<table class="table"><thead><tr><th>Company</th><th>Short % float</th><th>Short shares</th><th>Pressure</th><th>Latest</th></tr></thead><tbody>${out.map(o=>{const d=o.d||{},p=d.short_percent_float,[pressure,cls]=shortPressure(d,p);return `<tr><td><strong class="stock" onclick="showStock('${esc(o.x.ticker)}')">${esc(o.x.name)}</strong><div class="sub">${esc(o.x.ticker)}</div></td><td>${p==null?'—':Number(p).toFixed(2)+'%'}</td><td>${d.shares==null?'—':Number(d.shares).toLocaleString('no-NO')}</td><td class="${cls}">${pressure}</td><td>${esc(d.latest_date||'—')}</td></tr>`}).join('')}</tbody></table>`;
  };
})();
