from abc import ABC, abstractmethod

class MarketDataProvider(ABC):
    @abstractmethod
    def quote(self, ticker: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def historical(self, ticker: str, period: str = "1y") -> list[dict]:
        raise NotImplementedError

class DemoProvider(MarketDataProvider):
    def quote(self, ticker):
        return {"ticker": ticker, "price": None, "change_pct": None, "source": "demo"}

    def historical(self, ticker, period="1y"):
        return []

class RealtimeProvider(MarketDataProvider):
    """Adapter slot for a licensed real-time market-data provider.

    Implement quote() and historical() here after credentials/licensing are selected.
    Keep provider-specific code isolated from the scoring engine.
    """
    def quote(self, ticker):
        raise NotImplementedError("Connect licensed real-time provider")

    def historical(self, ticker, period="1y"):
        raise NotImplementedError("Connect licensed historical provider")
