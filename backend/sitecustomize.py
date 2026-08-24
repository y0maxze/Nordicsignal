"""Runtime patch for live insider disclosures from Euronext Oslo Børs Newspoint."""
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin
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

        html = self._html(self.EURONEXT_NEWS, params=params)
        parser = self._parser(html)
        candidates = []
        seen = set()
        insider_terms = (
            "primary insider", "primary insiders", "insider transaction",
            "insider notification", "mandatory notification of trade",
            "primærinsider", "primærinsidetransaksjon", "meldepliktig handel",
            "pdmr",
        )
        company_terms = [x for x in {
            self._norm(company_name),
            self._norm(company_name.replace("ASA", "")),
            self._norm(ticker),
        } if x]

        for href, text in parser.links:
            title = " ".join((text or "").split())
            low = title.lower()
            if not any(term in low for term in insider_terms):
                continue
            if "buyback" in low or "share buyback" in low or "tilbakekjøp" in low:
                continue
            # Euronext uses several URL forms (including /listview/company-press-release/).
            # Do not require a particular path; identify the issuer from the link text.
            company_match = any(term in self._norm(title) for term in company_terms)
            if company_terms and not company_match:
                continue
            url = urljoin(self.EURONEXT_NEWS, href)
            if url in seen:
                continue
            seen.add(url)
            candidates.append({"url": url, "title": title})
            if len(candidates) >= 12:
                break

        items = []
        buy_count = 0
        sell_count = 0
        for candidate in candidates:
            try:
                detail_html = self._html(candidate["url"])
                detail = self._parser(detail_html)
                body = detail.text
            except Exception:
                body = ""

            combined = f"{candidate['title']} {body}"
            low = combined.lower()
            direction = "unknown"
            if re.search(r"\b(bought|buy|purchased|acquired|acquisition|purchase|kjøpt|kjøpte|kjøp|ervervet|erverv)\b", low):
                direction = "buy"
                buy_count += 1
            elif re.search(r"\b(sold|sell|sale|disposed|disposal|solgte|solgt|salg|avhendet|avhending)\b", low):
                direction = "sell"
                sell_count += 1

            items.append({
                "ticker": ticker,
                "title": candidate["title"],
                "direction": direction,
                "url": candidate["url"],
                "source": "Oslo Børs Newspoint",
                "text": body[:1600],
            })

        if not items:
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

        return {
            "ticker": ticker,
            "items": items,
            "source": "Euronext Oslo Børs Newspoint",
            "status": "live",
            "buy_count": buy_count,
            "sell_count": sell_count,
            "signal": "buy" if buy_count > sell_count else "sell" if sell_count > buy_count else "mixed",
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
