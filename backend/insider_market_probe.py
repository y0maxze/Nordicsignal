import json

from curl_cffi import requests

import general_news_runtime

BASE = "https://live.euronext.com/en/listview/company-press-releases-by-mkt/1061/all"
PARAMS = {"field_company_press_releases_target_id[1081]": "1081"}

for page in range(3):
    params = dict(PARAMS)
    params["page"] = page
    try:
        r = requests.get(BASE, params=params, impersonate="chrome", timeout=25, allow_redirects=True)
        rows = general_news_runtime.parse_general_euronext_html(r.text, 60)
        insider = [x for x in rows if x.get("category") == "Insider"]
        print("PAGE", page)
        print("STATUS", r.status_code)
        print("FINAL", r.url)
        print("HTML_LEN", len(r.text))
        print("ROWS", len(rows), "INSIDER", len(insider))
        print(json.dumps(insider[:60], ensure_ascii=False, indent=2, default=str))
    except Exception as exc:
        print("ERROR", page, type(exc).__name__, repr(exc))
