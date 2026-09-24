import "./frontend/brand_config.js";

const API_ORIGIN = "https://nordicsignal-api.onrender.com";
const BRAND = globalThis.NORDICSIGNAL_BRAND;

const ASSET_ROUTES = new Map([
  ["/", "/home.html"],
  ["/home", "/home.html"],
  ["/home/", "/home.html"],
  ["/app", "/index.html"],
  ["/app/", "/index.html"],
  ["/dashboard", "/index.html"],
  ["/dashboard/", "/index.html"],
  ["/mobile", "/index.html"],
  ["/mobile/", "/index.html"],
  ["/morning", "/morning.html"],
  ["/morning/", "/morning.html"],
  ["/alerts", "/alerts.html"],
  ["/alerts/", "/alerts.html"],
  ["/notifications", "/alerts.html"],
  ["/notifications/", "/alerts.html"],
  ["/capital-flow", "/capital-flow.html"],
  ["/capital-flow/", "/capital-flow.html"],
  ["/insider", "/insider.html"],
  ["/insider/", "/insider.html"],
  ["/stock", "/stock.html"],
  ["/stock/", "/stock.html"],
  ["/stock-intelligence", "/stock.html"],
  ["/stock-intelligence/", "/stock.html"],
  ["/intelligence", "/intelligence.html"],
  ["/intelligence/", "/intelligence.html"],
  ["/instrument", "/instrument.html"],
  ["/instrument/", "/instrument.html"],

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
  ["/research", "/learning.html"],
  ["/research/", "/learning.html"],

  ["/legal", "/legal.html"],
  ["/legal/", "/legal.html"],
  ["/frontend", "/index.html"],
  ["/frontend/", "/index.html"],
]);

const REMOVED_PRODUCT_ROUTES = new Set([
  "/paper", "/paper/", "/paper-trading", "/paper-trading/",
  "/development", "/development/",
  "/holdings", "/holdings/", "/frontend/holdings.html",
  "/portfolio", "/portfolio/", "/holdings.html", "/portfolio.html", "/frontend/portfolio.html", "/mobile.html", "/frontend/mobile.html",
]);

const THEME_LINK = '<link rel="stylesheet" href="/theme.css">';
const BRAND_CONFIG = '<script src="/brand_config.js"></script>';
const PWA_HEAD = `<link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="${BRAND.themeDark}"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><meta name="apple-mobile-web-app-title" content="${BRAND.appleTitle}">`;
const BRAND_STYLE = `<style id="nsBrandMarkStyle">.logo{display:inline-flex!important;align-items:center!important;gap:0!important;font-size:0!important;color:#eef7ff!important}.logo span{display:none!important}.logo:before{content:"";display:block;width:34px;height:34px;flex:0 0 34px;margin-right:10px;background:url("${BRAND.mark}") center/contain no-repeat;filter:drop-shadow(0 0 10px rgba(25,167,255,.42))}.logo:after{content:"${BRAND.label}";font-size:16px;line-height:1;letter-spacing:.08em;font-weight:820;color:#eef7ff}.nsGlobalHome{display:inline-flex!important;align-items:center!important}</style>`;
const GLOBAL_HOME_UI = `<a class="nsGlobalHome" href="/app" aria-label="Til ${BRAND.name} dashboard" title="Til dashboard"><img src="${BRAND.mark}" alt="" width="23" height="23" style="display:block;margin-right:7px">${BRAND.label}</a>`;
const STOCK_EXTRAS = '<script src="/stock_selector.js"></script><script src="/stock_data_bridge.js"></script><script src="/stock_extras.js"></script><script src="/stock_evidence_ui.js"></script>';
const LEARNING_EXTRAS = '<script src="/learning_version_ui.js"></script><script src="/learning_shadow_ui.js"></script><script src="/learning_smart_money_ui.js"></script><script src="/learning_temporal_ui.js"></script><script src="/learning_scan_audit_ui.js"></script><script src="/learning_failure_streak_ui.js"></script><script src="/learning_sandbox_ui.js"></script>';
const MOBILE_SHELL = '<script src="/alert_local_capture.js"></script><script src="/mobile_shell.js"></script><script src="/mobile_learning_nav.js"></script><script src="/alert_nav_ui.js"></script>';
const ACCESS_GATE = '';
const SECURITY_HEADERS = {
  "x-content-type-options":"nosniff",
  "referrer-policy":"strict-origin-when-cross-origin",
  "permissions-policy":"camera=(), microphone=(), geolocation=()",
  "x-frame-options":"DENY",
};

function assetRequest(request, pathname) {
  const url = new URL(request.url);
  url.pathname = pathname;
  return new Request(url, request);
}

function applySecurityHeaders(headers) {
  for (const [key,value] of Object.entries(SECURITY_HEADERS)) headers.set(key,value);
  return headers;
}

function json(body, status = 200) {
  const headers=applySecurityHeaders(new Headers({"content-type":"application/json; charset=utf-8","cache-control":"no-store"}));
  return new Response(JSON.stringify(body), {status,headers});
}

function assetPath(pathname) {
  if (ASSET_ROUTES.has(pathname)) return ASSET_ROUTES.get(pathname);
  if (pathname.startsWith("/frontend/")) return pathname.slice("/frontend".length);
  return pathname;
}

function isStockEntry(pathname) {
  return pathname === "/stock" || pathname === "/stock/" || pathname === "/stock-intelligence" || pathname === "/stock-intelligence/";
}

