const API_ORIGIN = "https://nordicsignal-api.onrender.com";

const ASSET_ROUTES = new Map([
  ["/", "/index.html"],
  ["/app", "/index.html"],
  ["/app/", "/index.html"],
  ["/dashboard", "/index.html"],
  ["/dashboard/", "/index.html"],
  ["/stock", "/stock.html"],
  ["/stock/", "/stock.html"],
  ["/stock-intelligence", "/stock.html"],
  ["/stock-intelligence/", "/stock.html"],
  ["/paper", "/paper.html"],
  ["/paper/", "/paper.html"],
  ["/paper-trading", "/paper.html"],
  ["/paper-trading/", "/paper.html"],
  ["/history", "/history.html"],
  ["/history/", "/history.html"],
  ["/frontend", "/index.html"],
  ["/frontend/", "/index.html"],
]);

const STOCK_PRESSURE_UI = `
<style>
#pressureAlertBar{margin-top:14px;display:none;gap:10px;flex-wrap:wrap}.pressureAlert{border:1px solid #294660;border-radius:10px;padding:10px 12px;background:#0a1727;min-width:250px;flex:1}.pressureAlert.long{border-color:#1f6e55;background:#09231d}.pressureAlert.short{border-color:#7a3543;background:#29131a}.pressureAlert.high{box-shadow:0 0 0 1px rgba(251,113,133,.35),0 0 18px rgba(251,113,133,.14)}.pressureAlert.long.high{box-shadow:0 0 0 1px rgba(53,212,154,.35),0 0 18px rgba(53,212,154,.14)}.pressureAlert b{display:block;margin-bottom:3px}.pressureDot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;background:#91a5bd}.pressureAlert.long .pressureDot{background:#35d49a}.pressureAlert.short .pressureDot{background:#fb7185}.pressureGrid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:14px}@media(max-width:900px){.pressureGrid{grid-template-columns:repeat(2,1fr)}}@media(max-width:550px){.pressureGrid{grid-template-columns:1fr}}
</style>
<script>
(function(){
  var api='/api';
  var t=(new URLSearchParams(location.search).get('ticker')||'LSG').toUpperCase();
  var htmlEsc=function(v){return String(v==null?'—':v).replace(/[&<>\"]/g,function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]})};
  var fmt=function(v,d){return v==null?'—':Number(v).toLocaleString('no-NO',{maximumFractionDigits:d==null?2:d})};
  var pressure=null;
  var tabs=document.querySelector('.tabs');
  if(tabs&&!tabs.querySelector('[data-tab="pressure"]')){
    var b=document.createElement('button');b.className='tab';b.dataset.tab='pressure';b.textContent='Market Pressure';tabs.appendChild(b);
    b.addEventListener('click',function(){renderPressure(true)});
  }
  var hero=document.querySelector('.hero');
  if(hero&&!document.getElementById('pressureAlertBar'))hero.insertAdjacentHTML('afterend','<div id="pressureAlertBar"></div>');
  function alertCard(a){var cls='pressureAlert '+(a.type==='long'?'long':a.type==='short'?'short':'')+' '+(a.level==='high'?'high':'');var title=a.type==='long'?'LONG-varsel':a.type==='short'?'SHORT-varsel':'Volumvarsel';return '<div class="'+cls+'"><b><span class="pressureDot"></span>🔔 '+title+'</b><span>'+htmlEsc(a.message)+'</span></div>'}
  function updateAlertBar(){var bar=document.getElementById('pressureAlertBar');if(!bar||!pressure)return;var important=(pressure.alerts||[]).filter(function(a){return a.type==='long'||a.type==='short'});bar.innerHTML=important.map(alertCard).join('');bar.style.display=important.length?'flex':'none'}
  function pressurePanel(){
    if(!pressure)return '<section class="card"><div class="notice">Laster market pressure…</div></section>';
    var s=pressure.short||{},l=pressure.long_proxy||{};
    var alerts=(pressure.alerts||[]).map(alertCard).join('')||'<div class="notice">Ingen aktive LONG/SHORT-varsler akkurat nå.</div>';
    return '<section class="card"><h2>Market Pressure · '+htmlEsc(t)+'</h2><div class="notice">LONG er en transparent proxy basert på kurs, volum og eventuell shortreduksjon. SHORT bygger på offentlig Finanstilsynet SSR. Dette er ikke en Level 2-ordrebok og viser ikke skjulte eller ventende ordre.</div><div class="pressureGrid"><div class="metric"><span class="muted">LONG proxy</span><b class="'+(l.level==='high'||l.level==='elevated'?'positive':'')+'">'+htmlEsc((l.level||'none').toUpperCase())+'</b></div><div class="metric"><span class="muted">Offentlig short</span><b>'+htmlEsc(s.short_percent_float==null?'—':fmt(s.short_percent_float)+'%')+'</b></div><div class="metric"><span class="muted">Short-endring</span><b class="'+(s.short_change_pp!=null&&s.short_change_pp>0?'negative':s.short_change_pp!=null&&s.short_change_pp<0?'positive':'')+'">'+htmlEsc(s.short_change_pp==null?'—':(s.short_change_pp>0?'+':'')+fmt(s.short_change_pp)+' pp')+'</b></div><div class="metric"><span class="muted">Volum / 20d</span><b>'+htmlEsc(pressure.volume_ratio==null?'—':fmt(pressure.volume_ratio,1)+'×')+'</b></div></div><div style="margin-top:14px">'+alerts+'</div><div class="item"><b>Pressure proxy</b><div class="muted">'+htmlEsc(pressure.pressure_text||'—')+'</div></div><div class="item"><b>Databegrensning</b><div class="muted">'+htmlEsc(pressure.order_book_note||'—')+'</div></div></section>';
  }
  function renderPressure(force){var c=document.getElementById('content');if(!c)return;if(force){document.querySelectorAll('.tab').forEach(function(x){x.classList.toggle('active',x.dataset.tab==='pressure')});c.innerHTML=pressurePanel()}}
  async function refresh(){try{var r=await fetch(api+'/market-pressure/'+encodeURIComponent(t),{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);pressure=await r.json();updateAlertBar();var active=document.querySelector('.tab.active');if(active&&active.dataset.tab==='pressure')renderPressure(true)}catch(e){console.warn('market pressure unavailable',e)}}
  refresh();setInterval(refresh,60000);
})();
</script>`;

