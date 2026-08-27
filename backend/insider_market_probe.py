import re
from curl_cffi import requests

NODE_IDS = ("12906847",)
BASE = "https://live.euronext.com"

for node_id in NODE_IDS:
    url = f"{BASE}/ajax/node/company-press-release/{node_id}"
    try:
        response = requests.get(url, impersonate="chrome", timeout=30, allow_redirects=True)
        text = response.text
        clean = re.sub(r"\s+", " ", text)
        print("NODE", node_id)
        print("STATUS", response.status_code)
        print("FINAL", response.url)
        print("CONTENT_TYPE", response.headers.get("content-type"))
        print("LEN", len(text))
        print("HAS_PRIMARY_INSIDER", "primary insider" in text.lower() or "mandatory notification" in text.lower())
        print("HAS_SHARES", "shares" in text.lower())
        print("BODY", clean[:12000])
    except Exception as exc:
        print("ERROR", node_id, type(exc).__name__, repr(exc))
