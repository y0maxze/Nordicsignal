"""Runtime patch for live insider disclosures from Euronext Oslo Børs Newspoint."""
from datetime import datetime, timedelta, timezone
import re


def _install_insider_patch():
    try:
        from providers import NordicRegulatoryProvider
    except Exception:
        return

    if getattr(NordicRegulatoryProvider, "_live_insider_patch", False):
        return

    ISSUER_PAGES = {
        "LSG": "https://live.euronext.com/en/product/equities/NO0003096208-XOSL/company-information",
    }

    INSIDER_PHRASES = (
        "primary insider",
        "primærinsidetransaksjon",
        "mandatory notification of trade primary insiders",
        "meldepliktig handel for primærinnsidere",
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
        if not month:
            return None
        return f"{m.group(3)}-{month:02d}-{int(m.group(1)):02d}"

    def extract_rows(text, ticker, company_name):
        lines = [" ".join(x.split()) for x in (text or "").splitlines() if x.strip()]
        rows = []
        for idx, line in enumerate(lines):
            low = line.lower()
            if not any(phrase in low for phrase in INSIDER_PHRASES):
                continue
            if any(x in low for x in ("buyback", "share buyback", "tilbakekjop")):
                continue
            d = parse_date(line)
            if not d and idx > 0:
                d = parse_date(lines[idx - 1])
            rows.append({
                "ticker": ticker,
                "date": d,
                "title": line,
                "direction": "unknown",
                "source": "Euronext Oslo Børs Newspoint",
            })
        unique = []
        seen = set()
        for row in rows:
            key = (row.get("date"), norm(row.get("title")))
            # English and Norwegian versions on the same date represent one disclosure.
            date_key = row.get("date")
            if date_key and date_key in seen:
                continue
            if not date_key and key in seen:
                continue
            seen.add(date_key or key)
            unique.append(row)
        return unique

    def insider(self, ticker, company_name=""):
        ticker = (ticker or "").upper()
        company_name = company_name or ticker
        now = datetime.now(timezone.utc)
        urls = []
        if ticker in ISSUER_PAGES:
            urls.append(ISSUER_PAGES[ticker])
        urls.append(self.EURONEXT_NEWS)
        last_error = None

        for url in urls:
            try:
                params = None if ticker in ISSUER_PAGES and url == ISSUER_PAGES[ticker] else {
                    "keys": company_name,
                    "field_company_pr_pub_datetime_end": "now",
                    "field_company_pr_pub_datetime_start": (now - timedelta(days=365)).strftime("%Y-%m-%d 00:00:00"),
                    "page": 0,
                }
                html = self._html(url, params=params)
                parser = self._parser(html)
                rows = extract_rows(parser.text, ticker, company_name)

                # If the HTML parser receives the table as one long text block,
                # parse date/title pairs directly from that block as a fallback.
                if not rows:
                    flat = " ".join((parser.text or "").split())
                    for m in re.finditer(r"(\d{1,2}[./-]\d{1,2}[./-]20\d{2}|\d{1,2}\s+[A-Za-z]{3}\s+20\d{2}).{0,180}?(Primary Insider Transaction|Primærinsidetransaksjon|Mandatory Notification of Trade Primary Insiders|Meldepliktig handel for primærinnsidere)", flat, flags=re.I):
                        rows.append({"ticker": ticker, "date": parse_date(m.group(1)), "title": m.group(2), "direction": "unknown", "source": "Euronext Oslo Børs Newspoint"})
                    dedup = {}
                    for row in rows:
                        dedup[row.get("date") or row.get("title")] = row
                    rows = list(dedup.values())

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

    def parser(html):
        from providers import _TextParser
        p = _TextParser()
        p.feed(html)
        return p

    NordicRegulatoryProvider._parser = staticmethod(parser)
    NordicRegulatoryProvider.insider = insider
    NordicRegulatoryProvider._live_insider_patch = True


_install_insider_patch()
