import json

from curl_cffi import requests

import general_news_runtime
import insider_market_v2_runtime as im2
import news_runtime


def dump(label, value):
    print(f"\n=== {label} ===")
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


for label, url in (
    ("RENDER", "https://nordicsignal-api.onrender.com/api/insider-market?days=14&refresh=true"),
    ("CLOUDFLARE", "https://nordicsignal.8pnwk5r8f4.workers.dev/api/insider-market?days=14&refresh=true"),
):
    try:
        r = requests.get(url, impersonate="chrome", timeout=30)
        body = r.json() if "json" in str(r.headers.get("content-type", "")).lower() else r.text[:20000]
        dump(label, {"status_code": r.status_code, "body": body})
    except Exception as exc:
        dump(label, {"error": type(exc).__name__, "detail": repr(exc)})

try:
    html = news_runtime._fetch_text(news_runtime.EURONEXT_LATEST)
    rows = general_news_runtime.parse_general_euronext_html(html, 60)
    insider_rows = [x for x in rows if x.get("category") == "Insider"]
    dump("LIVE EURONEXT PARSER", {
        "html_len": len(html),
        "row_count": len(rows),
        "insider_count": len(insider_rows),
        "insider_rows": insider_rows[:20],
    })
except Exception as exc:
    dump("LIVE EURONEXT PARSER", {"error": type(exc).__name__, "detail": repr(exc)})

try:
    feed = im2.market_insider_feed(limit=100, days=14, refresh=True)
    dump("LOCAL V2 FEED", {
        "status": feed.get("status"),
        "runtime": feed.get("runtime"),
        "disclosure_count": feed.get("disclosure_count"),
        "eligible_trade_count": feed.get("eligible_trade_count"),
        "pending_detail_count": feed.get("pending_detail_count"),
        "excluded_non_signal_count": feed.get("excluded_non_signal_count"),
        "pulses": feed.get("pulses"),
        "items": feed.get("items"),
        "errors": feed.get("errors"),
    })
except Exception as exc:
    dump("LOCAL V2 FEED", {"error": type(exc).__name__, "detail": repr(exc)})