const STOCK_INSIDER_UI = `
<style>
.insiderSummary{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:12px 0 16px}.insiderSummary .metric b{font-size:17px}.actorBadge,.sourceBadge{display:inline-block;padding:3px 7px;border-radius:999px;font-size:10px;font-weight:800;margin-left:6px}.actorBadge.person{background:#102f46;color:#83c5ff}.actorBadge.company{background:#2d2410;color:#ffd36a}.sourceBadge.disclosed{background:#0c3027;color:#35d49a}.sourceBadge.estimated{background:#30260d;color:#f5c451}.ownershipCell small{display:block;color:#91a5bd;margin-top:3px}@media(max-width:900px){.insiderSummary{grid-template-columns:repeat(2,1fr)}}@media(max-width:550px){.insiderSummary{grid-template-columns:1fr}}
</style>
<script>
(function(){
  if(typeof window.insider!=='function')return;
  var h=function(v){return String(v==null?'—':v).replace(/[&<>\"]/g,function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]})};
  var n=function(v,d){return v==null?'—':Number(v).toLocaleString('no-NO',{maximumFractionDigits:d==null?2:d})};
  var kr=function(v){return v==null?'—':Number(v).toLocaleString('no-NO',{maximumFractionDigits:2})+' kr'};
  var pct=function(v){return v==null?'—':Number(v).toLocaleString('no-NO',{minimumFractionDigits:2,maximumFractionDigits:4})+'%'};
  window.insider=function(){
    var d=(window.data&&window.data.insider)||{};
    var a=d.items||[];
    var summary='<div class="insiderSummary"><div class="metric"><span class="muted">Kjøp</span><b class="positive">'+h(d.buy_count||0)+'</b></div><div class="metric"><span class="muted">Salg</span><b class="negative">'+h(d.sell_count||0)+'</b></div><div class="metric"><span class="muted">Verifiserte handler</span><b>'+h(d.verified_detail_count||0)+'</b></div><div class="metric"><span class="muted">Kilde</span><b style="font-size:12px">'+h(d.source||'Euronext / Oslo Børs')+'</b></div></div>';
    var note='<div class="notice">Kun offentlige og verifiserbare opplysninger vises. Eierandel merkes <b>oppgitt</b> når den står direkte i meldingen, eller <b>estimert</b> når den beregnes fra oppgitt beholdning etter handel og tilgjengelig aksjetall.</div>';
    if(!a.length)return '<section class="card"><h2>Insider · hvem kjøpte og solgte?</h2>'+summary+note+'<div class="notice">Ingen detaljerte offentlige insiderhandler tilgjengelig akkurat nå.</div></section>';
    var rows=a.map(function(x){
      var actor=x.person||x.entity||x.insider||x.holder||'Ikke oppgitt i kilden';
      var actorType=x.actor_type==='company'?'company':x.actor_type==='person'?'person':'';
      var actorLabel=actorType==='company'?'FORETAK':actorType==='person'?'PERSON':'';
      var value=x.transaction_value!=null?x.transaction_value:(x.shares!=null&&x.price!=null?x.shares*x.price:null);
      var ownSource=x.ownership_pct_source||'';
      var ownBadge=ownSource==='disclosed'?'<span class="sourceBadge disclosed">OPPGITT</span>':ownSource?'<span class="sourceBadge estimated">ESTIMERT</span>':'';
      var ownNote=ownSource==='estimated_from_latest_annual_share_count'?'<small>Basert på siste tilgjengelige aksjetall</small>':'';
      return '<tr><td>'+h(x.trade_date||x.date||'—')+'</td><td><span class="pill '+(x.transaction_type==='sell'?'sell':'')+'">'+h(x.transaction_type==='buy'?'KJØP':x.transaction_type==='sell'?'SALG':'ANNET')+'</span></td><td><b>'+h(actor)+'</b>'+(actorLabel?'<span class="actorBadge '+actorType+'">'+actorLabel+'</span>':'')+'</td><td>'+h(x.role||'—')+'</td><td>'+n(x.shares,0)+'</td><td>'+kr(x.price)+'</td><td>'+kr(value)+'</td><td>'+n(x.holding_after_shares,0)+'</td><td class="ownershipCell"><b>'+pct(x.ownership_pct)+'</b>'+ownBadge+ownNote+'</td><td>'+(x.url?'<a href="'+h(x.url)+'" target="_blank" rel="noopener">Original</a>':'—')+'</td></tr>';
    }).join('');
    return '<section class="card"><h2>Insider · hvem kjøpte og solgte?</h2>'+summary+note+'<div class="tablewrap"><table><thead><tr><th>Dato</th><th>Handling</th><th>Person / foretak</th><th>Rolle</th><th>Antall</th><th>Pris</th><th>Verdi</th><th>Eier etter</th><th>Eierandel</th><th>Kilde</th></tr></thead><tbody>'+rows+'</tbody></table></div></section>';
  };
})();
</script>`;

