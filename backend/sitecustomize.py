"""Live primary-insider parser patch for NordicSignal."""
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

    EURONEXT = "https://live.euronext.com/en/listview/company-press-releases/1061"
    NEWSWIRE = "https://rss.globenewswire.com/WpFeed/search/{q}/timezone/Eastern%20Standard%20Time/dateFormat/MMM%20dd%20yyyy%20hh:mm"
    ISSUERS = {
        "LSG": ("Lerøy Seafood Group ASA", ("lerøy seafood", "leroy seafood", "lerøy seafood group", "leroy seafood group")),
        "MPCC": ("MPC Container Ships", ("mpc container ships",)), "ELO": ("Elopak", ("elopak",)),
        "PEXIP": ("Pexip", ("pexip",)), "XPLRA": ("Xplora Technologies", ("xplora",)),
        "EQNR": ("Equinor", ("equinor",)), "DNB": ("DNB", ("dnb",)),
        "NHY": ("Norsk Hydro", ("norsk hydro",)), "YAR": ("Yara International", ("yara international", "yara")),
        "MOWI": ("Mowi", ("mowi",)), "SALM": ("SalMar", ("salmar",)),
        "GJF": ("Gjensidige Forsikring", ("gjensidige",)), "TEL": ("Telenor", ("telenor",)),
        "ORK": ("Orkla", ("orkla",)), "TOM": ("Tomra Systems", ("tomra",)),
        "KOG": ("Kongsberg Gruppen", ("kongsberg gruppen", "kongsberg")),
        "NAS": ("Norwegian Air Shuttle", ("norwegian air shuttle",)), "AKRBP": ("Aker BP", ("aker bp",)),
        "AKSO": ("Aker Solutions", ("aker solutions",)), "SUBC": ("Subsea 7", ("subsea 7",)),
        "BWLPG": ("BW LPG", ("bw lpg",)), "HAUTO": ("Höegh Autoliners", ("höegh autoliners", "hoegh autoliners")),
        "GOGL": ("Golden Ocean", ("golden ocean",)), "VAR": ("Vår Energi", ("vår energi", "var energi")),
    }
    PHRASES = ("Primary Insider Transaction", "Primærinsidetransaksjon", "Mandatory Notification of Trade Primary Insiders", "Meldepliktig handel for primærinnsidere", "Notification of Trade by Primary Insider", "Notification of Trade by PDMR", "Mandatory notification of trade")
    MONTHS = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"mai":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"okt":10,"nov":11,"dec":12,"des":12}

    def norm(v):
        return re.sub(r"[^a-z0-9]+", " ", (v or "").lower().replace("ø","o").replace("æ","ae").replace("å","a")).strip()

    def matches(text, ticker, company_name=""):
        n = norm(text); name, aliases = ISSUERS.get(ticker, (company_name or ticker, ()))
        return any(norm(x) and norm(x) in n for x in (name, *aliases, company_name, ticker))

    def parse_date(v):
        v = v or ""
        m = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b", v)
        if m: return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        m = re.search(r"\b(\d{1,2})\s+([A-Za-z]{3})\s+(20\d{2})\b", v)
        if m and m.group(2).lower() in MONTHS: return f"{m.group(3)}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
        m = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", v)
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None

    def text_of(html):
        p = _TextParser(); p.feed(html or ""); return " ".join((p.text or "").split()), p.links

    def direction(v):
        n = norm(v)
        if re.search(r"\b(purchased|purchase|bought|buy|acquired|kjopt|kjopte|kjøpt|kjøpte|kjøp)\b", n): return "buy"
        if re.search(r"\b(sold|sell|sale|disposed|avhendet|solgt|solgte|salg)\b", n): return "sell"
        return "unknown"

    def trade_item(body, ticker, title, source, url=None):
        raw = " ".join(unescape(body or "").split()); d = direction(raw); date = parse_date(raw); shares = None
        for pat in (r"(?:purchased|purchase|bought|acquired|sold|disposed(?: of)?|buy|sell).{0,160}?(\d[\d .,\u00a0]{0,20})\s+shares?", r"(?:kjøpt|kjopte|kjøp|solgt|solgte|salg).{0,120}?(\d[\d .,\u00a0]{0,20})\s+aksjer", r"(\d[\d .,\u00a0]{0,20})\s+shares?\s+(?:in|of)"):
            m = re.search(pat, raw, re.I)
            if m:
                digits = re.sub(r"[^0-9]", "", m.group(1))
                if digits: shares = int(digits); break
        person = None
        for pat in (r"^(.{2,120}?),\s*(?:CEO|CFO|Chair(?:man)?|Board member|Styremedlem|Konsernsjef)\b", r"^(.{2,120}?)\s+(?:has|har)\s+(?:on|den)\s+\d"):
            m = re.search(pat, raw, re.I)
            if m: person = m.group(1).strip(" ,"); break
        item = {"ticker": ticker, "date": date, "trade_date": date, "title": title or "Primary insider transaction", "direction": d, "transaction_type": d if d in ("buy","sell") else "other", "source": source, "verified_detail": bool(date and (d in ("buy","sell") or shares is not None or person)), "summary": raw[:800]}
        if shares is not None: item["shares"] = shares
        if person: item["insider"] = person
        if url: item["url"] = url
        return item

    def euronext_rows(html, ticker, company_name):
        text, links = text_of(html); rows=[]; phrases="|".join(re.escape(x) for x in PHRASES); dates=r"(?:\d{1,2}[./-]\d{1,2}[./-]20\d{2}|\d{1,2}\s+[A-Za-z]{3}\s+20\d{2})"
        aliases=ISSUERS.get(ticker,(company_name,(company_name,)))[1] or (company_name,); names="|".join(re.escape(x) for x in aliases if x)
        for pat in (rf"({dates}).{{0,120}}?({names}).{{0,280}}?({phrases})", rf"({names}).{{0,280}}?({phrases}).{{0,180}}?({dates})"):
            for m in re.finditer(pat, text, re.I):
                title=(re.search(phrases,m.group(0),re.I) or ["Primary insider transaction"])[0]
                rows.append(trade_item(m.group(0),ticker,title,"Euronext Oslo Børs Newspoint",EURONEXT))
        for href,label in links:
            if not label or not any(norm(p) in norm(label) for p in PHRASES): continue
            full=href if href.startswith("http") else "https://live.euronext.com"+href
            try:
                detail=text_of(self._html(full))[0]
                if not matches(detail,ticker,company_name): continue
                item=trade_item(detail,ticker,label,"Euronext Oslo Børs Newspoint",full)
                if item["verified_detail"]: rows.append(item)
            except Exception: pass
        return rows

    def newswire_rows(company_name,ticker):
        if not company_name: return []
        try: root=ET.fromstring(self._html(NEWSWIRE.format(q=urllib.parse.quote(company_name,safe=""))))
        except Exception: return []
        rows=[]
        for elem in root.iter():
            if elem.tag.rsplit("}",1)[-1].lower() not in ("item","entry"): continue
            fields={}
            for child in elem.iter():
                if child is elem: continue
                k=child.tag.rsplit("}",1)[-1].lower(); v=" ".join("".join(child.itertext()).split())
                if v and k not in fields: fields[k]=v
            title=fields.get("title",""); desc=fields.get("description") or fields.get("summary") or fields.get("content",""); body=" ".join((title,desc,fields.get("pubdate",""),fields.get("published","")))
            if not matches(body,ticker,company_name) or not any(norm(p) in norm(title) for p in PHRASES): continue
            rows.append(trade_item(body,ticker,title,"GlobeNewswire / issuer release",fields.get("link")))
        return rows

    def merge(rows):
        out=[]
        for row in rows:
            dup=next((x for x in out if row.get("date") and x.get("date")==row.get("date") and x.get("direction")==row.get("direction") and x.get("shares")==row.get("shares") and norm(x.get("insider"))==norm(row.get("insider")) and (x.get("shares") is not None or row.get("shares") is not None)),None)
            if not dup: out.append(row); continue
            for k in ("shares","insider","url","summary"):
                if dup.get(k) in (None,"") and row.get(k) not in (None,""): dup[k]=row[k]
            dup["verified_detail"]=bool(dup.get("verified_detail") or row.get("verified_detail"))
        return sorted(out,key=lambda x:x.get("date") or "",reverse=True)

    def insider(self,ticker,company_name=""):
        ticker=(ticker or "").upper(); company_name=company_name or ISSUERS.get(ticker,(ticker,()))[0]; now=datetime.now(timezone.utc).isoformat(); rows=[]; errors=[]; feed_relevant=False
        try:
            html=self._html(EURONEXT,params={"keys":ticker,"page":0}); feed_relevant=matches(html,ticker,company_name) and any(norm(p) in norm(html) for p in PHRASES); rows.extend(euronext_rows(html,ticker,company_name))
        except Exception as exc: errors.append(str(exc))
        try: rows.extend(newswire_rows(company_name,ticker))
        except Exception as exc: errors.append(str(exc))
        rows=merge(rows); verified=[x for x in rows if x.get("verified_detail")]; buys=sum(x.get("direction")=="buy" for x in verified); sells=sum(x.get("direction")=="sell" for x in verified)
        if verified: status="live"; signal="buying" if buys>sells else "selling" if sells>buys else "activity"
        elif feed_relevant: status="live"; signal="no_recent_disclosures"
        else: status="unavailable"; signal="unavailable"
        result={"ticker":ticker,"items":rows[:12],"source":"Euronext Oslo Børs Newspoint + issuer release fallback","status":status,"buy_count":buys,"sell_count":sells,"unknown_count":len(rows)-buys-sells,"verified_detail_count":len(verified),"signal":signal,"updated_at":now}
        if errors: result["debug"]="; ".join(errors)[:1000]
        return result

    NordicRegulatoryProvider.insider=insider
    NordicRegulatoryProvider._live_insider_patch=True

_install_insider_patch()
