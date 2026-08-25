import unittest

import instrument_search_runtime as search_runtime


class FakeProvider:
    BASES = ("https://one.invalid", "https://two.invalid")
    BASE = BASES[0]

    def __init__(self):
        self.calls = []

    def _get(self, url, params=None, need_crumb=False):
        self.calls.append((url, dict(params or {})))
        if "one.invalid" in url:
            raise RuntimeError("temporary host failure")
        return {
            "quotes": [
                {"symbol": "AAPL", "quoteType": "EQUITY", "longname": "Apple Inc.", "exchange": "NMS", "currency": "USD"},
                {"symbol": "VFIAX", "quoteType": "MUTUALFUND", "longname": "Vanguard 500 Index Fund", "exchange": "NAS", "currency": "USD"},
                {"symbol": "VOO", "quoteType": "ETF", "longname": "Vanguard S&P 500 ETF", "exchange": "PCX", "currency": "USD"},
                {"symbol": "BTC-USD", "quoteType": "CRYPTOCURRENCY", "shortname": "Bitcoin USD"},
            ]
        }


class InstrumentSearchRuntimeTests(unittest.TestCase):
    def test_retries_second_yahoo_host_and_keeps_supported_instruments(self):
        provider = FakeProvider()
        rows = search_runtime.resilient_search_instruments(provider, "vanguard", 12)
        self.assertEqual([x["asset_class"] for x in rows], ["Aksjer", "Fond", "ETF"])
        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(provider.calls[1][1]["region"], "NO")

    def test_empty_query_does_not_hit_provider(self):
        provider = FakeProvider()
        self.assertEqual(search_runtime.resilient_search_instruments(provider, "  "), [])
        self.assertEqual(provider.calls, [])


if __name__ == "__main__":
    unittest.main()