const DASHBOARD_STOCK_ACTIONS_UI = `
<style>
#nsStockActions{margin:14px 0 18px;padding:14px;border:1px solid #20354d;border-radius:12px;background:#0a1727}#nsStockActions .nsTitle{font-weight:800;margin-bottom:10px}#nsStockActions .nsActions{display:flex;flex-wrap:wrap;gap:8px}#nsStockActions a{display:inline-flex;align-items:center;text-decoration:none;border:1px solid #294660;background:#10243a;color:#eef5ff;border-radius:9px;padding:8px 11px;font-size:12px;font-weight:700}#nsStockActions a:hover{border-color:#65a9ff;background:#17324d}
</style>
<script>
(function(){
  function detectTicker(){
    var nodes=document.querySelectorAll('.muted');
    for(var i=0;i<nodes.length;i++){
      var text=(nodes[i].textContent||'').trim();
      var m=text.match(/^([A-Z0-9.]{1,12})\s*·.*Oslo Børs/i);
      if(m)return m[1].toUpperCase();
    }
    return null;
  }
  function mount(){
    var ticker=detectTicker();
    if(!ticker)return;
    var existing=document.getElementById('nsStockActions');
    if(existing&&existing.dataset.ticker===ticker)return;
    if(existing)existing.remove();
    var headings=Array.from(document.querySelectorAll('h1,h2,h3,h4'));
    var anchor=headings.find(function(x){return /why this score|hvorfor.*score/i.test(x.textContent||'')});
    if(!anchor)return;
    var box=document.createElement('div');box.id='nsStockActions';box.dataset.ticker=ticker;
    var actions=[['Oversikt','overview'],['Nyheter','news'],['Insider','insider'],['Rapporter','reports'],['Utbytte','dividend'],['Short','short'],['Paper Trade','paper'],['Backtest','backtest'],['Market Pressure','pressure']];
    box.innerHTML='<div class="nsTitle">'+ticker+' · Aksjeverktøy</div><div class="nsActions">'+actions.map(function(a){return '<a href="/stock?ticker='+encodeURIComponent(ticker)+'&tab='+encodeURIComponent(a[1])+'">'+a[0]+'</a>'}).join('')+'</div>';
    anchor.parentNode.insertBefore(box,anchor);
  }
  var queued=false;function schedule(){if(queued)return;queued=true;setTimeout(function(){queued=false;mount()},80)}
  new MutationObserver(schedule).observe(document.documentElement,{childList:true,subtree:true,characterData:true});
  window.addEventListener('popstate',schedule);document.addEventListener('click',function(){setTimeout(schedule,120)});schedule();
})();
</script>`;

