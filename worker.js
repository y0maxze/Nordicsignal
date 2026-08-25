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
  if (pathname !== "/index.html" && pathname !== "/stock.html") return response;

  let html = await response.text();
  if (pathname === "/index.html") {
    const navExtras = '<a href="/stock">Stock Intelligence</a><a href="/paper">Paper Trading</a>';
    if (!html.includes('href="/paper"')) html = html.replace("</nav>", `${navExtras}</nav>`);
  }
  if (pathname === "/stock.html" && !html.includes('id="pressureAlertBar"')) {
    html = html.replace("</body>", `${STOCK_PRESSURE_UI}</body>`);
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
