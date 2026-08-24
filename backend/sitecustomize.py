"""Runtime patch for live insider disclosures from Euronext Oslo Børs Newspoint."""
from datetime import datetime, timedelta, timezone
import re
from urllib.parse import urljoin


def _install_insider_patch():
    try:
        from providers import NordicRegulatoryProvider
    except Exception:
        return

    if getattr(NordicRegulatoryProvider, "_live_insider_patch", False):
        return

    # Euronext's issuer pages are more stable than the global filtered-news
    # page for server-side retrieval. Add ISIN-backed issuer pages here and
    # extend the map as the Nordic universe grows.
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
        m = re.search(r"\b(\d{1,2})\s+([A-Za-z]{3})\s+(20\d{2})\b", value or "")
        if not m:
            return None
        month = MONTHS.get(m.group(2).lower())
        if not month:
            return None
        return f"{m.group(3)}-{month:02d}-{int(m.group(1)):02d}"

    def extract_rows(text, ticker, company_name):
        lines = [" ".join(x.split()) for x in (text or "").splitlines() if x.strip()]
        rows = []
        current_date = None
        issuer = norm(company_name)
        for idx, line in enumerate(lines):
            d = parse_date(line)
            if d:
                current_date = d
            low = line.lower()
            if not any(phrase in low for phrase in INSIDER_PHRASES):
                continue
            if any(x in low for x in ("buyback", "share buyback", "tilbakekjop")):
                continue
            neighbourhood = norm(" ".join(lines[max(0, idx - 2):idx + 3]))
            if issuer and issuer not in neighbourhood and norm(ticker) not in neighbourhood:
                # The issuer page is already company-specific, so issuer text
                # is not mandatory when parsing that page.
                pass
            rows.append({
                "ticker": ticker,
                "date": current_date,
                "title": line,
                "direction": "unknown",
                "source": "Euronext Oslo Børs Newspoint",
            })
        # Keep one row per disclosure date/title; English/Norwegian duplicates
        # for the same date are collapsed into one live disclosure.
        unique = []
        seen_dates = set()
        for row in rows:
            key = row.get("date") or norm(row.get("title"))
            if key in seen_dates:
                continue
            seen_dates.add(key)
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
                params = None if url in ISSUER_PAGES.values() else {
                    "keys": company_name,
                    "field_company_pr_pub_datetime_end": "now",
                    "field_company_pr_pub_datetime_start": (now - timedelta(days=365)).strftime("%Y-%m-%d 00:00:00"),
                    "page": 0,
                }
                html = self._html(url, params=params)
                parser = self._parser(html)
                rows = extract_rows(parser.text, ticker, company_name)
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