const STOCK_TAB_DEEPLINK_UI = `
<script>
(function(){
  var tab=(new URLSearchParams(location.search).get('tab')||'').toLowerCase();
  var allowed={overview:1,news:1,insider:1,reports:1,dividend:1,short:1,paper:1,backtest:1,pressure:1};
  if(!allowed[tab])return;
  var tries=0;
  var timer=setInterval(function(){
    tries++;
    var button=document.querySelector('.tab[data-tab="'+tab+'"]');
    var content=document.getElementById('content');
    if(button&&content&&content.children.length){button.click();clearInterval(timer)}
    else if(tries>80)clearInterval(timer);
  },125);
})();
</script>`;

const DASHBOARD_METRIC_UI = `
<style>
.cards>.card.nsMetricCard{cursor:pointer;transition:transform .12s ease,border-color .12s ease,background .12s ease}.cards>.card.nsMetricCard:hover,.cards>.card.nsMetricCard:focus{transform:translateY(-2px);border-color:#65a9ff;background:#10243a;outline:none}.cards>.card.nsMetricCard:after{content:'Klikk for å se liste';display:block;color:#65a9ff;font-size:10px;margin-top:8px}.nsMetricBack{margin-bottom:14px}.nsMetricEmpty{padding:14px;border:1px solid #20354d;border-radius:10px;color:#91a5bd;background:#0a1727}
.logo.nsHomeLogo{cursor:pointer}.logo.nsHomeLogo:hover{opacity:.85}
</style>
<script>
(function(){
  function setDashboardNavActive(){document.querySelectorAll('#nav a').forEach(function(a){a.classList.toggle('active',a.dataset.page==='Dashboard')})}
  function goDashboard(){setDashboardNavActive();if(typeof renderDashboard==='function')renderDashboard();else location.href='/app'}
  function metricItems(kind){
    var all=(typeof universe!=='undefined'&&Array.isArray(universe))?universe:[];
    if(kind==='strong')return all.filter(function(x){return Number(x.score)>=80});
    if(kind==='live')return all.filter(function(x){return !!x.live_verified});
    if(kind==='partial')return all.filter(function(x){return !!x.partial_live});
    return all;
  }
  function openMetric(kind,title,subtitle){
    var items=metricItems(kind);
    if(typeof setTitle==='function')setTitle(title,subtitle);
    var view=document.getElementById('appview');if(!view)return;
    var body=items.length&&typeof rows==='function'?rows(items):'<div class="nsMetricEmpty">Ingen aksjer i denne kategorien akkurat nå.</div>';
    view.innerHTML='<button class="btn nsMetricBack" id="nsMetricBack">← Tilbake til dashboard</button><section class="section"><div class="toolbar"><div><h2 style="margin:0">'+title+'</h2><div class="sub">'+items.length+' aksjer</div></div></div>'+(items.length?'<div class="row head"><span>Company</span><span>Score</span><span>Strength</span><span>Signal</span></div>':'')+body+'</section>';
    var back=document.getElementById('nsMetricBack');if(back)back.onclick=goDashboard;
  }
  function mountCards(){
    var cards=document.querySelectorAll('.cards>.card');
    if(cards.length<4)return;
    var defs=[['tracked','Alle aksjer','Hele Oslo Børs-universet som NordicSignal følger'],['strong','Strong signals','Aksjer med score ≥ 80'],['live','Live verified','Aksjer med 100/100 live-datadekning'],['partial','Partial live','Aksjer med delvis live-datadekning']];
    cards.forEach(function(card,i){if(i>3)return;card.classList.add('nsMetricCard');card.tabIndex=0;card.setAttribute('role','button');card.setAttribute('aria-label','Åpne '+defs[i][1]);card.onclick=function(){openMetric(defs[i][0],defs[i][1],defs[i][2])};card.onkeydown=function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();card.click()}}});
  }
  function mountLogo(){var logo=document.querySelector('.logo');if(!logo)return;if(logo.dataset.homeReady)return;logo.dataset.homeReady='1';logo.classList.add('nsHomeLogo');logo.title='Til dashboard';logo.setAttribute('role','link');logo.tabIndex=0;logo.onclick=goDashboard;logo.onkeydown=function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();goDashboard()}}}
  var pending=false;function mount(){if(pending)return;pending=true;setTimeout(function(){pending=false;mountCards();mountLogo()},50)}
  new MutationObserver(mount).observe(document.documentElement,{childList:true,subtree:true});mount();
})();
</script>`;

