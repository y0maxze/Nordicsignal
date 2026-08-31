const API_ORIGIN = "https://nordicsignal-api.onrender.com";

const ASSET_ROUTES = new Map([
  ["/", "/index.html"],
  ["/app", "/index.html"],
  ["/app/", "/index.html"],
  ["/dashboard", "/index.html"],
  ["/dashboard/", "/index.html"],
  ["/mobile", "/mobile.html"],
  ["/mobile/", "/mobile.html"],
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
  ["/holdings", "/holdings.html"],
  ["/holdings/", "/holdings.html"],
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
  ["/learning", "/learning.html"],
  ["/learning/", "/learning.html"],
  ["/signal-performance", "/learning.html"],
  ["/signal-performance/", "/learning.html"],
  ["/development", "/development.html"],
  ["/development/", "/development.html"],
  ["/legal", "/legal.html"],
  ["/legal/", "/legal.html"],
  ["/frontend", "/index.html"],
  ["/frontend/", "/index.html"],
]);

const THEME_LINK = '<link rel="stylesheet" href="/theme.css">';
const PWA_HEAD = '<link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="#070707"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><meta name="apple-mobile-web-app-title" content="NordicSignal">';
const GLOBAL_HOME_UI = '<a class="nsGlobalHome" href="/app" aria-label="Til NordicSignal dashboard" title="Til dashboard">Nordic<span>Signal</span></a>';
const STOCK_EXTRAS = '<script src="/stock_selector.js"></script><script src="/stock_data_bridge.js"></script><script src="/stock_extras.js"></script><script src="/stock_readiness.js"></script><script src="/stock_evidence_ui.js"></script><script src="/stock_opportunity_ui.js"></script>';
const LEARNING_EXTRAS = '<script src="/learning_version_ui.js"></script><script src="/learning_shadow_ui.js"></script><script src="/learning_scan_audit_ui.js"></script><script src="/learning_failure_streak_ui.js"></script><script src="/learning_sandbox_ui.js"></script>';
const MOBILE_SHELL = '<script src="/mobile_shell.js"></script><script src="/mobile_learning_nav.js"></script>';
const ACCESS_GATE = '<script src="/access_gate.js"></script>';
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
  return pathname;
}

function isApiPath(pathname) { return pathname.startsWith('/api/'); }
function isHtmlPath(pathname) { return ASSET_ROUTES.has(pathname); }

async function proxyApi(request, env) {
  const incoming = new URL(request.url);
  const target = new URL(incoming.pathname + incoming.search, API_ORIGIN);
  const headers = new Headers(request.headers);
  headers.set('host', target.host);
  if (env?.NORDICSIGNAL_WRITE_TOKEN && !headers.has('x-nordicsignal-token')) headers.set('x-nordicsignal-token', env.NORDICSIGNAL_WRITE_TOKEN);
  return fetch(new Request(target, {method:request.method,headers,body:['GET','HEAD'].includes(request.method)?undefined:request.body,redirect:'follow'}));
}

async function serveAsset(request, env, pathname) {
  const assetResponse = await env.ASSETS.fetch(assetRequest(request, assetPath(pathname)));
  if (!isHtmlPath(pathname) || !assetResponse.ok) return assetResponse;
  let html = await assetResponse.text();
  if (!html.includes('/theme.css')) html = html.replace('</head>', THEME_LINK + PWA_HEAD + '</head>');
  if (!html.includes('nsGlobalHome')) html = html.replace('<body>', '<body>' + GLOBAL_HOME_UI);
  if (pathname === '/stock' || pathname === '/stock/' || pathname === '/stock-intelligence' || pathname === '/stock-intelligence/') html = html.replace('</body>', STOCK_EXTRAS + '</body>');
  if (pathname === '/learning' || pathname === '/learning/' || pathname === '/signal-performance' || pathname === '/signal-performance/') html = html.replace('</body>', LEARNING_EXTRAS + '</body>');
  if (!html.includes('/mobile_shell.js')) html = html.replace('</body>', MOBILE_SHELL + ACCESS_GATE + '</body>');
  return new Response(html,{status:assetResponse.status,headers:applySecurityHeaders(new Headers(assetResponse.headers))});
}

async function handleRequest(request, env) {
  const url = new URL(request.url);
  if (isApiPath(url.pathname)) return proxyApi(request, env);
  return serveAsset(request, env, url.pathname);
}

async function handleScheduled(env) {
  const headers = new Headers({'content-type':'application/json'});
  if (env?.NORDICSIGNAL_WRITE_TOKEN) headers.set('x-nordicsignal-token', env.NORDICSIGNAL_WRITE_TOKEN);
  try {
    await fetch(`${API_ORIGIN}/api/opportunity-scan/run`, {method:'POST',headers});
  } catch (_) {}
}

export default {
  fetch: handleRequest,
  scheduled(_event, env, _ctx) { return handleScheduled(env); },
};
