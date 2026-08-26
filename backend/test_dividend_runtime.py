from dividend_runtime import _extract_events, fetch_dividend_events


def test_extract_timestamp_keyed_dividends():
    data = {
        "chart": {
            "result": [{
                "events": {
                    "dividends": {
                        "1717027200": {"amount": 2.5, "date": 1717027200}
                    }
                }
            }]
        }
    }
    rows = _extract_events(data)
    assert rows[0]["amount"] == 2.5
    assert rows[0]["timestamp"] == 1717027200


def test_extract_list_dividends():
    data = {
        "chart": {
            "result": [{
                "events": {
                    "dividends": [{"amount": 1.25, "date": 1717027200}]
                }
            }]
        }
    }
    assert _extract_events(data)[0]["amount"] == 1.25


class FakeProvider:
    BASE = "https://query1.finance.yahoo.com"
    BASES = ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com")

    def symbol(self, ticker):
        return ticker + ".OL"

    def __init__(self):
        self.calls = []

    def _get(self, url, params):
        self.calls.append((url, params))
        if len(self.calls) == 1:
            return {"chart": {"result": [{"events": {"dividends": {}}}]}}
        return {
            "chart": {
                "result": [{
                    "events": {
                        "dividends": {
                            "1717027200": {"amount": 2.5, "date": 1717027200}
                        }
                    }
                }]
            }
        }


def test_fetch_falls_back_when_first_event_response_is_empty():
    provider = FakeProvider()
    rows = fetch_dividend_events(provider, "LSG", 1716768000, 1719705600)
    assert rows
    assert rows[0]["amount"] == 2.5
    assert len(provider.calls) >= 2


class MaxFallbackProvider(FakeProvider):
    def _get(self, url, params):
        self.calls.append((url, params))
        if params.get("range") == "max":
            return {
                "chart": {
                    "result": [{
                        "events": {
                            "dividends": {
                                "1717027200": {"amount": 2.5, "date": 1717027200}
                            }
                        }
                    }]
                }
            }
        return {"chart": {"result": [{"events": {"dividends": {}}}]}}


def test_max_range_fallback_uses_monthly_bars_not_daily_history():
    provider = MaxFallbackProvider()
    rows = fetch_dividend_events(provider, "LSG", 1716768000, 1719705600)
    assert rows
    max_calls = [params for _, params in provider.calls if params.get("range") == "max"]
    assert max_calls
    assert all(params["interval"] == "1mo" for params in max_calls)
