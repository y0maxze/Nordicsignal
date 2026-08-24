"""Runtime patch for live insider disclosures from Euronext Oslo Børs Newspoint."""
from datetime import datetime, timedelta, timezone
import re


def _install_insider_patch():
    try:
        from providers import NordicRegulatoryProvider, _TextParser
    except Exception:
        return
    if getattr(NordicRegulatoryProvider, "_live_insider_patch", False):
        return

    ISSUER_PAGES = {
        "LSG": "https://live.euronext.com/en/product/equities/NO0003096208-XOSL/company-information",
    }
    NEWS_ARCHIVE = "https://live.euronext.com/en/listview/company-press-releases/1061"
    PHRASES = (
        "Primary Insider Transaction",
        "Primærinsidetransaksjon",
        "Mandatory Notification of Trade Primary Insiders",
        "Meldepliktig handel for primærinnsidere",
        "Notification of Trade by Primary Insider",
        "Notification of Trade by PDMR",
    )
    MONTHS = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"mai":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"okt":10,"nov":11,"dec":12,"des":12}

    def norm(v):
        v = (v or "").lower().replace("ø","o").replace("æ","ae").replace("å","a")
        return re.sub(r"[^a-z0-9]+", " ", v).strip()

    def parse_date(v):
        v = v or ""
        m = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b", v)
        if m:
            return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        m = re.search(r"\b(\d{1,2})\s+([A-Za-z]{3})\s+(20\d{2})\b", v)
        if not m or m.group(2).lower() not in MONTHS:
            return None
        return f"{m.group(3)}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"

    def clean_html(html):
        p = _TextParser(); p.feed(html or "")
        return " ".join((p.text or "").split()), p.links

    def extract(html, ticker):
        text, links = clean_html(html)
        flat = " ".join(text.split())
        rows = []
        date_pat = r"(?:\d{1,2}[./-]\d{1,2}[./-]20\d{2}|\d{1,2}\s+[A-Za-z]{3}\s+20\d{2})"
        phrase_pat = r"(?:Primary Insider Transaction|Primærinsidetransaksjon|Mandatory Notification of Trade Primary Insiders|Meldepliktig handel for primærinnsidere|Notification of Trade by Primary Insider|Notification of Trade by PDMR)"
        # Euronext may render the date before the title or the title before the date.
        patterns = [
            rf"({date_pat}).{{0,700}}?({phrase_pat})",
            rf"({phrase_pat}).{{0,700}}?({date_pat})",
        ]
        for pattern in patterns:
            for m in re.finditer(pattern, flat, re.I):
                date = parse_date(m.group(1)) or parse_date(m.group(2))
                title = m.group(2) if is_phrase(m.group(2)) else m.group(1)
                rows.append({"ticker": ticker, "date": date, "title": title.strip(), "direction": "unknown", "source": "Euronext Oslo Børs Newspoint"})
        # Also inspect actual anchor text; issuer pages can split date/title into separate DOM nodes.
        for href, label in links:
            if not label or not any(norm(p) in norm(label) for p in PHRASES):
                continue
            full = href if href.startswith("http") else "https://live.euronext.com" + href
            rows.append({"ticker": ticker, "date": parse_date(label), "title": label.strip(), "direction": "unknown", "source": "Euronext Oslo Børs Newspoint", "url": full})
        out, seen = [], set()
        for row in rows:
            key = (row.get("date"), norm(row.get("title")))
            if key in seen:
                continue
            seen.add(key); out.append(row)
        return out

    def is_phrase(v):
        n = norm(v)
        return any(norm(p) in n for p in PHRASES)

    def insider(self, ticker, company_name=""):
        ticker = (ticker or "").upper()
        now = datetime.now(timezone.utc)
        urls = []
        if ticker in ISSUER_PAGES:
            urls.append((ISSUER_PAGES[ticker], None))
        urls.append((NEWS_ARCHIVE, {"keys": ticker, "page": 0}))
        last_error = None
        for url, params in urls:
            try:
                html = self._html(url, params=params)
                rows = extract(html, ticker)
                if rows:
                    return {
                        "ticker": ticker,
                        "items": rows[:12],
                        "source": "Euronext Oslo Børs Newspoint",
                        "status": "live_disclosures",
                        "buy_count": sum(1 for r in rows if r.get("direction") == "buy"),
                        "sell_count": sum(1 for r in rows if r.get("direction") == "sell"),
                        "unknown_count": sum(1 for r in rows if r.get("direction") == "unknown"),
                        "signal": "activity",
                        "updated_at": now.isoformat(),
                    }
            except Exception as exc:
                last_error = exc
        result = {"ticker": ticker, "items": [], "source": "Euronext Oslo Børs Newspoint", "status": "no_recent_disclosures", "buy_count": 0, "sell_count": 0, "signal": "unavailable", "updated_at": now.isoformat()}
        if last_error:
            result["debug"] = str(last_error)
        return result

    NordicRegulatoryProvider.insider = insider
    NordicRegulatoryProvider._live_insider_patch = True

_install_insider_patch()
