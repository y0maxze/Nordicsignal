export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Keep the public routes stable even if HTML handling settings change.
    const aliases = {
      "/paper": "/paper.html",
      "/paper/": "/paper.html",
      "/paper-trading": "/paper.html",
      "/paper-trading/": "/paper.html",
      "/app": "/index.html",
      "/app/": "/index.html",
    };

    const assetPath = aliases[url.pathname];
    if (assetPath) {
      url.pathname = assetPath;
      return env.ASSETS.fetch(new Request(url, request));
    }

    return env.ASSETS.fetch(request);
  },
};
