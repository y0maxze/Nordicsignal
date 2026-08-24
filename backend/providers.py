from abc import ABC, abstractmethod
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json
import time

import requests


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


class YahooProvider(MarketDataProvider):
    """Yahoo Finance adapter for Oslo-listed symbols."""
    BASES = ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com")
    BASE = BASES[0]
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"

    def __init__(self):
        self.cookie = None
        self.crumb = None
        self._bootstrap_at = 0
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.UA, "Accept": "application/json,text/plain,*/*"})

    def symbol(self, ticker: str) -> str:
        ticker = ticker.upper()
        return ticker if "." in ticker else ticker + ".OL"

    def _get(self, url, params=None, headers=None):
        response = self.session.get(url, params=params, headers=headers, timeout=15)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            body = response.text[:500]
            raise RuntimeError(f"Yahoo HTTP {response.status_code}: {body}") from exc
        return response.json()

    def _bootstrap(self):
        if self.crumb and self.cookie and time.time() - self._bootstrap_at < 1800:
            return

        # Keep the cookie and crumb in the SAME requests.Session. Yahoo binds
        # the crumb to the session cookie. fc.yahoo.com may return 404 by design,
        # but the response still sets the A3 session cookie.
        self.session.cookies.clear()
        self.crumb = None
        self.cookie = None

        try:
            self.session.get("https://fc.yahoo.com", timeout=12, allow_redirects=True)
        except requests.RequestException:
            pass

        cookie_values = [f"{c.name}={c.value}" for c in self.session.cookies]
        self.cookie = "; ".join(cookie_values) or None
        if not self.cookie:
            raise RuntimeError("Yahoo did not provide a session cookie")

        last_error = None
        for base in self.BASES:
            try:
                response = self.session.get(
                    base + "/v1/test/getcrumb",
                    headers={"Accept": "text/plain"},
                    timeout=12,
                    allow_redirects=True,
                )
                response.raise_for_status()
                crumb = response.text.strip()
                if crumb and not crumb.lower().startswith("unauthorised") and "<html" not in crumb.lower():
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
            "ticker": ticker.upper(),
            "symbol": symbol,
            "price": price,
            "previous_close": previous,
            "change_pct": change,
            "volume": volumes[-1] if volumes else None,
            "currency": meta.get("currency"),
            "exchange": meta.get("exchangeName"),
            "source": "Yahoo Finance",
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }

    def historical(self, ticker, period="1y"):
        ranges = {
            "now": ("1d", "5m"), "1d": ("1d", "5m"), "1w": ("5d", "1h"),
            "1m": ("1mo", "1d"), "3m": ("3mo", "1d"), "6m": ("6mo", "1d"),
            "1y": ("1y", "1d"), "5y": ("5y", "1wk"), "10y": ("10y", "1mo"),
            "max": ("max", "1mo"),
        }
        rng, interval = ranges.get(period, ranges["1y"])
        data = self._get(f"{self.BASE}/v8/finance/chart/{self.symbol(ticker)}", {"range": rng, "interval": interval, "events": "div,splits"})
        result = data["chart"]["result"][0]
        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators", {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        volumes = quote.get("volume") or []
        rows = []
        for i, ts in enumerate(timestamps):
            if i >= len(closes) or closes[i] is None:
                continue
            rows.append({
                "timestamp": ts,
                "date": datetime.fromtimestamp(ts, timezone.utc).isoformat(),
                "open": opens[i] if i < len(opens) else None,
                "high": highs[i] if i < len(highs) else None,
                "low": lows[i] if i < len(lows) else None,
                "close": closes[i],
                "volume": volumes[i] if i < len(volumes) else None,
            })
        return rows

    def research(self, ticker):
        self._bootstrap()
        modules = ",".join([
            "price", "summaryDetail", "defaultKeyStatistics", "financialData",
            "summaryProfile", "insiderTransactions", "insiderHolders",
            "institutionOwnership", "majorHoldersBreakdown", "netSharePurchaseActivity"
        ])
        params = {"modules": modules, "crumb": self.crumb, "formatted": "false", "lang": "en-US", "region": "US"}
        last_error = None
        for base in self.BASES:
            try:
                data = self._get(f"{base}/v10/finance/quoteSummary/{self.symbol(ticker)}", params)
                result = (data.get("quoteSummary", {}).get("result") or [])
                if result:
                    return result[0]
                last_error = RuntimeError("Yahoo returned no quoteSummary result")
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"Yahoo research failed for {self.symbol(ticker)}: {last_error}")


class RealtimeProvider(YahooProvider):
    pass
