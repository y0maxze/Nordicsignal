"""ISIN syntax/check digit only; never proof of issuer, venue or current validity."""
import re


def valid_isin(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Z]{2}[A-Z0-9]{9}[0-9]', value):
        return False
    digits = ''.join(str(ord(c) - 55) if c.isalpha() else c for c in value)
    weighted = (int(c) * (2 if i % 2 else 1) for i, c in enumerate(reversed(digits)))
    return sum(n // 10 + n % 10 for n in weighted) % 10 == 0


def listing_identity(row):
    """Preserve the source's literal identifier; quarantine malformed values."""
    item = dict(row)
    reported = item.get('reported_isin', item.get('isin'))
    valid = valid_isin(reported)
    item.update(reported_isin=reported, isin=reported if valid else None,
                isin_status='format_valid' if valid else 'invalid' if reported else 'missing')
    return item
