from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json
import time


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
    BASE = "https://query1.finance.yahoo.com"
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"

    def __init__(self):
        self.cookie = None
        self.crumb = None
        self._bootstrap_at = 0

    def symbol(self, ticker: str) -> str:
        ticker = ticker.upper()
        return ticker if "." in ticker else ticker + ".OL"

    def _get(self, url, params=None, headers=None):
        if params:
            url += ("&" if "?" in url else "?") + urlencode(params)
        req = Request(url, headers={"User-Agent": self.UA, **(headers or {})})
        with urlopen(req, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))

    def _bootstrap(self):
        if self.crumb and time.time() - self._bootstrap_at < 1800:
            return
        req = Request("https://fc.yahoo.com", headers={"User-Agent": self.UA})
        try:
            with urlopen(req, timeout=10) as response:
                raw = response.headers.get("Set-Cookie", "")
        except Exception:
            raw = ""
        self.cookie = raw.split(";", 1)[0] if raw else None
        headers = {"Cookie": self.cookie} if self.cookie else {}
        req = Request(self.BASE + "/v1/test/getcrumb", headers={"User-Agent": self.UA, **headers})
        with urlopen(req, timeout=10) as response:
            self.crumb = response.read().decode("utf-8").strip()
        self._bootstrap_at = time.time()

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
        # UI periods are intentionally explicit. Yahoo's range/interval pair
        # controls the amount of data and therefore the chart resolution.
        ranges = {
            "now": ("1d", "5m"),
            "1d": ("1d", "5m"),
            "1w": ("5d", "1h"),
            "1m": ("1mo", "1d"),
            "3m": ("3mo", "1d"),
            "6m": ("6mo", "1d"),
            "1y": ("1y", "1d"),
            "5y": ("5y", "1wk"),
            "10y": ("10y", "1mo"),
            "max": ("max", "1mo"),
        }
        rng, interval = ranges.get(period, ranges["1y"])
        data = self._get(
            f"{self.BASE}/v8/finance/chart/{self.symbol(ticker)}",
            {"range": rng, "interval": interval, "events": "div,splits"},
        )
        result = data["chart"]["result"][0]
        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators", {}).get("quote") or [{}])[0]
        rows = []
        closes = quote.get("close") or []
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        volumes = quote.get("volume") or []
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
        params = {"modules": modules, "crumb": self.crumb, "formatted": "false"}
        headers = {"Cookie": self.cookie} if self.cookie else {}
        data = self._get(f"{self.BASE}/v10/finance/quoteSummary/{self.symbol(ticker)}", params, headers)
        return (data.get("quoteSummary", {}).get("result") or [{}])[0]


class RealtimeProvider(YahooProvider):
    pass
