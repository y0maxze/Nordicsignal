import json
import re

import news_runtime


def show(label, text):
    print(f"\n=== {label} ===\n{text}\n")

urls = [
    "https://live.euronext.com/en/listview/company-press-releases-by-mkt/1061/all",
    "https://live.euronext.com/en/markets/oslo/equities/company-news",
]
for url in urls:
    try:
        html = news_runtime._fetch_text(url)
        show("URL", url)
        for needle in (
            "Mandatory notification of trade primary insiders",
            "Meldepliktig handel for primærinnsidere",
            "company_press_releases_view",
        ):
            pos = html.lower().find(needle.lower())
            snippet = html[max(0, pos-2500):pos+2500] if pos >= 0 else "NOT FOUND"
            show(needle, snippet)
        inputs = re.findall(r'<input[^>]+(?:name|value)=["\'][^"\']+["\'][^>]*>', html, flags=re.I)
        relevant = [x for x in inputs if any(k in x.lower() for k in ("topic", "press", "trade", "date", "field_"))]
        show("RELEVANT INPUTS", "\n".join(relevant[:120]))
        forms = re.findall(r'<form[^>]*>', html, flags=re.I)
        show("FORMS", "\n".join(forms[:30]))
    except Exception as exc:
        show("ERROR", type(exc).__name__ + ": " + repr(exc))
