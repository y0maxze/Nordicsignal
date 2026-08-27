import json
import sys

from curl_cffi import requests

import insider_market_runtime as im
import news_runtime
import general_news_runtime


def dump(label, value):
    print(f"\n=== {label} ===")
    if isinstance(value, str):
        print(value)
    else:
        print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


for label, url in (
    ("RENDER ENDPOINT", "https://nordicsignal-api.onrender.com/api/insider-market?days=14&refresh=true"),
    ("CLOUDFLARE ENDPOINT", "https://nordicsignal.8pnwk5r8f4.workers.dev/api/insider-market?days=14&refresh=true"),
):
    try:
        response = requests.get(url, impersonate="chrome", timeout=30)
        dump(label, {"status": response.status_code, "body": response.text[:30000]})
    except Exception as exc:
        dump(label, {"error": type(exc).__name__, "detail": repr(exc)})

for url in (news_runtime.EURONEXT_LATEST, news_runtime.EURONEXT_ARCHIVE):
    try:
        html = news_runtime._fetch_text(url)
        rows = general_news_runtime.parse_general_euronext_html(html, 60)
        dump("EURONEXT SOURCE", {
            "url": url,
            "html_len": len(html),
            "row_count": len(rows),
            "rows": rows[:40],
        })
    except Exception as exc:
        dump("EURONEXT SOURCE ERROR", {"url": url, "error": type(exc).__name__, "detail": repr(exc)})

try:
    candidates = im._candidate_announcements()
    dump("CANDIDATES", {"count": len(candidates), "items": candidates})
    extracted = []
    for item in candidates:
        try:
            extracted.append({"announcement": item, "rows": im._extract_disclosure(item)})
        except Exception as exc:
            extracted.append({"announcement": item, "error": type(exc).__name__, "detail": repr(exc)})
    dump("EXTRACTED", extracted)
except Exception as exc:
    dump("CANDIDATE ERROR", {"error": type(exc).__name__, "detail": repr(exc)})

try:
    dump("LOCAL FEED", im.market_insider_feed(limit=100, days=14, refresh=True))
except Exception as exc:
    dump("LOCAL FEED ERROR", {"error": type(exc).__name__, "detail": repr(exc)})
    sys.exit(1)
