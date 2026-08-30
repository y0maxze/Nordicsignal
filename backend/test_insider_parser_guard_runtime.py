import insider_parser_guard_runtime  # noqa: F401
from insider_runtime import parse_trade


def test_price_parser_stops_before_adjacent_share_count():
    body = (
        "CEO Example purchased 37 500 shares at a price of NOK 26.65 "
        "and after the transaction holds 660 000 shares on 2026-08-19."
    )
    row = parse_trade(body, "XPLRA", "Primary insider transaction", "Euronext", "https://example.test")
    assert row["shares"] == 37500
    assert row["price"] == 26.65
    assert round(row["transaction_value"], 2) == 999375.00


def test_price_parser_supports_decimal_comma():
    body = "CFO Example kjøpte 8 000 aksjer til kurs NOK 26,91 den 19.08.2026."
    row = parse_trade(body, "XPLRA", "Primærinnsidetransaksjon", "Euronext", "https://example.test")
    assert row["shares"] == 8000
    assert row["price"] == 26.91
    assert round(row["transaction_value"], 2) == 215280.00


def test_price_parser_supports_grouped_high_price_without_partial_match():
    body = "CEO Example purchased 10 shares at a price of NOK 1 234,50 per share on 2026-08-19."
    row = parse_trade(body, "TEST", "Primary insider transaction", "Euronext", "https://example.test")
    assert row["price"] == 1234.5
