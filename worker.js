const API_ORIGIN = "https://nordicsignal-api.onrender.com";

const ASSET_ROUTES = new Map([
  ["/", "/index.html"],
  ["/app", "/index.html"],
  ["/app/", "/index.html"],
  ["/dashboard", "/index.html"],
  ["/dashboard/", "/index.html"],
  ["/paper", "/paper.html"],
  ["/paper/", "/paper.html"],
  ["/paper-trading", "/paper.html"],
  ["/paper-trading/", "/paper.html"],
  ["/history", "/history.html"],
  ["/history/", "/history.html"],
]);

function assetRequest(request, pathname) {
  const url = new URL(request.url);
  url.pathname = pathname;
  url.search = new URL(request.url).search;
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

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // This Worker is deliberately the routing layer for the multi-page
    // frontend. Static assets remain in ./frontend and are served through
    // the ASSETS binding. Keeping this explicit avoids relying on implicit
    // HTML rewrites for /app, /paper and /history.
    if (!env || !env.ASSETS || typeof env.ASSETS.fetch !== "function") {
      return json({
        status: "error",
        code: "ASSETS_BINDING_MISSING",
        message: "Cloudflare ASSETS binding is not available in this deployment.",
        path: url.pathname,
      }, 500);
    }

    if (request.method !== "GET" && request.method !== "HEAD") {
      // The frontend API is hosted by Render. Do not accidentally turn
      // mutation requests into static-asset requests.
      if (url.pathname.startsWith("/api/")) {
        return fetch(`${API_ORIGIN}${url.pathname}${url.search}`, request);
      }
      return json({ status: "error", code: "METHOD_NOT_ALLOWED" }, 405);
    }

    if (url.pathname.startsWith("/api/")) {
      // Keep the Worker usable as the public gateway as well. The current
      // frontend still uses the Render origin directly, but this makes API
      // routes available from the same NordicSignal host.
      const upstream = new URL(`${API_ORIGIN}${url.pathname}`);
      upstream.search = url.search;
      const response = await fetch(upstream.toString(), request);
      const headers = new Headers(response.headers);
      headers.set("access-control-allow-origin", "*");
      return new Response(response.body, { status: response.status, headers });
    }

    const target = ASSET_ROUTES.get(url.pathname) || url.pathname;
    return env.ASSETS.fetch(assetRequest(request, target));
  },
};
