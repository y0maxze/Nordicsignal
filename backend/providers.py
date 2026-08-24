from abc import ABC, abstractmethod
from datetime import datetime, timezone
import re
import time
from html.parser import HTMLParser

from curl_cffi import requests


class MarketDataProvider(ABC):
    @abstractmethod
    def quote(self, ticker: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def historical(self, ticker: str, period: str = "1y") -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def research(self, ticker: str) -> dict:
        raise NotImplementedError


class DemoProvider(MarketDataProvider):
    def quote(self, ticker):
        return {"ticker": ticker, "price": None, "change_pct": None, "volume": None, "source": "demo"}

    def historical(self, ticker, period="1y"):
        return []

    def research(self, ticker):
        return {"ticker": ticker, "source": "demo"}


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.links = []
        self._href = None
        self._link_text = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self._href = attrs.get("href")
            self._link_text = []
        if tag in ("script", "style", "noscript"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            text = " ".join(self._link_text).strip()
            self.links.append((self._href, text))
            self._href = None
            self._link_text = []
        if tag in ("script", "style", "noscript"):
            self._skip = max(0, self._skip - 1)

    def handle_data(self, data):
        if self._skip:
            return
        text = " ".join(data.split())
        if text:
            self.parts.append(text)
            if self._href is not None:
                self._link_text.append(text)

    @property
    def text(self):
        return " ".join(self.parts)


class YahooProvider(MarketDataProvider):
    BASES = ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com")
    BASE = BASES[0]
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"

    def __init__(self):
        self.session = requests.Session(impersonate="chrome")
        self.session.headers.update({
            "User-Agent": self.UA,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self.crumb = None
        self._bootstrap_at = 0

    def symbol(self, ticker: str) -> str:
        ticker = ticker.upper()
        return ticker if "." in ticker else ticker + ".OL"

    def _get(self, url, params=None, need_crumb=False):
        p = dict(params or {})
        if need_crumb:
            self._bootstrap()
            p["crumb"] = self.crumb
        response = self.session.get(url, params=p, timeout=15, allow_redirects=True)
        if response.status_code in (401, 403) and need_crumb:
            self._bootstrap(force=True)
            p["crumb"] = self.crumb
            response = self.session.get(url, params=p, timeout=15, allow_redirects=True)
        if response.status_code >= 400:
            raise RuntimeError(f"Yahoo HTTP {response.status_code}: {response.text[:400]}")
        return response.json()

    def _bootstrap(self, force=False):
        if not force and self.crumb and time.time() - self._bootstrap_at < 1800:
            return
        self.crumb = None
        try:
            self.session.cookies.clear()
        except Exception:
            pass
        try:
            self.session.get("https://fc.yahoo.com", timeout=10, allow_redirects=True)
        except Exception:
            pass
        if not list(self.session.cookies):
            raise RuntimeError("Yahoo did not provide a session cookie")
        last_error = None
        for base in self.BASES:
            try:
                response = self.session.get(base + "/v1/test/getcrumb", headers={"Accept": "text/plain"}, timeout=10, allow_redirects=True)
                if response.status_code >= 400:
                    raise RuntimeError(f"crumb HTTP {response.status_code}: {response.text[:200]}")
                crumb = response.text.strip()
                if crumb and "unauthorised" not in crumb.lower() and "<html" not in crumb.lower():
                    self.crumb = crumb
                    self._bootstrap_at = time.time()
                    return
                last_error = RuntimeError("Yahoo returned an empty/invalid crumb")
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"Yahoo crumb bootstrap failed: {last_error}")

    def quote(self, ticker):
        symbol = self.symbol(ticker)
        data = self._get(f"{self.BASE}/v8/finance/chart/{symbol}", {"range": "5d", "interval": "1d"})
        result = data["chart"]["result"][0]
        meta = result.get("meta", {})
        price = meta.get("regularMarketPrice") or meta.get("previousClose")
        previous = meta.get("previousClose")
        change = ((price - previous) / previous * 100) if price is not None and previous else None
        volumes = result.get("indicators", {}).get("quote", [{}])[0].get("volume") or []
        return {
            "ticker": ticker.upper(), "symbol": symbol, "price": price, "previous_close": previous,
            "change_pct": change, "volume": volumes[-1] if volumes else None,
            "currency": meta.get("currency"), "exchange": meta.get("exchangeName"),
            "source": "Yahoo Finance", "captured_at": datetime.now(timezone.utc).isoformat(),
        }

    def historical(self, ticker, period="1y"):
        ranges = {"now": ("1d", "5m"), "1d": ("1d", "5m"), "1w": ("5d", "1h"), "1m": ("1mo", "1d"), "3m": ("3mo", "1d"), "6m": ("6mo", "1d"), "1y": ("1y", "1d"), "5y": ("5y", "1wk"), "10y": ("10y", "1mo"), "max": ("max", "1mo")}
        rng, interval = ranges.get(period, ranges["1y"])
        data = self._get(f"{self.BASE}/v8/finance/chart/{self.symbol(ticker)}", {"range": rng, "interval": interval, "events": "div,splits"})
        result = data["chart"]["result"][0]
        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators", {}).get("quote") or [{}])[0]
        closes, opens, highs, lows, volumes = quote.get("close") or [], quote.get("open") or [], quote.get("high") or [], quote.get("low") or [], quote.get("volume") or []
        rows = []
        for i, ts in enumerate(timestamps):
            if i >= len(closes) or closes[i] is None:
                continue
            rows.append({"timestamp": ts, "date": datetime.fromtimestamp(ts, timezone.utc).isoformat(), "open": opens[i] if i < len(opens) else None, "high": highs[i] if i < len(highs) else None, "low": lows[i] if i < len(lows) else None, "close": closes[i], "volume": volumes[i] if i < len(volumes) else None})
        return rows

    def fundamentals(self, ticker):
        symbol = self.symbol(ticker)
        types = ["annualTotalRevenue", "annualEBITDA", "annualEBIT", "annualNetIncome", "annualDilutedEPS", "annualOperatingCashFlow", "annualFreeCashFlow", "annualTotalDebt", "annualStockholdersEquity", "annualGrossProfit", "annualOperatingIncome", "annualPretaxIncome", "annualBasicAverageShares", "quarterlyTotalRevenue", "quarterlyEBITDA", "quarterlyDilutedEPS", "quarterlyOperatingCashFlow", "quarterlyFreeCashFlow"]
        params = {"symbol": symbol, "type": ",".join(types), "period1": "946684800", "period2": str(int(time.time()) + 86400)}
        last_error = None
        for base in self.BASES:
            try:
                data = self._get(f"{base}/ws/fundamentals-timeseries/v1/finance/timeseries/{symbol}", params)
                result = data.get("timeseries", {}).get("result") or []
                if result:
                    normalized = []
                    for row in result:
                        if not isinstance(row, dict):
                            continue
                        clean = dict(row)
                        for key, value in list(clean.items()):
                            if isinstance(value, list):
                                clean[key] = [self._normalize_timeseries_row(item) for item in value]
                        normalized.append(clean)
                    return {"ticker": ticker.upper(), "symbol": symbol, "series": normalized, "source": "Yahoo Finance Timeseries", "captured_at": datetime.now(timezone.utc).isoformat()}
                last_error = RuntimeError("Yahoo returned no fundamentals timeseries")
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"Yahoo fundamentals failed for {symbol}: {last_error}")

    @staticmethod
    def _normalize_timeseries_row(row):
        if not isinstance(row, dict):
            return row
        clean = dict(row)
        reported = clean.get("reportedValue")
        if isinstance(reported, dict) and isinstance(reported.get("raw"), (int, float)):
            clean["reportedValue"] = reported["raw"]
        return clean

    @staticmethod
    def _latest(values):
        candidates = []
        for row in values or []:
            if not isinstance(row, dict):
                continue
            value = row.get("reportedValue")
            if isinstance(value, dict):
                value = value.get("raw")
            if isinstance(value, (int, float)):
                candidates.append((row.get("asOfDate", ""), float(value)))
        return sorted(candidates, key=lambda x: x[0])[-1][1] if candidates else None

    def research(self, ticker):
        q = self.quote(ticker)
        f = self.fundamentals(ticker)
        flat = {}
        for item in f.get("series", []):
            for key, value in item.items():
                if key not in ("meta", "timestamp"):
                    flat[key] = value
        revenue = self._latest(flat.get("annualTotalRevenue")); ebitda = self._latest(flat.get("annualEBITDA")); ebit = self._latest(flat.get("annualEBIT")); net_income = self._latest(flat.get("annualNetIncome")); eps = self._latest(flat.get("annualDilutedEPS")); ocf = self._latest(flat.get("annualOperatingCashFlow")); fcf = self._latest(flat.get("annualFreeCashFlow")); debt = self._latest(flat.get("annualTotalDebt")); equity = self._latest(flat.get("annualStockholdersEquity")); gross = self._latest(flat.get("annualGrossProfit")); opinc = self._latest(flat.get("annualOperatingIncome")); pretax = self._latest(flat.get("annualPretaxIncome")); shares = self._latest(flat.get("annualBasicAverageShares"))
        price = q.get("price")
        market_cap = price * shares if price is not None and shares else None
        pe = price / eps if price is not None and eps and eps > 0 else None
        pb = market_cap / equity if market_cap is not None and equity and equity > 0 else None
        ev = (market_cap + debt) if market_cap is not None and debt is not None else None
        ev_ebitda = ev / ebitda if ev is not None and ebitda and ebitda > 0 else None
        return {
            "summaryDetail": {"regularMarketPrice": price, "trailingPE": pe, "priceToBook": pb, "marketCap": market_cap},
            "defaultKeyStatistics": {"trailingEps": eps, "priceToBook": pb, "enterpriseToEbitda": ev_ebitda, "sharesOutstanding": shares},
            "financialData": {"currentPrice": price, "totalRevenue": revenue, "ebitda": ebitda, "ebit": ebit, "netIncomeToCommon": net_income, "freeCashflow": fcf, "operatingCashflow": ocf, "totalDebt": debt, "grossProfits": gross, "operatingIncome": opinc, "returnOnEquity": (net_income / equity) if net_income is not None and equity else None, "grossMargins": (gross / revenue) if gross is not None and revenue else None, "ebitdaMargins": (ebitda / revenue) if ebitda is not None and revenue else None, "operatingMargins": (opinc / revenue) if opinc is not None and revenue else None, "debtToEquity": (debt / equity * 100) if debt is not None and equity else None},
            "insiderTransactions": {"transactions": []}, "insiderHolders": {"holders": []}, "price": q,
            "fundamentals": {"revenue": revenue, "ebitda": ebitda, "ebit": ebit, "net_income": net_income, "eps": eps, "operating_cashflow": ocf, "free_cashflow": fcf, "debt": debt, "equity": equity, "gross_profit": gross, "operating_income": opinc, "pretax_income": pretax, "shares": shares},
            "_annual_series": flat, "source": "Yahoo Finance Timeseries + Chart", "captured_at": datetime.now(timezone.utc).isoformat(),
        }


class NordicRegulatoryProvider:
    """Official Norwegian/Euronext sources for public short positions and insider disclosures."""
    SHORT_API = "https://ssr.finanstilsynet.no/api/v2/instruments"
    EURONEXT_NEWS = "https://live.euronext.com/en/markets/oslo/equities/company-news"

    def __init__(self):
        self.session = requests.Session(impersonate="chrome")
        self.session.headers.update({"User-Agent": YahooProvider.UA, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9,nb;q=0.8"})
        self._short_cache = None
        self._short_cache_at = 0

    def _json(self, url):
        r = self.session.get(url, timeout=20, allow_redirects=True)
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        return r.json()

    def _html(self, url, params=None):
        r = self.session.get(url, params=params, timeout=20, allow_redirects=True)
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        return r.text

    @staticmethod
    def _norm(value):
        return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()

    def short(self, ticker, company_name=""):
        if self._short_cache is None or time.time() - self._short_cache_at > 900:
            self._short_cache = self._json(self.SHORT_API)
            self._short_cache_at = time.time()
        target = self._norm(company_name)
        aliases = {"LSG": ["leroy seafood", "lerøy seafood"], "MPCC": ["mpcc"], "ELO": ["elopak"], "PEXIP": ["pexip"], "XPLRA": ["xplora"], "EQNR": ["equinor"], "DNB": ["dnb"], "NHY": ["norsk hydro"], "YAR": ["yara"], "MOWI": ["mowi"], "SALM": ["salmar"], "GJF": ["gjensidige"], "TEL": ["telenor"], "ORK": ["orkla"], "TOM": ["tomra"], "KOG": ["kongsberg"], "NAS": ["norwegian air shuttle"], "AKRBP": ["aker bp"], "AKSO": ["aker solutions"], "SUBC": ["subsea 7"], "BWLPG": ["bw lpg"], "HAUTO": ["hoegh autoliners", "höegh autoliners"], "GOGL": ["golden ocean"], "VAR": ["var energi", "vår energi"]}
        candidates = aliases.get(ticker.upper(), [])
        if target:
            candidates.append(target)
        matches = []
        for instrument in self._short_cache or []:
            issuer = self._norm(instrument.get("issuerName", ""))
            if not issuer or not any(c in issuer or issuer in c for c in candidates):
                continue
            events = instrument.get("events") or []
            if events:
                latest = sorted(events, key=lambda x: x.get("date", ""), reverse=True)[0]
                matches.append({"isin": instrument.get("isin"), "issuer_name": instrument.get("issuerName"), "date": latest.get("date"), "short_percent": latest.get("shortPercent"), "shares": latest.get("shares"), "active_positions": latest.get("activePositions") or [], "source": "Finanstilsynet Short Sale Register"})
        if not matches:
            return {"ticker": ticker.upper(), "source": "Finanstilsynet Short Sale Register", "items": [], "short_percent_float": None, "short_ratio": None, "status": "no_public_position", "updated_at": datetime.now(timezone.utc).isoformat()}
        latest = max(matches, key=lambda x: x.get("date") or "")
        return {"ticker": ticker.upper(), "source": "Finanstilsynet Short Sale Register", "items": matches[:10], "short_percent_float": latest.get("short_percent"), "short_ratio": None, "shares": latest.get("shares"), "latest_date": latest.get("date"), "status": "public_position", "updated_at": datetime.now(timezone.utc).isoformat()}

    def insider(self, ticker):
        ticker = ticker.upper()
        html_text = self._html(self.EURONEXT_NEWS, {"keys": ticker, "page": 0})
        parser = _TextParser(); parser.feed(html_text)
        links, seen = [], set()
        for href, text in parser.links:
            if not href or "/products/equities/company-news/" not in href:
                continue
            full = href if href.startswith("http") else "https://live.euronext.com" + href
            low = (text or "").lower()
            if any(k in low for k in ("insider", "primary", "primær", "pdmr")) and full not in seen:
                seen.add(full); links.append((full, text))
            if len(links) >= 8:
                break
        items = []
        for url, link_text in links:
            try:
                page = self._html(url)
                p = _TextParser(); p.feed(page); body = p.text; low = body.lower()
                if not any(k in low for k in ("primary insider", "primærinnsider", "mandatory notification", "pdmr")):
                    continue
                transaction_type = "other"
                if re.search(r"\b(bought|buy|purchased|acquired|purchase)\b", low): transaction_type = "buy"
                elif re.search(r"\b(sold|sell|disposed|sale)\b", low): transaction_type = "sell"
                shares = price = None
                pattern = re.search(r"(?:bought|purchased|acquired|sold|disposed of|purchase|sale).{0,120}?(\d[\d\s.,]*)\s+shares.{0,100}?(?:NOK\s*)?(\d+(?:[.,]\d+)?)", body, flags=re.I)
                if pattern:
                    try: shares = float(re.sub(r"[^\d]", "", pattern.group(1)))
                    except Exception: pass
                    try: price = float(pattern.group(2).replace(",", "."))
                    except Exception: pass
                date_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", body)
                items.append({"ticker": ticker, "transaction_type": transaction_type, "shares": shares, "price": price, "trade_date": date_match.group(1) if date_match else None, "title": link_text or "Primary insider disclosure", "source": "Euronext Oslo Børs / Oslo Børs Newspoint", "url": url})
            except Exception:
                continue
        dedup = {item["url"]: item for item in items}
        items = list(dedup.values())[:8]
        buys = sum(1 for x in items if x["transaction_type"] == "buy")
        sells = sum(1 for x in items if x["transaction_type"] == "sell")
        signal = "buying" if buys > sells else "selling" if sells > buys else "mixed" if items else "unavailable"
        return {"ticker": ticker, "items": items, "source": "Euronext Oslo Børs / Oslo Børs Newspoint", "status": "live" if items else "no_recent_disclosures", "buy_count": buys, "sell_count": sells, "signal": signal, "updated_at": datetime.now(timezone.utc).isoformat()}


class RealtimeProvider(YahooProvider):
    pass