function ensureSharedScript(html, src) {
  if (html.includes(`src="${src}"`)) return html;
  return html.replace("</body>", `<script src="${src}"></script></body>`);
}

function enhanceHtml(html, pathname) {
  if (pathname === "/home.html") return html;
  if (!html.includes('href="/theme.css"')) html = html.replace("</head>", `${THEME_LINK}</head>`);
  if (!html.includes('src="/brand_config.js"')) html = html.replace("</head>", `${BRAND_CONFIG}</head>`);
  if (!html.includes('id="nsBrandMarkStyle"')) html = html.replace("</head>", `${BRAND_STYLE}</head>`);
  if (!html.includes('rel="manifest"')) html = html.replace("</head>", `${PWA_HEAD}</head>`);
  if (pathname === "/index.html") {
    const navExtras = '<a href="/morning">Før børs</a>'; 
    if (!html.includes('href="/morning"')) html = html.replace("</nav>", `${navExtras}</nav>`);
  } else if (pathname !== "/legal.html" && !html.includes('class="nsGlobalHome"')) {
    html = html.replace("<body>", `<body>${GLOBAL_HOME_UI}`);
  }
  if (pathname === "/stock.html" && !html.includes('src="/stock_selector.js"')) {
    html = html.replace("</body>", `${STOCK_EXTRAS}</body>`);
  }
  if (pathname === "/learning.html" && !html.includes('src="/learning_version_ui.js"')) {
    html = html.replace("</body>", `${LEARNING_EXTRAS}</body>`);
  }
  html = ensureSharedScript(html, "/theme_mode.js");
  html = ensureSharedScript(html, "/ui_shell.js");
  html = ensureSharedScript(html, "/mobile_nav.js");
  if (!html.includes('src="/mobile_shell.js"')) {
    html = html.replace("</body>", `${['/index.html','/stock.html','/morning.html'].includes(pathname)?'<script src="/mobile_shell.js"></script>':MOBILE_SHELL}</body>`);
  }
  return html;
}

async function serveAsset(request, env, pathname) {
  const response = await env.ASSETS.fetch(assetRequest(request, pathname));
  if (request.method === "HEAD" || !response.ok) return response;
  const type = response.headers.get("content-type") || "";
  if (!type.includes("text/html")) return response;
  const html = enhanceHtml(await response.text(), pathname);
  const headers = applySecurityHeaders(new Headers(response.headers));
  headers.delete("content-length");
  headers.set("cache-control", "no-store");
  return new Response(html, {status:response.status, headers});
}

async function proxyApi(request, url, env) {
  const upstream = new URL(`${API_ORIGIN}${url.pathname}`);
  upstream.search = url.search;
  try {
    // Never allow the public proxy to act as an unauthenticated write-token relay.
    // Scheduled jobs use the backend directly with the existing secret.
    const mutates = !['GET','HEAD','OPTIONS'].includes(request.method) || url.pathname === '/api/refresh' || url.pathname.endsWith('/refresh') || url.searchParams.get('refresh') === 'true';
    if (/^\/api\/(holdings|portfolio|watchlist|purchases|alerts|notifications|dashboard-home)(\/|$)/.test(url.pathname)) return json({status:'error',code:'PRIVATE_READ_ACCESS_REQUIRED'},403);
    if (mutates) return json({status:'error',code:'PRIVATE_WRITE_ACCESS_REQUIRED',message:'Private authenticated write access is required'},403);
    const headers = new Headers(request.headers);
    headers.delete('x-nordicsignal-internal-token');
    if (env && env.NORDICSIGNAL_WRITE_TOKEN) {
      headers.set("x-nordicsignal-internal-token", env.NORDICSIGNAL_WRITE_TOKEN);
    }
    const forwarded = new Request(upstream.toString(), request);
    const secured = new Request(forwarded, {headers});
    const response = await fetch(new Request(secured, {signal:AbortSignal.timeout(30000)}));
    const responseHeaders = applySecurityHeaders(new Headers(response.headers));
    responseHeaders.delete("access-control-allow-origin");
    responseHeaders.set("cache-control", "no-store");
    return new Response(response.body, {status:response.status, headers:responseHeaders});
  } catch (error) {
    return json({status:"error",code:"API_UPSTREAM_UNAVAILABLE",message:"Backend is temporarily unavailable"},502);
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!env || !env.ASSETS || typeof env.ASSETS.fetch !== "function") {
      return json({status:"error",code:"ASSETS_BINDING_MISSING",message:"Cloudflare ASSETS binding is not available in this deployment.",path:url.pathname},500);
    }
    if (url.pathname === "/api/paper" || url.pathname.startsWith("/api/paper/")) {
      return json({status:"removed",code:"FEATURE_REMOVED",message:"Paper trading and product backtesting are no longer part of NordicSignal."},410);
    }
    if (url.pathname.startsWith("/api/")) return proxyApi(request, url, env);
    if (request.method !== "GET" && request.method !== "HEAD") return json({status:"error",code:"METHOD_NOT_ALLOWED"},405);
    if (REMOVED_PRODUCT_ROUTES.has(url.pathname)) {
      return Response.redirect(new URL("/app", url), 302);
    }
    let pathname = assetPath(url.pathname);
    if (isStockEntry(url.pathname) && !url.searchParams.get("ticker") && !url.searchParams.get("symbol")) pathname = "/intelligence.html";
    return serveAsset(request, env, pathname);
  },
};
