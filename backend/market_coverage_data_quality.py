"""Data-quality helpers for observed market coverage gaps."""


def insider_detail_quality(item):
    item = item or {}
    shares = item.get("shares")
    price = item.get("price")
    value = item.get("transaction_value")
    if shares is None:
        return "partial_missing_volume"
    if price is None and value is None:
        return "partial_missing_price_value"
    return "complete"
