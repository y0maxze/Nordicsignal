"""Runtime patch for live insider disclosures from Euronext and public issuer feeds."""
from datetime import datetime, timezone
from html import unescape
import re
import urllib.parse
import xml.etree.ElementTree as ET


def _install_insider_patch():
    try:
        from providers import NordicRegulatoryProvider, _TextParser
    except Exception:
        return
    if getattr(NordicRegulatoryProvider, "_live_insider_patch", False):
        return

    NEWS_ARCHIVE = "https://live.euronext.com/en/listview/company-press-releases/1061"
    NEWSWIRE_SEARCH = "https://rss.globenewswire.com/WpFeed/search/{query}/timezone/Eastern%20Standard%20Time/dateFormat/MMM%20dd%20yyyy%20hh:mm"
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
        v = (v or "").lower().replace("ø", "o").replace("æ", "ae").replace("å", "a")
        return re.sub(r"[^a-z0-9]+", " ", v).strip()

    def parse_date(v):
        v = v or ""
        m = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b", v)
        if m:
            return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        m = re.search(r"\b(\d{1,2})\s+([A-Za-z]{3})\s+(20\d{2})\b", v)
        if m and m.group(2).lower() in MONTHS:
            return f"{m.group(3)}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
        return None

    def clean_html(html):
        p = _TextParser(); p.feed(html or "")
        return " ".join((p.text or "").split()), p.links

    def direction_from_text(text):
        n = norm(text)
        if re.search(r"\b(purchased|bought|buy|kjopt|kjøpt|kjopte|kjøpte|acquired)\b", n):
            return "buy"
        if re.search(r"\b(sold|sell|solgte|solgt|disposed|avhendet)\b", n):
            return "sell"
        return "unknown"

    def parse_trade_text(text, ticker, title=None, source="Euronext Oslo Børs Newspoint", url=None):
        raw = " ".join(unescape(text or "").split())
        direction = direction_from_text(raw)
        date = parse_date(raw)
        if not date:
            m = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", raw)
            if m:
                date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        shares = None
        patterns = (
            r"(?:purchased|bought|sold|acquired|disposed[^0-9]{0,30})\s+([0-9][0-9 .,\u00a0]{0,20})\s+shares?",
            r"(?:kjøpt|kjopte|solgt|solgte)\s+([0-9][0-9 .,\u00a0]{0,20})\s+aksjer",
            r"([0-9][0-9 .,\u00a0]{0,20})\s+shares?\s+(?:in|of)",
        )
        for pat in patterns:
            m = re.search(pat, raw, re.I)
            if m:
                digits = re.sub(r"[^0-9]", "", m.group(1))
                if digits:
                    shares = int(digits)
                    break
        person = None
        m = re.search(r"^(.{2,100}?),\s*(?:CEO|CFO|Chair|Chairman|Board member|Styremedlem|Konsernsjef|konsernleder)\b", raw, re.I)
        if m:
            person = m.group(1).strip()
        if not person:
            m = re.search(r"^(.{2,100}?)\s+has\s+on\s+\d{1,2}\s+[A-Za-z]{3}\s+20\d{2}", raw, re.I)
            if m:
                person = m.group(1).strip()
        remaining = raw
        item = {
            "ticker": ticker,
            "date": date,
            "title": title or "Primary insider transaction",
            "direction": direction,
            "source": source,
        }
        if person:
            item["insider"] = person
        if shares is not None:
            item["shares"] = shares
        if url:
            item["url"] = url
        item["verified_detail"] = bool(date and (direction != "unknown" or shares is not None or person))
        item["summary"] = remaining[:500]
        return item

    def extract_euronext(html, ticker):
        text, links = clean_html(html)
        flat = " ".join(text.split())
        rows = []
        date_pat = r"(?:\d{1,2}[./-]\d{1,2}[./-]20\d{2}|\d{1,2}\s+[A-Za-z]{3}\s+20\d{2})"
        phrase_pat = r"(?:Primary Insider Transaction|Primærinsidetransaksjon|Mandatory Notification of Trade Primary Insiders|Meldepliktig handel for primærinnsidere|Notification of Trade by Primary Insider|Notification of Trade by PDMR)"
        for pattern in (rf"({date_pat}).{{0,900}}?({phrase_pat})", rf"({phrase_pat}).{{0,900}}?({date_pat})"):
            for m in re.finditer(pattern, flat, re.I):
                date = parse_date(m.group(1)) or parse_date(m.group(2))
                title = m.group(2) if norm(m.group(2)) in [norm(p) for p in PHRASES] else m.group(1)
                rows.append({"ticker": ticker, "date": date, "title": title.strip(), "direction": "unknown", "source": "Euronext Oslo Børs Newspoint", "verified_detail": False})
        for href, label in links:
            if not label or not any(norm(p) in norm(label) for p in PHRASES):
                continue
            full = href if href.startswith("http") else "https://live.euronext.com" + href
            rows.append({"ticker": ticker, "date": parse_date(label), "title": label.strip(), "direction": "unknown", "source": "Euronext Oslo Børs Newspoint", "verified_detail": False, "url": full})
        out, seen = [], set()
        for row in rows:
            key = (row.get("date"), norm(row.get("title")))
            if key not in seen:
                seen.add(key); out.append(row)
        return out

    def extract_newswire(company_name, ticker):
        if not company_name:
            return []
        query = urllib.parse.quote(company_name, safe="")
        url = NEWSWIRE_SEARCH.format(query=query)
        try:
            xml = self._html(url)
            root = ET.fromstring(xml)
        except Exception:
            return []
        rows = []
        for elem in root.iter():
            tag = elem.tag.rsplit("}", 1)[-1].lower()
            if tag not in ("item", "entry"):
                continue
            fields = {}
            for child in elem.iter():
                key = child.tag.rsplit("}", 1)[-1].lower()
                if child is elem:
                    continue
                value = " ".join("".join(child.itertext()).split())
                if value and key not in fields:
                    fields[key] = value
            title = fields.get("title", "")
            desc = fields.get("description") or fields.get("summary") or fields.get("content", "")
            if not any(norm(p) in norm(title) for p in PHRASES):
                continue
            if company_name and norm(company_name) not in norm(title + " " + desc):
                continue
            pub = fields.get("pubdate") or fields.get("published") or fields.get("updated") or ""
            url_value = fields.get("link")
            body = " ".join([title, desc, pub])
            row = parse_trade_text(body, ticker, title=title, source="GlobeNewswire / issuer release", url=url_value)
            if not row.get("date"):
                row["date"] = parse_date(pub)
            rows.append(row)
        return rows

    def merge_rows(primary, secondary):
        merged = list(primary)
        for s in secondary:
            best = None
            for p in merged:
                if s.get("date") and p.get("date") == s.get("date") and norm(s.get("title"))[:24] == norm(p.get("title"))[:24]:
                    best = p; break
            if best is None:
                merged.append(s)
                continue
            for key in ("direction", "insider", "shares", "summary", "url"):
                if (best.get(key) in (None, "unknown", "")) and s.get(key) not in (None, "unknown", ""):
                    best[key] = s[key]
            best["verified_detail"] = bool(best.get("verified_detail") or s.get("verified_detail"))
            if best.get("source") == "Euronext Oslo Børs Newspoint" and s.get("verified_detail"):
                best["detail_source"] = s.get("source")
        return sorted(merged, key=lambda x: x.get("date") or "", reverse=True)

    def insider(self, ticker, company_name=""):
        ticker = (ticker or "").upper()
        now = datetime.now(timezone.utc)
        last_error = None
        rows = []
        try:
            html = self._html(NEWS_ARCHIVE, params={"keys": ticker, "page": 0})
            rows = extract_euronext(html, ticker)
        except Exception as exc:
            last_error = exc
        try:
            rows = merge_rows(rows, extract_newswire(company_name, ticker))
        except Exception as exc:
            last_error = last_error or exc
        if not rows:
            result = {"ticker": ticker, "items": [], "source": "Euronext Oslo Børs Newspoint", "status": "no_recent_disclosures", "buy_count": 0, "sell_count": 0, "signal": "unavailable", "updated_at": now.isoformat()}
            if last_error:
                result["debug"] = str(last_error)
            return result
        buys = sum(1 for r in rows if r.get("direction") == "buy")
        sells = sum(1 for r in rows if r.get("direction") == "sell")
        unknown = len(rows) - buys - sells
        verified = sum(1 for r in rows if r.get("verified_detail"))
        signal = "buying" if buys > sells else "selling" if sells > buys else "activity"
        return {
            "ticker": ticker,
            "items": rows[:12],
            "source": "Euronext Oslo Børs Newspoint + issuer release fallback",
            "status": "live_disclosures",
            "buy_count": buys,
            "sell_count": sells,
            "unknown_count": unknown,
            "verified_detail_count": verified,
            "signal": signal,
            "updated_at": now.isoformat(),
        }

    NordicRegulatoryProvider.insider = insider
    NordicRegulatoryProvider._live_insider_patch = True

_install_insider_patch()
