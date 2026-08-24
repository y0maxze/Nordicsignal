"""Runtime patch for live insider disclosures from Euronext Oslo Børs Newspoint.

Euronext's company-news pages render the disclosure table as page content, while
individual disclosure links are not consistently exposed as normal anchors.
This patch therefore parses the issuer's filtered news table itself instead of
requiring a particular URL shape.
"""
from datetime import datetime, timedelta, timezone
import re


def _install_insider_patch():
    try:
        from providers import NordicRegulatoryProvider
    except Exception:
        return

    if getattr(NordicRegulatoryProvider, "_live_insider_patch", False):
        return

    def insider(self, ticker, company_name=""):
        ticker = (ticker or "").upper()
        company_name = company_name or ticker
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=365)).strftime("%Y-%m-%d 00:00:00")

        params = {
            "keys": company_name,
            "field_company_pr_pub_datetime_end": "now",
            "field_company_pr_pub_datetime_start": start,
            "page": 0,
        }

        try:
            raw_html = self._html(self.EURONEXT_NEWS, params=params)
            parser = self._parser(raw_html)
            text = parser.text or ""
        except Exception as exc:
            return {
                "ticker": ticker,
                "items": [],
                "source": "Euronext Oslo Børs Newspoint",
                "status": "unavailable",
                "buy_count": 0,
                "sell_count": 0,
                "signal": "unavailable",
                "error": str(exc),
                "updated_at": now.isoformat(),
            }

        def norm(value):
            return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()

        issuer_terms = {
            norm(company_name),
            norm(company_name.replace(" ASA", "")),
            norm(ticker),
        }
        issuer_terms = {x for x in issuer_terms if x}

        insider_terms = (
            "primary insider",
            "primary insiders",
            "insider transaction",
            "insider notification",
            "mandatory notification of trade",
            "primærinsider",
            "primærinsidetransaksjon",
            "meldepliktig handel",
            "pdmr",
        )

        # The filtered Euronext table contains rows such as:
        # 22 Aug 2026 | Lerøy Seafood Group ASA | ... Primary Insider Transaction
        # The same disclosure is normally published in English and Norwegian.
        lines = [" ".join(x.split()) for x in text.splitlines() if x.strip()]
        rows = []
        current_date = None

        date_re = re.compile(r"^(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})$")
        inline_date_re = re.compile(r"^(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s+")

        for idx, line in enumerate(lines):
            m = date_re.match(line)
            if m:
                current_date = m.group(1)
                continue

            m = inline_date_re.match(line)
            if m:
                current_date = m.group(1)

            low = line.lower()
            if not any(term in low for term in insider_terms):
                continue
            if any(bad in low for bad in ("buyback", "share buyback", "tilbakekjøp")):
                continue

            issuer_match = any(term in norm(line) for term in issuer_terms)
            # When the table splits columns into adjacent lines, inspect a small
            # neighbourhood around the title as well.
            if not issuer_match:
                neighbourhood = " ".join(lines[max(0, idx - 2):idx + 3])
                issuer_match = any(term in norm(neighbourhood) for term in issuer_terms)
            if not issuer_match:
                continue

            rows.append({
                "ticker": ticker,
                "date": current_date,
                "title": line,
                "direction": "unknown",
                "source": "Oslo Børs Newspoint",
            })

        # De-duplicate English/Norwegian versions of the same disclosure while
        # retaining the most useful title.
        unique = []
        seen = set()
        for row in rows:
            key = (row.get("date"), norm(row.get("title", "")))
            if key in seen:
                continue
            seen.add(key)
            unique.append(row)

        # We can safely report that live insider disclosures exist from the
        # official Euronext feed. Direction is deliberately left unknown until
        # the individual KRT-1500 transaction document is parsed; no fake buy/sell
        # score is generated from the headline alone.
        if unique:
            return {
                "ticker": ticker,
                "items": unique[:12],
                "source": "Euronext Oslo Børs Newspoint",
                "status": "live_disclosures",
                "buy_count": 0,
                "sell_count": 0,
                "unknown_count": len(unique[:12]),
                "signal": "activity",
                "updated_at": now.isoformat(),
            }

        return {
            "ticker": ticker,
            "items": [],
            "source": "Euronext Oslo Børs Newspoint",
            "status": "no_recent_disclosures",
            "buy_count": 0,
            "sell_count": 0,
            "signal": "unavailable",
            "updated_at": now.isoformat(),
        }

    def parser(html):
        from providers import _TextParser
        p = _TextParser()
        p.feed(html)
        return p

    NordicRegulatoryProvider._parser = staticmethod(parser)
    NordicRegulatoryProvider.insider = insider
    NordicRegulatoryProvider._live_insider_patch = True


_install_insider_patch()
