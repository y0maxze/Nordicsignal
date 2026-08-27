import json
import re
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


node_id = "12906847"
for url in (
    f"https://live.euronext.com/en/node/{node_id}",
    f"https://live.euronext.com/en/company-press-release/{node_id}",
    f"https://live.euronext.com/en/ajax/company-press-release/{node_id}",
    f"https://live.euronext.com/en/ajax/getCompanyPressRelease/{node_id}",
    f"https://live.euronext.com/en/node/{node_id}?ajax=1",
):
    try:
        r = requests.get(url, impersonate="chrome", timeout=20, allow_redirects=True)
        dump("NODE URL", {"url": url, "status": r.status_code, "final": r.url, "len": len(r.text), "body": r.text[:2500]})
    except Exception as exc:
        dump("NODE URL ERROR", {"url": url, "error": type(exc).__name__, "detail": repr(exc)})

try:
    html = news_runtime._fetch_text(news_runtime.EURONEXT_LATEST)
    rows = general_news_runtime.parse_general_euronext_html(html, 60)
    dump("EURONEXT SOURCE", {"html_len": len(html), "row_count": len(rows), "rows": rows[:10]})
    patterns = [
        r'[^\n]{0,250}standardRightCompanyPressRelease[^\n]{0,500}',
        r'[^\n]{0,250}data-node-nid[^\n]{0,500}',
        r'[^\n]{0,250}(?:ajax|Ajax|AJAX)[^\n]{0,500}',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, html, flags=re.I)
        dump("MARKUP MATCH " + pattern, matches[:12])
    scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, flags=re.I)
    dump("SCRIPTS", [x for x in scripts if any(k in x.lower() for k in ("company", "market", "main", "global", "euronext", "live"))][-30:])
except Exception as exc:
    dump("EURONEXT SOURCE ERROR", {"error": type(exc).__name__, "detail": repr(exc)})

try:
    dump("LOCAL FEED", im.market_insider_feed(limit=100, days=14, refresh=True))
except Exception as exc:
    dump("LOCAL FEED ERROR", {"error": type(exc).__name__, "detail": repr(exc)})
    sys.exit(1)
