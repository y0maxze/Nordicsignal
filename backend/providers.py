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
        return {"ticker": ticker, "price": None, "change_pct": None, "volume": None, "source": "demo"}

    def historical(self, ticker, period="1y"):
        return []

class RealtimeProvider(MarketDataProvider):
    """
    Provider adapter for the future licensed market-data connection.
    Keeping this isolated means the scoring/database layer does not need
    to change when a real provider is selected.
    """
    def quote(self, ticker):
        raise NotImplementedError("Connect the selected licensed real-time provider.")

    def historical(self, ticker, period="1y"):
        raise NotImplementedError("Connect the selected historical-data provider.")
