from instrument_detail_runtime import instrument_distributions


class FakeProvider:
    BASE = "https://query1.finance.yahoo.com"
    BASES = (BASE,)

    def __init__(self):
        self.calls = []

    def _get(self, url, params):
        self.calls.append((url, dict(params)))
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


def test_distribution_lookup_uses_bounded_monthly_history():
    provider = FakeProvider()
    result = instrument_distributions(provider, "VOO", years=10)
    assert result["event_count"] == 1
    assert provider.calls
    params = provider.calls[0][1]
    assert params["interval"] == "1mo"
    assert "period1" in params and "period2" in params
    assert params["period2"] > params["period1"]
    assert params.get("range") != "max"