const GLOBAL_HOME_UI = `
<style>
.nsGlobalHome{position:fixed;top:12px;left:12px;z-index:9999;text-decoration:none;background:#081423;border:1px solid #20354d;border-radius:10px;padding:9px 12px;color:#eef5ff!important;font:800 14px system-ui,-apple-system,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.25)}.nsGlobalHome span{color:#35d49a}.nsGlobalHome:hover{border-color:#65a9ff;background:#10243a}@media(max-width:650px){.nsGlobalHome{position:static;display:inline-block;margin:10px 12px 0}}
</style>
<a class="nsGlobalHome" href="/app" aria-label="Til NordicSignal dashboard" title="Til dashboard">Nordic<span>Signal</span></a>`;

function assetRequest(request, pathname) {
  const url = new URL(request.url);
  url.pathname = pathname;
  return new Request(url, request);
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

function assetPath(pathname) {
  if (ASSET_ROUTES.has(pathname)) return ASSET_ROUTES.get(pathname);
  if (pathname.startsWith("/frontend/")) return pathname.slice("/frontend".length);
  return pathname;
}

async function searchUpstream(request, searchTerm) {
  const upstream = new URL(`${API_ORIGIN}/api/search`);
  upstream.searchParams.set("q", searchTerm);
  const response = await fetch(upstream.toString(), request);
  if (!response.ok) throw new Error(`Search upstream returned HTTP ${response.status}`);
  const data = await response.json();
  return { items: Array.isArray(data.items) ? data.items : [] };
}

async function serveAsset(request, env, pathname) {
  const response = await env.ASSETS.fetch(assetRequest(request, pathname));
  if (request.method === "HEAD" || !response.ok) return response;
  const type = response.headers.get("content-type") || "";
  if (!type.includes("text/html")) return response;
  const enhancedPages = new Set(["/index.html","/stock.html","/paper.html","/history.html"]);
  if (!enhancedPages.has(pathname)) return response;

  let html = await response.text();
  if (pathname === "/index.html") {
    const navExtras = '<a href="/stock">Stock Intelligence</a><a href="/paper">Paper Trading</a>';
    if (!html.includes('href="/paper"')) html = html.replace("</nav>", `${navExtras}</nav>`);
    if (!html.includes('id="nsStockActions"')) html = html.replace("</body>", `${DASHBOARD_STOCK_ACTIONS_UI}</body>`);
    if (!html.includes('nsMetricCard')) html = html.replace("</body>", `${DASHBOARD_METRIC_UI}</body>`);
  }
  if (pathname === "/stock.html") {
    if (!html.includes('id="pressureAlertBar"')) html = html.replace("</body>", `${STOCK_PRESSURE_UI}</body>`);
    if (!html.includes('class="insiderSummary"')) html = html.replace("</body>", `${STOCK_INSIDER_UI}</body>`);
    if (!html.includes('STOCK_TAB_DEEPLINK_MARKER')) html = html.replace("</body>", `${STOCK_TAB_DEEPLINK_UI.replace('<script>','<script>/* STOCK_TAB_DEEPLINK_MARKER */')}</body>`);
  }
  if (pathname !== "/index.html" && !html.includes('class="nsGlobalHome"')) {
    html = html.replace("<body>", `<body>${GLOBAL_HOME_UI}`);
  }

  const headers = new Headers(response.headers);
  headers.delete("content-length");
  headers.set("cache-control", "no-store");
  return new Response(html, { status: response.status, headers });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (!env || !env.ASSETS || typeof env.ASSETS.fetch !== "function") {
      return json({status:"error",code:"ASSETS_BINDING_MISSING",message:"Cloudflare ASSETS binding is not available in this deployment.",path:url.pathname},500);
    }

    if (url.pathname === "/api/search") {
      const q = (url.searchParams.get("q") || "").trim();
      if (!q) return json({ items: [] });
      try { return json(await searchUpstream(request, q)); }
      catch (error) { return json({status:"error",code:"API_UPSTREAM_UNAVAILABLE",message:String(error)},502); }
    }

    if (url.pathname.startsWith("/api/")) {
      const upstream = new URL(`${API_ORIGIN}${url.pathname}`);
      upstream.search = url.search;
      try {
        const response = await fetch(upstream.toString(), request);
        const headers = new Headers(response.headers);
        headers.set("access-control-allow-origin", "*");
        headers.set("cache-control", "no-store");
        return new Response(response.body, { status: response.status, headers });
      } catch (error) {
        return json({status:"error",code:"API_UPSTREAM_UNAVAILABLE",message:String(error)},502);
      }
    }

    if (request.method !== "GET" && request.method !== "HEAD") return json({status:"error",code:"METHOD_NOT_ALLOWED"},405);
    return serveAsset(request, env, assetPath(url.pathname));
  },
};