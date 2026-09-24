"""Normalize issuer identity in the market-wide insider feed.

Euronext's company column can contain an issuer followed by related bond/security
names. That text is useful on the exchange page but is noisy as an issuer label in
NordicSignal and can prevent tracked issuers from resolving to their stock ticker.
This runtime keeps the authoritative release itself untouched while normalizing the
issuer label used by the market feed and UI.
"""

import re

import general_news_runtime
import insider_market_v2_runtime
import insider_runtime


_TITLE_COMPANY = re.compile(
    r"^(?:Correction:\s*)?(?P<company>.{2,100}?(?:ASA|AS|AB|A/S|PLC|Ltd\.?|Limited))\s*:\s*",
    re.I,
)


def _collapse(value):
    return " ".join(str(value or "").split()).strip(" ,.-–—")


def canonical_issuer(company=None, title=None, ticker=None):
    """Return (ticker, display_company) without security-list noise."""
    title_text = _collapse(title)
    company_text = _collapse(company)

    title_match = _TITLE_COMPANY.match(title_text)
    if title_match:
        candidate = _collapse(title_match.group("company"))
    else:
        # Current Euronext rows may contain the issuer followed by several related
        # bonds/instruments separated by commas. The first token is the issuer.
        candidate = _collapse(company_text.split(",", 1)[0]) if company_text else ""

    # A common name fragment is not issuer evidence (e.g. Kongsberg Maritime
    # must not resolve to Kongsberg Gruppen). Ignore a prior fuzzy ticker when
    # a source company name is available; retain only a unique exact alias.
    def identity(value):
        value = insider_market_v2_runtime._norm(value)
        return re.sub(r"\s+(?:asa|as|ab|plc|ltd|limited)$", "", value).strip()

    resolved_ticker = str(ticker or "").upper().replace(".OL", "").strip() or None
    if candidate:
        target = identity(candidate)
        matches = {symbol for symbol, (name, aliases) in insider_runtime.ISSUERS.items()
                   if target and any(identity(alias) == target for alias in (name, *aliases))}
        resolved_ticker = next(iter(matches)) if len(matches) == 1 else None

    if resolved_ticker in insider_runtime.ISSUERS:
        candidate = insider_runtime.ISSUERS[resolved_ticker][0]

    return resolved_ticker, candidate or company_text or title_text[:90] or "Oslo Børs-selskap"


def install():
    if getattr(general_news_runtime, "_insider_company_cleanup_runtime", False):
        return

    original_parse = general_news_runtime.parse_general_euronext_html

    def cleaned_parse_general_euronext_html(html, limit=30):
        items = original_parse(html, limit)
        cleaned = []
        for raw in items:
            item = dict(raw)
            ticker, company = canonical_issuer(
                item.get("company"),
                item.get("title"),
                item.get("ticker"),
            )
            item["company"] = company
            item["ticker"] = ticker
            cleaned.append(item)
        return cleaned

    general_news_runtime.parse_general_euronext_html = cleaned_parse_general_euronext_html
    general_news_runtime._insider_company_cleanup_runtime = True


install()
