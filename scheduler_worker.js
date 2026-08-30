import appWorker from "./worker.js";

const API_ORIGIN = "https://nordicsignal-api.onrender.com";
const SCAN_PATH = "/api/opportunity-scan/run";

async function triggerOpportunityScan(env) {
  const headers = new Headers({
    "content-type": "application/json",
    "user-agent": "NordicSignal-Cloudflare-Cron/1.0",
  });
  if (env && env.NORDICSIGNAL_WRITE_TOKEN) {
    headers.set("x-nordicsignal-internal-token", env.NORDICSIGNAL_WRITE_TOKEN);
  }
  const response = await fetch(`${API_ORIGIN}${SCAN_PATH}`, {
    method: "POST",
    headers,
    body: "{}",
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(`Opportunity scheduler HTTP ${response.status}: ${detail.slice(0, 240)}`);
  }
  return response.text();
}

export default {
  fetch(request, env, ctx) {
    return appWorker.fetch(request, env, ctx);
  },

  async scheduled(controller, env, ctx) {
    ctx.waitUntil(triggerOpportunityScan(env));
  },
};
