import json
import time
from curl_cffi import requests

WORKER = "https://nordicsignal.8pnwk5r8f4.workers.dev"
RENDER = "https://nordicsignal-api.onrender.com"


def get(url, timeout=90):
    response = requests.get(url, impersonate="chrome", timeout=timeout, allow_redirects=True)
    ctype = str(response.headers.get("content-type") or "")
    body = None
    if "json" in ctype:
        try:
            body = response.json()
        except Exception:
            body = None
    return response, body


def wait_for_new_backend():
    for attempt in range(12):
        try:
            response, body = get(RENDER + "/api/system-health", timeout=30)
            if response.status_code == 200 and isinstance(body, dict):
                return response, body, attempt + 1
        except Exception:
            pass
        time.sleep(10)
    return None, None, 12


print("=== DEPLOYED STORAGE HEALTH ===")
response, health, attempts = wait_for_new_backend()
print("ATTEMPTS", attempts)
if response is None:
    print("ERROR system-health unavailable after deploy wait")
else:
    print("HTTP", response.status_code)
    print(json.dumps({
        "status": health.get("status"),
        "storage_backend": health.get("storage_backend"),
        "persistent_storage": health.get("persistent_storage"),
        "database_ok": health.get("database_ok"),
        "counts": health.get("counts"),
        "latest": health.get("latest"),
        "warnings": health.get("warnings"),
    }, ensure_ascii=False, indent=2))

print("\n=== INSIDER PULSE WINDOWS ===")
for base_name, base in (("RENDER", RENDER), ("WORKER", WORKER)):
    for days in (7, 14, 30):
        try:
            response, data = get(f"{base}/api/insider-market?limit=100&days={days}&refresh=true")
            if not isinstance(data, dict):
                print(base_name, days, "HTTP", response.status_code, "NON_JSON", response.text[:500])
                continue
            items = data.get("items") or []
            sample = [
                {
                    "date": x.get("trade_date") or x.get("date") or x.get("published_at"),
                    "company": x.get("company"),
                    "ticker": x.get("ticker"),
                    "type": x.get("activity_type"),
                    "direction": x.get("direction"),
                    "pending": x.get("details_pending"),
                }
                for x in items[:12]
            ]
            print(json.dumps({
                "endpoint": base_name,
                "days": days,
                "http": response.status_code,
                "runtime": data.get("runtime"),
                "status": data.get("status"),
                "disclosure_count": data.get("disclosure_count"),
                "eligible_trade_count": data.get("eligible_trade_count"),
                "pending_detail_count": data.get("pending_detail_count"),
                "returned_items": len(items),
                "source_meta": data.get("source_meta"),
                "sample": sample,
            }, ensure_ascii=False, indent=2))
        except Exception as exc:
            print(base_name, days, "ERROR", type(exc).__name__, repr(exc))

print("\n=== MOBILE / POLICY STATIC ASSETS ===")
checks = (
    ("app", "/app"),
    ("holdings", "/holdings"),
    ("manifest", "/manifest.webmanifest"),
    ("service_worker", "/sw.js"),
    ("mobile_shell", "/mobile_shell.js"),
    ("risk_gate", "/access_gate.js"),
    ("legal", "/legal"),
)
for name, path in checks:
    try:
        response, _ = get(WORKER + path, timeout=30)
        text = response.text
        flags = {}
        if name == "app":
            flags = {
                "manifest_injected": "manifest.webmanifest" in text,
                "mobile_shell_injected": "mobile_shell.js" in text,
                "risk_gate_injected": "access_gate.js" in text,
            }
        elif name == "risk_gate":
            flags = {
                "new_policy": "NS-RISK-2026-08-27-2" in text,
                "session_storage": "sessionStorage" in text,
            }
        elif name == "legal":
            flags = {"new_policy": "NS-RISK-2026-08-27-2" in text}
        print(name, response.status_code, response.url, len(text), json.dumps(flags))
    except Exception as exc:
        print(name, "ERROR", type(exc).__name__, repr(exc))
