"""Runtime patch for reliable live primary-insider disclosures.

The Euronext company-news archive is a shared feed. A ticker query can still
return unrelated issuers, so every candidate is validated against the issuer
name/ticker before it is accepted. Detail is enriched from the issuer release
feed and only verified trade details are allowed to drive the insider score.
"""
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

    EURONEXT_ARCHIVE = "https://live.euronext.com/en/listview/company-press-releases/1061"
    NEWSWIRE_SEARCH = "https://rss.globenewswire.com/WpFeed/search/{query}/timezone/Eastern%20Standard%20Time/dateFormat/MMM%20dd%20yyyy%20hh:mm"

    ISSUERS = {
        "LSG": {"name": "Lerøy Seafood Group ASA", "aliases": ["lerøy seafood", "leroy seafood", "lerøy seafood group", "leroy seafood group"]},
        "MPCC": {"name": "MPC Container Ships", "aliases": ["mpc container ships"]},
        "ELO": {"name": "Elopak", "aliases": ["elopak"]},
        "PEXIP": {"name": "Pexip", "aliases": ["pexip"]},
        "XPLRA": {"name": "Xplora Technologies", "aliases": ["xplora"]},
        "EQNR": {"name": "Equinor", "aliases": ["equinor"]},
        "DNB": {"name": "DNB", "aliases": ["dnb"]},
        "NHY": {"name": "Norsk Hydro", "aliases": ["norsk hydro"]},
        "YAR": {"name": "Yara International", "aliases": ["yara international", "yara"]},
        "MOWI": {"name": "Mowi", "aliases": ["mowi"]},
        "SALM": {"name": "SalMar", "aliases": ["salmar"]},
        "GJF": {"name": "Gjensidige Forsikring", "aliases": ["gjensidige"]},
        "TEL": {"name": "Telenor", "aliases": ["telenor"]},
        "ORK": {"name": "Orkla", "aliases": ["orkla"]},
        "TOM": {"name": "Tomra Systems", "aliases": ["tomra"]},
        "KOG": {"name": "Kongsberg Gruppen", "aliases": ["kongsberg gruppen", "kongsberg"]},
        "NAS": {"name": "Norwegian Air Shuttle", "aliases": ["norwegian air shuttle"]},
        "AKRBP": {"name": "Aker BP", "aliases": ["aker bp"]},
        "AKSO": {"name": "Aker Solutions", "aliases": ["aker solutions"]},
        "SUBC": {"name": "Subsea 7", "aliases": ["subsea 7"]},
        "BWLPG": {"name": "BW LPG", "aliases": ["bw lpg"]},
        "HAUTO": {"name": "Höegh Autoliners", "aliases": ["höegh autoliners", "hoegh autoliners"]},
        "GOGL": {"name": "Golden Ocean", "aliases": ["golden ocean"]},
        "VAR": {"name": "Vår Energi", "aliases": ["vår energi", "var energi"]},
    }

    PHRASES = (
        "Primary Insider Transaction",
        "Primærinsidetransaksjon",
        "Mandatory Notification of Trade Primary Insiders",
        "Meldepliktig handel for primærinnsidere",
        "Notification of Trade by Primary Insider",
        "Notification of Trade by PDMR",
        "Mandatory notification of trade",
    )

    MONTHS = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "mai": 5,
        "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "okt": 10,
        "nov": 11, "dec": 12, "des": 12,
    }

    def norm(value):
        value = (value or "").lower().replace("ø", "o").replace("æ", "ae").replace("å", "a")
        return re.sub(r"[^a-z0-9]+", " ", value).strip()

    def issuer_matches(text, ticker, company_name=""):
        n = norm(text)
        info = ISSUERS.get((ticker or "").upper(), {})
        aliases = list(info.get("aliases", []))
        if company_name:
            aliases.append(company_name)
        aliases.append((ticker or "").upper())
        return any(norm(alias) and norm(alias) in n for alias in aliases)

    def parse_date(value):
        value = value or ""
        m = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b", value)
        if m:
            return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        m = re.search(r"\b(\d{1,2})\s+([A-Za-z]{3})\s+(20\d{2})\b", value)
        if m and m.group(2).lower() in MONTHS:
            return f"{m.group(3)}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
        m = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", value)
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None

    def clean_html(html):
        parser = _TextParser()
        parser.feed(html or "")
        return " ".join((parser.text or "").split()), parser.links

    def direction_from_text(text):
        n = norm(text)
        if re.search(r"\b(purchased|purchase|bought|buy|acquired|kjopt|kjopte|kjopt|kjøpt|kjøpte|kjøp)\b", n):
            return "buy"
        if re.search(r"\b(sold|sell|sale|disposed|disposed of|avhendet|solgt|solgte|salg)\b", n):
            return "sell"
        return "unknown"

    def parse_trade(text, ticker, title, source, url=None):
        raw = " ".join(unescape(text or "").split())
        direction = direction_from_text(raw)
        date = parse_date(raw)

        shares = None
        for pattern in (
            r"(?:purchased|purchase|bought|acquired|sold|disposed(?:\s+of)?|buy|sell).{0,160}?(\d[\d .,\u00a0]{0,20})\s+shares?",
            r"(?:kjøpt|kjopte|kjøp|solgt|solgte|salg).{0,120}?(\d[\d .,\u00a0]{0,20})\s+aksjer",
            r"(\d[\d .,\u00a0]{0,20})\s+shares?\s+(?:in|of)",
        ):
            m = re.search(pattern, raw, re.I)
            if m:
                digits = re.sub(r"[^0-9]", "", m.group(1))
                if digits:
                    shares = int(digits)
                    break

        price = None
        price_match = re.search(r"(?:NOK|kr)\s*([0-9]+(?:[.,][0-9]+)?)\s*(?:per|/)?\s*share", raw, re.I)
        if price_match:
            try:
                price = float(price_match.group(1).replace(",", "."))
            except Exception:
                price = None

        person = None
        person_patterns = (
            r"^(.{2,120}?),\s*(?:CEO|CFO|Chair(?:man)?|Board member|Styremedlem|Konsernsjef|konsernleder)\b",
            r"^(.{2,120}?)\s+(?:has|har)\s+(?:on|den)\s+\d",
        )
        for pattern in person_patterns:
            m = re.search(pattern, raw, re.I)
            if m:
                person = m.group(1).strip(" ,")
                break

        item = {
            "ticker": ticker,
            "date": date,
            "trade_date": date,
            "title": title or "Primary insider transaction",
            "direction": direction,
            "transaction_type": direction if direction in ("buy", "sell") else "other",
            "source": source,
            "verified_detail": bool(date and (direction in ("buy", "sell") or shares is not None or person)),
            "summary": raw[:800],
        }
        if shares is not None:
            item["shares"] = shares
        if price is not None:
            item["price"] = price
        if person:
            item["insider"] = person
        if url:
            item["url"] = url
        return item

    def extract_euronext(html, ticker, company_name):
        text, links = clean_html(html)
        flat = " ".join(text.split())
        rows = []
        phrase_alt = "|".join(re.escape(x) for x in PHRASES)
        date_pat = r"(?:\d{1,2}[./-]\d{1,2}[./-]20\d{2}|\d{1,2}\s+[A-Za-z]{3}\s+20\d{2})"
        aliases = ISSUERS.get(ticker, {}).get("aliases", []) or [company_name]
        alias_alt = "|".join(re.escape(x) for x in aliases if x)

        # Euronext renders archive rows as date -> issuer -> title -> topic.
        patterns = (
            rf"({date_pat}).{{0,120}}?({alias_alt}).{{0,280}}?({phrase_alt})",
            rf"({alias_alt}).{{0,280}}?({phrase_alt}).{{0,180}}?({date_pat})",
        )
        for pattern in patterns:
            for match in re.finditer(pattern, flat, re.I):
                snippet = match.group(0)
                title_match = re.search(phrase_alt, snippet, re.I)
                title = title_match.group(0) if title_match else "Primary insider transaction"
                rows.append(parse_trade(snippet, ticker, title, "Euronext Oslo Børs Newspoint", EURONEXT_ARCHIVE))

        # Follow candidate Euronext links, but validate the actual issuer page before accepting it.
        for href, label in links:
            if not label or not any(norm(p) in norm(label) for p in PHRASES):
                continue
            full = href if href.startswith("http") else "https://live.euronext.com" + href
            try:
                detail_html = self._html(full)
                detail_text, _ = clean_html(detail_html)
                if not issuer_matches(detail_text, ticker, company_name):
                    continue
                item = parse_trade(detail_text, ticker, label, "Euronext Oslo Børs Newspoint", full)
                if item["verified_detail"]:
                    rows.append(item)
            except Exception:
                continue
        return rows

    def extract_newswire(company_name, ticker):
        if not company_name:
            return []
        query = urllib.parse.quote(company_name, safe="")
        try:
            xml = self._html(NEWSWIRE_SEARCH.format(query=query))
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
                if child is elem:
                    continue
                key = child.tag.rsplit("}", 1)[-1].lower()
                value = " ".join("".join(child.itertext()).split())
                if value and key not in fields:
                    fields[key] = value
            title = fields.get("title", "")
            description = fields.get("description") or fields.get("summary") or fields.get("content", "")
            body = " ".join([title, description, fields.get("pubdate", ""), fields.get("published", "")])
            if not issuer_matches(body, ticker, company_name):
                continue
            if not any(norm(p) in norm(title) for p in PHRASES):
                continue
            url = fields.get("link")
            row = parse_trade(body, ticker, title, "GlobeNewswire / issuer release", url)
            if not row.get("date"):
                row["date"] = parse_date(fields.get("pubdate") or fields.get("published") or "")
                row["trade_date"] = row["date"]
            rows.append(row)
        return rows

    def merge_rows(rows):
        merged = []
        for row in rows:
            key = (
                row.get("date"),
                row.get("direction"),
                row.get("shares"),
                norm(row.get("insider")),
                norm(row.get("summary"))[:80],
            )
            # English/Norwegian duplicates often differ only in title. If trade date,
            # direction, shares and insider match, keep the richer row.
            duplicate = None
            for existing in merged:
                same_trade = (
                    row.get("date") and existing.get("date") == row.get("date") and
                    row.get("direction") == existing.get("direction") and
                    row.get("shares") == existing.get("shares") and
                    norm(row.get("insider")) == norm(existing.get("insider"))
                )
                if same_trade and (row.get("shares") is not None or existing.get("shares") is not None):
                    duplicate = existing
                    break
            if duplicate is None:
                merged.append(row)
            else:
                for field in ("price", "insider", "shares", "url", "summary"):
                    if duplicate.get(field) in (None, "") and row.get(field) not in (None, ""):
                        duplicate[field] = row[field]
                duplicate["verified_detail"] = bool(duplicate.get("verified_detail") or row.get("verified_detail"))
                if duplicate.get("source", "").startswith("Euronext") and row.get("verified_detail"):
                    duplicate["detail_source"] = row.get("source")
        return sorted(merged, key=lambda x: x.get("date") or "", reverse=True)

    def insider(self, ticker, company_name=""):
        ticker = (ticker or "").upper()
        info = ISSUERS.get(ticker, {})
        company_name = company_name or info.get("name") or ticker
        now = datetime.now(timezone.utc).isoformat()
        errors = []
        rows = []
        euronext_ok = False

        try:
            html = self._html(EURONEXT_ARCHIVE, params={"keys": ticker, "page": 0})
            euronext_ok = True
            rows.extend(extract_euronext(html, ticker, company_name))
        except Exception as exc:
            errors.append(str(exc))

        try:
            rows.extend(extract_newswire(company_name, ticker))
        except Exception as exc:
            errors.append(str(exc))

        rows = merge_rows(rows)
        verified = [r for r in rows if r.get("verified_detail")]
        buys = sum(1 for r in verified if r.get("direction") == "buy")
        sells = sum(1 for r in verified if r.get("direction") == "sell")
        unknown = len(rows) - buys - sells

        # A successful official feed check with no matching disclosure is a verified
        # neutral state; a parser/network failure is not. Never label an unrelated
        # issuer or a title-only hit as live scoring data.
        if verified:
            status = "live"
            signal = "buying" if buys > sells else "selling" if sells > buys else "activity"
        elif euronext_ok:
            status = "live_empty"
            signal = "no_recent_disclosures"
        else:
            status = "unavailable"
            signal = "unavailable"

        result = {
            "ticker": ticker,
            "items": rows[:12],
            "source": "Euronext Oslo Børs Newspoint + issuer release fallback",
            "status": status,
            "buy_count": buys,
            "sell_count": sells,
            "unknown_count": unknown,
            "verified_detail_count": len(verified),
            "signal": signal,
            "updated_at": now,
        }
        if errors:
            result["debug"] = "; ".join(errors)[:1000]
        return result

    NordicRegulatoryProvider.insider = insider
    NordicRegulatoryProvider._live_insider_patch = True


_install_insider_patch()
