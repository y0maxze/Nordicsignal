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
  ["/frontend", "/index.html"],
  ["/frontend/", "/index.html"],
]);

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
  // Older frontend code used /frontend/<asset>. Keep those URLs working even
  // though ./frontend is the configured asset root and therefore the public
  // asset URL is /<asset>.
  if (pathname.startsWith("/frontend/")) return pathname.slice("/frontend".length);
  return pathname;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (!env || !env.ASSETS || typeof env.ASSETS.fetch !== "function") {
      return json({
        status: "error",
        code: "ASSETS_BINDING_MISSING",
        message: "Cloudflare ASSETS binding is not available in this deployment.",
        path: url.pathname,
      }, 500);
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
        return json({ status: "error", code: "API_UPSTREAM_UNAVAILABLE", message: String(error) }, 502);
      }
    }

    if (request.method !== "GET" && request.method !== "HEAD") {
      return json({ status: "error", code: "METHOD_NOT_ALLOWED" }, 405);
    }

    return env.ASSETS.fetch(assetRequest(request, assetPath(url.pathname)));
  },
};
