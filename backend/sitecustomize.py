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
    NEWS_ARCHIVE = "https://live.euronext.com/en/markets/oslo/equities/company-news"

    INSIDER_PHRASES = (
        "primary insider",
        "primærinsidetransaksjon",
        "mandatory notification of trade primary insiders",
        "meldepliktig handel for primærinnsidere",
        "notification of trade by primary insider",
        "notification of trade by pdmr",
        "pdmr",
    )

    MONTHS = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "mai": 5,
        "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "okt": 10,
        "nov": 11, "dec": 12, "des": 12,
    }

    def norm(value):
        value = (value or "").lower().replace("ø", "o").replace("æ", "ae").replace("å", "a")
        return re.sub(r"[^a-z0-9]+", " ", value).strip()

    def parse_date(value):
        value = value or ""
        m = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b", value)
        if m:
            return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        m = re.search(r"\b(\d{1,2})\s+([A-Za-z]{3})\s+(20\d{2})\b", value)
        if not m:
            return None
        month = MONTHS.get(m.group(2).lower())
        return f"{m.group(3)}-{month:02d}-{int(m.group(1)):02d}" if month else None

    def is_insider(text):
        low = norm(text)
        return any(norm(p) in low for p in INSIDER_PHRASES)

    def extract_rows(text, ticker):
        lines = [" ".join(x.split()) for x in (text or "").splitlines() if x.strip()]
        rows = []
        for idx, line in enumerate(lines):
            if not is_insider(line):
                continue
            low = line.lower()
            if any(x in low for x in ("buyback", "share buyback", "tilbakekjop")):
                continue
            d = parse_date(line) or (parse_date(lines[idx - 1]) if idx else None)
            rows.append({
                "ticker": ticker,
                "date": d,
                "title": line,
                "direction": "unknown",
                "source": "Euronext Oslo Børs Newspoint",
            })
        return rows

    def extract_link_rows(parser, ticker):
        rows = []
        for href, text in parser.links:
            if not href or not text or not is_insider(text):
                continue
            full = href if href.startswith("http") else "https://live.euronext.com" + href
            rows.append({"ticker": ticker, "date": parse_date(text), "title": text.strip(), "direction": "unknown", "source": "Euronext Oslo Børs Newspoint", "url": full})
        return rows

    def dedup(rows):
        out, seen = [], set()
        for row in rows:
            date_key = row.get("date")
            title_key = norm(row.get("title"))
            # English/Norwegian duplicate publications on the same date are one disclosure.
            key = date_key or title_key
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
        return out

    def insider(self, ticker, company_name=""):
        ticker = (ticker or "").upper()
        now = datetime.now(timezone.utc)
        urls = []
        if ticker in ISSUER_PAGES:
            urls.append((ISSUER_PAGES[ticker], None))
        urls.append((NEWS_ARCHIVE, {
            "keys": ticker,
            "field_company_pr_pub_datetime_end": "now",
            "field_company_pr_pub_datetime_start": (now - timedelta(days=365)).strftime("%Y-%m-%d 00:00:00"),
            "page": 0,
        }))
        last_error = None

        for url, params in urls:
            try:
                html = self._html(url, params=params)
                parser = _TextParser()
                parser.feed(html)
                rows = extract_rows(parser.text, ticker)
                rows.extend(extract_link_rows(parser, ticker))
                rows = dedup(rows)

                # Parse table rows when the response is flattened into one text block.
                if not rows:
                    flat = " ".join((parser.text or "").split())
                    date_pat = r"(?:\d{1,2}[./-]\d{1,2}[./-]20\d{2}|\d{1,2}\s+[A-Za-z]{3}\s+20\d{2})"
                    phrase_pat = r"(?:Primary Insider Transaction|Primærinsidetransaksjon|Mandatory Notification of Trade Primary Insiders|Meldepliktig handel for primærinnsidere|Notification of Trade by Primary Insider|Notification of Trade by PDMR)"
                    pattern = re.compile(rf"({date_pat}).{{0,250}}?({phrase_pat})", re.I)
                    for m in pattern.finditer(flat):
                        rows.append({"ticker": ticker, "date": parse_date(m.group(1)), "title": m.group(2), "direction": "unknown", "source": "Euronext Oslo Børs Newspoint"})
                    rows = dedup(rows)

                if rows:
                    return {
                        "ticker": ticker,
                        "items": rows[:12],
                        "source": "Euronext Oslo Børs Newspoint",
                        "status": "live_disclosures",
                        "buy_count": 0,
                        "sell_count": 0,
                        "unknown_count": len(rows[:12]),
                        "signal": "activity",
                        "updated_at": now.isoformat(),
                    }
            except Exception as exc:
                last_error = exc

        result = {
            "ticker": ticker,
            "items": [],
            "source": "Euronext Oslo Børs Newspoint",
            "status": "no_recent_disclosures",
            "buy_count": 0,
            "sell_count": 0,
            "signal": "unavailable",
            "updated_at": now.isoformat(),
        }
        if last_error:
            result["debug"] = str(last_error)
        return result

    NordicRegulatoryProvider.insider = insider
    NordicRegulatoryProvider._live_insider_patch = True


_install_insider_patch()
