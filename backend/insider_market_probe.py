import json
import re
import time
from urllib.parse import urljoin

from curl_cffi import requests

WORKER = "https://nordicsignal.8pnwk5r8f4.workers.dev"
RENDER = "https://nordicsignal-api.onrender.com"
EURONEXT = "https://live.euronext.com/en/listview/company-press-releases-by-mkt/1061/all?field_company_press_releases_target_id%5B1081%5D=1081&page=0"


def get(url, timeout=60):
    return requests.get(url, impersonate="chrome", timeout=timeout, allow_redirects=True)


def json_get(url, timeout=60):
    response = get(url, timeout)
    try:
        return response, response.json()
    except Exception:
        return response, None


print("=== STORAGE HEALTH AFTER PURCHASE-LOT AUDIT ===")
for attempt in range(10):
    try:
        response, data = json_get(RENDER + "/api/system-health", 30)
        if response.status_code == 200 and isinstance(data, dict) and "holding_purchase_lots" in (data.get("counts") or {}):
            print(json.dumps({
                "status": data.get("status"),
                "storage_backend": data.get("storage_backend"),
                "persistent_storage": data.get("persistent_storage"),
                "database_ok": data.get("database_ok"),
                "counts": data.get("counts"),
                "latest": data.get("latest"),
                "warnings": data.get("warnings"),
            }, ensure_ascii=False, indent=2))
            break
    except Exception as exc:
        if attempt == 9:
            print("HEALTH_ERROR", type(exc).__name__, repr(exc))
    time.sleep(8)
else:
    print("HEALTH_NOT_UPDATED")

print("\n=== EURONEXT MODAL LOADER DISCOVERY ===")
try:
    page = get(EURONEXT, 30)
    html = page.text
    print("PAGE", page.status_code, len(html), page.url)
    needles = (
        "standardRightCompanyPressRelease",
        "data-node-nid",
        "companyPressRelease",
        "company-press-release",
        "press_release",
        "press-release",
    )
    for needle in needles:
        positions = [m.start() for m in re.finditer(re.escape(needle), html, flags=re.I)]
        print("INLINE", needle, "COUNT", len(positions))
        for pos in positions[-4:]:
            snippet = re.sub(r"\s+", " ", html[max(0,pos-500):pos+1000])
            if "<script" in snippet.lower() or "ajax" in snippet.lower() or "url" in snippet.lower():
                print("INLINE_MATCH", snippet[:1600])

    scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, flags=re.I)
    print("SCRIPT_COUNT", len(scripts))
    matched = 0
    for src in scripts:
        full = urljoin(page.url, src)
        if not full.startswith("https://live.euronext.com/"):
            continue
        try:
            r = get(full, 20)
            text = r.text
        except Exception:
            continue
        if not any(needle.lower() in text.lower() for needle in needles):
            continue
        matched += 1
        print("SCRIPT_MATCH_URL", full, "STATUS", r.status_code, "LEN", len(text))
        for needle in needles:
            pos = text.lower().find(needle.lower())
            if pos >= 0:
                print("SCRIPT_MATCH", needle, re.sub(r"\s+", " ", text[max(0,pos-1000):pos+2500])[:3600])
    print("MATCHED_SCRIPTS", matched)
except Exception as exc:
    print("EURONEXT_DISCOVERY_ERROR", type(exc).__name__, repr(exc))

print("\n=== DEPLOYED MOBILE POLICY QUICK CHECK ===")
for path in ("/app", "/holdings", "/manifest.webmanifest", "/sw.js", "/mobile_shell.js", "/access_gate.js", "/legal"):
    try:
        r = get(WORKER + path, 30)
        print(path, r.status_code, len(r.text), r.url)
    except Exception as exc:
        print(path, "ERROR", type(exc).__name__, repr(exc))
