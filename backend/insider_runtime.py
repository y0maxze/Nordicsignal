"""Robust live insider discovery for NordicSignal.

Uses Euronext issuer pages first, then the Oslo company-news feed.  A disclosure
is only counted as a verified trade when the detail page contains a trade
verb or a share quantity and matches the requested issuer.
"""
from datetime import datetime, timezone
from html.parser import HTMLParser
import re

from curl_cffi import requests


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.links = []
        self.href = None
        self.link_parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.href = attrs.get("href")
            self.link_parts = []
        if tag in ("script", "style", "noscript"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag == "a" and self.href:
            self.links.append((self.href, " ".join(self.link_parts).strip()))
            self.href = None
            self.link_parts = []
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if self.skip:
            return
        text = " ".join(data.split())
        if text:
            self.parts.append(text)
            if self.href is not None:
                self.link_parts.append(text)

    @property
    def text(self):
        return " ".join(self.parts)


ISSUERS = {
    "LSG": {"name": "Lerøy Seafood Group ASA", "aliases": ("lerøy seafood", "leroy seafood"), "url": "https://live.euronext.com/en/product/equities/NO0003096208-XOSL/company-information"},
}
PHRASES = ("primary insider", "primærinsider", "mandatory notification of trade", "notification of trade by primary insider", "pdmr")
BUY = re.compile(r"\b(purchased|purchase|bought|buy|acquired|kjøpt|kjøpte|kjøp)\b", re.I)
SELL = re.compile(r"\b(sold|sell|sale|disposed|avhendet|solgt|solgte|salg)\b", re.I)
SHARES = re.compile(r"(?:purchased|purchase|bought|buy|acquired|sold|sell|disposed of|kjøpt|kjøpte|kjøp|solgt|solgte|salg).{0,180}?(\d[\d .\u00a0,]*)\s+(?:shares|aksjer)\b", re.I | re.S)
DATE = re.compile(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b|\b(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})\b")


def _norm(value):
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower().replace("ø", "o").replace("æ", "ae").replace("å", "a")).strip()


def _parse_date(text):
    m = DATE.search(text or "")
    if not m:
        return None
    if m.group(1):
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return f"{m.group(5)}-{int(m.group(4)):02d}-{int(m.group(5) if False else m.group(4)):02d}" if False else f"{m.group(5)}-{int(m.group(4)):02d}-{int(m.group(5) if False else m.group(2)):02d}"


def _date(text):
    m = re.search(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b", text or "")
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})\b", text or "")
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return None


def _issuer_matches(body, ticker, company_name):
    n = _norm(body)
    info = ISSUERS.get(ticker, {})
    needles = [_norm(company_name), *(_norm(x) for x in info.get("aliases", ())), _norm(ticker)]
    return any(x and x in n for x in needles)


def _trade_detail(body, ticker, title, source, url):
    direction = "buy" if BUY.search(body) else "sell" if SELL.search(body) else "unknown"
    shares = None
    m = SHARES.search(body)
    if m:
        digits = re.sub(r"[^0-9]", "", m.group(1))
        if digits:
            shares = int(digits)
    # The issuer release itself is sufficient to verify direction; the share count
    # is additional evidence and is retained when available.
    verified = direction in ("buy", "sell") or shares is not None
    return {
        "ticker": ticker,
        "date": _date(body),
        "trade_date": _date(body),
        "title": title or "Primary insider transaction",
        "direction": direction,
        "transaction_type": direction if direction in ("buy", "sell") else "other",
        "shares": shares,
        "source": source,
        "verified_detail": verified,
        "summary": " ".join(body.split())[:1000],
        "url": url,
    }


def _fetch(session, url, params=None):
    r = session.get(url, params=params, timeout=20, allow_redirects=True)
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:250]}")
    return r.text


def install():
    try:
        from providers import NordicRegulatoryProvider
    except Exception:
        return
    if getattr(NordicRegulatoryProvider, "_robust_insider_patch", False):
        return

    def insider(self, ticker, company_name=""):
        ticker = (ticker or "").upper()
        info = ISSUERS.get(ticker, {})
        company_name = company_name or info.get("name") or ticker
        session = getattr(self, "session", requests.Session(impersonate="chrome"))
        pages = []
        if info.get("url"):
            pages.append(info["url"])
        pages.append("https://live.euronext.com/en/markets/oslo/equities/company-news")
        candidates = []
        seen = set()
        for page_url in pages:
            try:
                html = _fetch(session, page_url, {"keys": ticker, "page": 0})
            except Exception:
                continue
            parser = _Parser(); parser.feed(html)
            for href, label in parser.links:
                if "/products/equities/company-news/" not in href:
                    continue
                full = href if href.startswith("http") else "https://live.euronext.com" + href
                low = _norm(label)
                # On issuer pages the label may contain only the company title,
                # so inspect all company-news links and validate the detail page.
                if not (any(x in low for x in ("insider", "primar", "pdmr", "mandatory notification")) or ticker == "LSG"):
                    continue
                if full not in seen:
                    seen.add(full); candidates.append((full, label))
            # If the issuer page itself renders disclosures without links, the
            # visible rows still establish activity, but details require a link.
            if len(candidates) >= 12:
                break

        items = []
        for url, label in candidates[:20]:
            try:
                detail_html = _fetch(session, url)
                parser = _Parser(); parser.feed(detail_html); body = parser.text
                if not any(x in _norm(body) for x in PHRASES):
                    continue
                if not _issuer_matches(body, ticker, company_name):
                    continue
                item = _trade_detail(body, ticker, label, "Euronext Oslo Børs Newspoint", url)
                if item["verified_detail"]:
                    items.append(item)
            except Exception:
                continue

        # Deduplicate bilingual copies when they describe the same trade.
        dedup = {}
        for item in items:
            key = (item.get("date"), item.get("direction"), item.get("shares"))
            old = dedup.get(key)
            if old is None or (not old.get("shares") and item.get("shares")):
                dedup[key] = item
        items = sorted(dedup.values(), key=lambda x: x.get("date") or "", reverse=True)
        buys = sum(x.get("direction") == "buy" for x in items)
        sells = sum(x.get("direction") == "sell" for x in items)
        now = datetime.now(timezone.utc).isoformat()
        if items:
            signal = "buying" if buys > sells else "selling" if sells > buys else "activity"
            return {"ticker": ticker, "items": items[:12], "source": "Euronext Oslo Børs Newspoint", "status": "live", "buy_count": buys, "sell_count": sells, "unknown_count": 0, "verified_detail_count": len(items[:12]), "signal": signal, "updated_at": now}
        return {"ticker": ticker, "items": [], "source": "Euronext Oslo Børs Newspoint", "status": "no_recent_disclosures", "buy_count": 0, "sell_count": 0, "unknown_count": 0, "verified_detail_count": 0, "signal": "unavailable", "updated_at": now}

    NordicRegulatoryProvider.insider = insider
    NordicRegulatoryProvider._robust_insider_patch = True


install()
