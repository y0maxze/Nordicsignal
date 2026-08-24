from abc import ABC, abstractmethod
from datetime import datetime, timezone
import time
from curl_cffi import requests


class MarketDataProvider(ABC):
    @abstractmethod
    def quote(self, ticker: str) -> dict: raise NotImplementedError
    @abstractmethod
    def historical(self, ticker: str, period: str = "1y") -> list[dict]: raise NotImplementedError
    @abstractmethod
    def research(self, ticker: str) -> dict: raise NotImplementedError


class DemoProvider(MarketDataProvider):
    def quote(self, ticker): return {"ticker": ticker, "price": None, "change_pct": None, "volume": None, "source": "demo"}
    def historical(self, ticker, period="1y"): return []
    def research(self, ticker): return {"ticker": ticker, "source": "demo"}


class YahooProvider(MarketDataProvider):
    """Yahoo Finance adapter using chart data plus browser-like research session."""
    BASES = ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com")
    BASE = BASES[0]
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"

    def __init__(self):
        self.session = requests.Session(impersonate="chrome")
        self.session.headers.update({"User-Agent": self.UA, "Accept": "application/json,text/plain,*/*", "Accept-Language": "en-US,en;q=0.9"})
        self.crumb = None
        self._bootstrap_at = 0

    def symbol(self, ticker: str) -> str:
        ticker = ticker.upper()
        return ticker if "." in ticker else ticker + ".OL"

    def _get(self, url, params=None, need_crumb=False):
        params = dict(params or {})
        if need_crumb:
            self._bootstrap()
            params["crumb"] = self.crumb
        response = self.session.get(url, params=params, timeout=15, allow_redirects=True)
        if response.status_code in (401, 403) and need_crumb:
            self._bootstrap(force=True)
            params["crumb"] = self.crumb
            response = self.session.get(url, params=params, timeout=15, allow_redirects=True)
        if response.status_code >= 400:
            raise RuntimeError(f"Yahoo HTTP {response.status_code}: {response.text[:400]}")
        return response.json()

    def _bootstrap(self, force=False):
        if not force and self.crumb and time.time() - self._bootstrap_at < 1800:
            return
        self.crumb = None
        try: self.session.cookies.clear()
        except Exception: pass
        try: self.session.get("https://fc.yahoo.com", timeout=10, allow_redirects=True)
        except Exception: pass
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
                    self.crumb = crumb; self._bootstrap_at = time.time(); return
                last_error = RuntimeError("Yahoo returned an empty/invalid crumb")
            except Exception as exc: last_error = exc
        raise RuntimeError(f"Yahoo crumb bootstrap failed: {last_error}")

    def quote(self, ticker):
        symbol = self.symbol(ticker)
        data = self._get(f"{self.BASE}/v8/finance/chart/{symbol}", {"range": "5d", "interval": "1d"})
        result = data["chart"]["result"][0]; meta = result.get("meta", {})
        price = meta.get("regularMarketPrice") or meta.get("previousClose"); previous = meta.get("previousClose")
        change = ((price - previous) / previous * 100) if price is not None and previous else None
        volumes = result.get("indicators", {}).get("quote", [{}])[0].get("volume") or []
        return {"ticker": ticker.upper(), "symbol": symbol, "price": price, "previous_close": previous, "change_pct": change, "volume": volumes[-1] if volumes else None, "currency": meta.get("currency"), "exchange": meta.get("exchangeName"), "source": "Yahoo Finance", "captured_at": datetime.now(timezone.utc).isoformat()}

    def historical(self, ticker, period="1y"):
        ranges = {"now": ("1d", "5m"), "1d": ("1d", "5m"), "1w": ("5d", "1h"), "1m": ("1mo", "1d"), "3m": ("3mo", "1d"), "6m": ("6mo", "1d"), "1y": ("1y", "1d"), "5y": ("5y", "1wk"), "10y": ("10y", "1mo"), "max": ("max", "1mo")}
        rng, interval = ranges.get(period, ranges["1y"])
        data = self._get(f"{self.BASE}/v8/finance/chart/{self.symbol(ticker)}", {"range": rng, "interval": interval, "events": "div,splits"})
        result = data["chart"]["result"][0]; timestamps = result.get("timestamp") or []; quote = (result.get("indicators", {}).get("quote") or [{}])[0]
        closes, opens, highs, lows, volumes = quote.get("close") or [], quote.get("open") or [], quote.get("high") or [], quote.get("low") or [], quote.get("volume") or []
        rows = []
        for i, ts in enumerate(timestamps):
            if i >= len(closes) or closes[i] is None: continue
            rows.append({"timestamp": ts, "date": datetime.fromtimestamp(ts, timezone.utc).isoformat(), "open": opens[i] if i < len(opens) else None, "high": highs[i] if i < len(highs) else None, "low": lows[i] if i < len(lows) else None, "close": closes[i], "volume": volumes[i] if i < len(volumes) else None})
        return rows

    def fundamentals(self, ticker):
        """Fetch fundamentals through Yahoo's timeseries endpoint, which does not use quoteSummary crumbs."""
        symbol = self.symbol(ticker)
        types = [
            "annualTotalRevenue","annualEBITDA","annualEBIT","annualNetIncome",
            "annualDilutedEPS","annualOperatingCashFlow","annualFreeCashFlow",
            "annualTotalDebt","annualStockholdersEquity","annualGrossProfit",
            "annualOperatingIncome","annualPretaxIncome","annualBasicAverageShares",
            "quarterlyTotalRevenue","quarterlyEBITDA","quarterlyDilutedEPS",
            "quarterlyOperatingCashFlow","quarterlyFreeCashFlow"
        ]
        params = {"symbol": symbol, "type": ",".join(types), "period1": "946684800", "period2": str(int(time.time()) + 86400)}
        last_error = None
        for base in self.BASES:
            try:
                data = self._get(f"{base}/ws/fundamentals-timeseries/v1/finance/timeseries/{symbol}", params)
                result = data.get("timeseries", {}).get("result") or []
                if result:
                    latest = {}
                    for series in result:
                        for key, value in series.items():
                            if key in ("meta", "timestamp"): continue
                            if isinstance(value, list) and value:
                                latest[key] = value
                    return {"ticker": ticker.upper(), "symbol": symbol, "series": latest, "source": "Yahoo Finance Timeseries", "captured_at": datetime.now(timezone.utc).isoformat()}
                last_error = RuntimeError("Yahoo returned no fundamentals timeseries")
            except Exception as exc: last_error = exc
        raise RuntimeError(f"Yahoo fundamentals failed for {symbol}: {last_error}")

    def research(self, ticker):
        modules = "price,summaryDetail,defaultKeyStatistics,financialData,insiderTransactions,insiderHolders"
        last_error = None
        for attempt in range(2):
            try:
                self._bootstrap(force=attempt > 0)
                params = {"modules": modules, "formatted": "false", "lang": "en-US", "region": "US", "crumb": self.crumb}
                for base in self.BASES:
                    try:
                        data = self._get(f"{base}/v10/finance/quoteSummary/{self.symbol(ticker)}", params, need_crumb=False)
                        result = data.get("quoteSummary", {}).get("result") or []
                        if result: return result[0]
                        last_error = RuntimeError("Yahoo returned no quoteSummary result")
                    except Exception as exc: last_error = exc
            except Exception as exc: last_error = exc
        raise RuntimeError(f"Yahoo research failed for {self.symbol(ticker)}: {last_error}")


class RealtimeProvider(YahooProvider):
    pass