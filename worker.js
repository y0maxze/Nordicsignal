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
  ["/news", "/news.html"],
  ["/news/", "/news.html"],
  ["/calendar", "/calendar.html"],
  ["/calendar/", "/calendar.html"],
  ["/readiness", "/readiness.html"],
  ["/readiness/", "/readiness.html"],
  ["/investment-check", "/readiness.html"],
  ["/investment-check/", "/readiness.html"],
  ["/development", "/development.html"],
  ["/development/", "/development.html"],
  ["/legal", "/legal.html"],
  ["/legal/", "/legal.html"],
  ["/frontend", "/index.html"],
  ["/frontend/", "/index.html"],
]);

const THEME_LINK = '<link rel="stylesheet" href="/theme.css">';
const GLOBAL_HOME_UI = '<a class="nsGlobalHome" href="/app" aria-label="Til NordicSignal dashboard" title="Til dashboard">Nordic<span>Signal</span></a>';
const STOCK_EXTRAS = '<script src="/stock_extras.js"></script>';
const ACCESS_GATE = '<script src="/access_gate.js"></script>';

function assetRequest(request, pathname) {
  const url = new URL(request.url);
  url.pathname = pathname;
  return new Request(url, request);
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {"content-type":"application/json; charset=utf-8","cache-control":"no-store"},
  });
}

function assetPath(pathname) {
  if (ASSET_ROUTES.has(pathname)) return ASSET_ROUTES.get(pathname);
  if (pathname.startsWith("/frontend/")) return pathname.slice("/frontend".length);
  return pathname;
}

function enhanceHtml(html, pathname) {
  if (!html.includes('href="/theme.css"')) html = html.replace("</head>", `${THEME_LINK}</head>`);
  if (pathname === "/index.html") {
    const navExtras = '<a href="/stock">Stock Intelligence</a><a href="/readiness">Investment Check</a><a href="/paper">Paper Trading</a><a href="/news">Nyheter</a><a href="/calendar">Kalender</a><a href="/development">Development</a>';
    if (!html.includes('href="/stock"')) html = html.replace("</nav>", `${navExtras}</nav>`);
  } else if (pathname !== "/legal.html" && !html.includes('class="nsGlobalHome"')) {
    html = html.replace("<body>", `<body>${GLOBAL_HOME_UI}`);
  }
  if (pathname === "/stock.html" && !html.includes('src="/stock_extras.js"')) {
    html = html.replace("</body>", `${STOCK_EXTRAS}</body>`);
  }
  if (pathname !== "/legal.html" && !html.includes('src="/access_gate.js"')) {
    html = html.replace("</body>", `${ACCESS_GATE}</body>`);
  }
  return html;
}

async function serveAsset(request, env, pathname) {
  const response = await env.ASSETS.fetch(assetRequest(request, pathname));
  if (request.method === "HEAD" || !response.ok) return response;
  const type = response.headers.get("content-type") || "";
  if (!type.includes("text/html")) return response;
  const html = enhanceHtml(await response.text(), pathname);
  const headers = new Headers(response.headers);
  headers.delete("content-length");
  headers.set("cache-control", "no-store");
  return new Response(html, {status:response.status, headers});
}

async function proxyApi(request, url) {
  const upstream = new URL(`${API_ORIGIN}${url.pathname}`);
  upstream.search = url.search;
  try {
    const response = await fetch(upstream.toString(), request);
    const headers = new Headers(response.headers);
    headers.set("access-control-allow-origin", "*");
    headers.set("cache-control", "no-store");
    return new Response(response.body, {status:response.status, headers});
  } catch (error) {
    return json({status:"error",code:"API_UPSTREAM_UNAVAILABLE",message:String(error)},502);
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!env || !env.ASSETS || typeof env.ASSETS.fetch !== "function") {
      return json({status:"error",code:"ASSETS_BINDING_MISSING",message:"Cloudflare ASSETS binding is not available in this deployment.",path:url.pathname},500);
    }
    if (url.pathname.startsWith("/api/")) return proxyApi(request, url);
    if (request.method !== "GET" && request.method !== "HEAD") return json({status:"error",code:"METHOD_NOT_ALLOWED"},405);
    return serveAsset(request, env, assetPath(url.pathname));
  },
};