"""Verified document facts for archived IPO candidates.

The collector follows the candidate's official Euronext source page, records official
prospectus/offering-document links when present, and extracts only explicitly stated
terms. Missing fields remain unknown. This module never changes the NordicSignal
stock score or produces an investment recommendation.
"""
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
import json
import re

import extra_api
from database import connect
import news_runtime

VERSION = "ipo_document_facts_v1"
_ALLOWED_HOST_SUFFIXES = ("euronext.com", "oslobors.no")
_DOC_TERMS = ("prospectus", "offering memorandum", "information document", "company presentation")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _candidate(candidate_id):
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM ipo_candidates WHERE candidate_id=?", (str(candidate_id),)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _allowed_url(url):
    try:
        host = (urlparse(str(url or "")).hostname or "").lower()
    except Exception:
        return False
    return any(host == suffix or host.endswith("." + suffix) for suffix in _ALLOWED_HOST_SUFFIXES)


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.links = []
        self._href = None
        self._link_parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self._skip += 1
            return
        if self._skip:
            return
        if tag == "a":
            self._href = attrs.get("href")
            self._link_parts = []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._link_parts).strip()))
            self._href = None
            self._link_parts = []

    def handle_data(self, data):
        if self._skip:
            return
        text = " ".join(str(data or "").split())
        if not text:
            return
        self.parts.append(text)
        if self._href is not None:
            self._link_parts.append(text)

    @property
    def text(self):
        return " ".join(self.parts)


def _num(text):
    value = str(text or "").replace(" ", "").replace("\u00a0", "")
    value = value.replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


def _scaled_nok(number, scale):
    value = _num(number)
    if value is None:
        return None
    scale = str(scale or "").lower()
    if scale in {"bn", "billion", "billionn"}:
        value *= 1_000_000_000
    elif scale in {"m", "mn", "million"}:
        value *= 1_000_000
    return value


def _money_after(label_pattern, text):
    pattern = rf"(?:{label_pattern})[^.;:]{{0,120}}?(?:nok|nkr|kr)\s*([0-9][0-9 .,]*?)(?:\s*(bn|billion|m|mn|million))?(?=\s|[.,;)]|$)"
    match = re.search(pattern, text, re.I)
    return _scaled_nok(match.group(1), match.group(2)) if match else None


def _percent_after(label_pattern, text):
    match = re.search(rf"(?:{label_pattern})[^.;:]{{0,100}}?([0-9]+(?:[.,][0-9]+)?)\s*%", text, re.I)
    return _num(match.group(1)) if match else None


def _shares_after(label_pattern, text):
    match = re.search(rf"(?:{label_pattern})[^.;:]{{0,100}}?([0-9][0-9 ,.]+)\s+(?:new\s+)?shares", text, re.I)
    value = _num(match.group(1)) if match else None
    return int(value) if value is not None else None


def extract_facts(text):
    """Extract explicitly labelled terms only; ambiguous prose stays unknown."""
    text = " ".join(str(text or "").split())
    primary = _money_after(r"gross proceeds|new capital|primary proceeds", text)
    secondary = _money_after(r"secondary (?:sale|offering|proceeds)|sale by existing shareholders", text)
    raise_total = _money_after(r"total (?:offer|offering) size|gross offer size", text)
    founder_retention = _percent_after(r"founders? (?:will )?(?:retain|hold|own)|founder ownership after", text)
    lockup_months = None
    lockup = re.search(r"lock[- ]?up[^.;]{0,100}?([0-9]+)\s*(months?|days?)", text, re.I)
    if lockup:
        amount = int(lockup.group(1))
        lockup_months = round(amount / 30.4375, 1) if lockup.group(2).lower().startswith("day") else float(amount)
    new_shares = _shares_after(r"new shares|primary offering", text)
    existing_shares = _shares_after(r"existing shares|secondary offering", text)

    use_of_proceeds = None
    use_match = re.search(r"(?:use of proceeds|net proceeds (?:will|are expected to) be used (?:to|for))\s*[:\-]?\s*([^.;]{8,240})", text, re.I)
    if use_match:
        use_of_proceeds = use_match.group(1).strip()

    return {
        "new_capital_nok": primary,
        "secondary_sale_nok": secondary,
        "total_offer_size_nok": raise_total,
        "founder_retention_pct": founder_retention,
        "lockup_months": lockup_months,
        "new_shares": new_shares,
        "existing_shares_offered": existing_shares,
        "use_of_proceeds": use_of_proceeds,
    }


def _document_links(base_url, links):
    found = []
    seen = set()
    for href, label in links or []:
        url = urljoin(base_url, str(href or ""))
        label_clean = " ".join(str(label or "").split()).strip()
        haystack = (label_clean + " " + url).lower()
        if not any(term in haystack for term in _DOC_TERMS):
            continue
        if not _allowed_url(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        kind = next((term.replace(" ", "_") for term in _DOC_TERMS if term in haystack), "document")
        found.append({"kind": kind, "label": label_clean or kind.replace("_", " ").title(), "url": url})
    return found


def collect(candidate, fetch_text=None):
    candidate = dict(candidate or {})
    source_url = str(candidate.get("source_url") or "")
    raw = {}
    try:
        raw = json.loads(candidate.get("raw_payload") or "{}") if candidate.get("raw_payload") else {}
    except Exception:
        raw = {}
    seed_text = " ".join([
        str(candidate.get("title") or ""),
        str(raw.get("title") or ""),
        str(raw.get("summary") or ""),
        str(raw.get("topic") or ""),
    ])
    page_status = "not_fetched"
    page_text = ""
    documents = []
    if source_url and _allowed_url(source_url):
        try:
            html = (fetch_text or news_runtime._fetch_text)(source_url)
            parser = _PageParser()
            parser.feed(html)
            page_text = parser.text
            documents = _document_links(source_url, parser.links)
            page_status = "available"
        except Exception:
            page_status = "unavailable"
    facts = extract_facts(" ".join([seed_text, page_text]))
    known = sum(1 for value in facts.values() if value not in (None, ""))
    return {
        "version": VERSION,
        "candidate_id": candidate.get("candidate_id"),
        "company": candidate.get("company"),
        "ticker": candidate.get("ticker"),
        "source_url": source_url or None,
        "source_verified": bool(source_url and _allowed_url(source_url)),
        "page_status": page_status,
        "documents": documents,
        "facts": facts,
        "known_fact_count": known,
        "status": "facts_available" if known or documents else "insufficient",
        "policy": "Verified source facts only. Unknown fields stay unknown; no score change or recommendation.",
        "generated_at": _now(),
    }


def document_facts(candidate_id):
    row = _candidate(candidate_id)
    if not row:
        return {"status": "not_found", "candidate_id": str(candidate_id), "policy": "No score changes."}
    return collect(row)


def install():
    if getattr(extra_api, "_ipo_document_facts_runtime_v1", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)

        @app.get("/api/ipo-radar/documents/{candidate_id}")
        def ipo_document_facts(candidate_id: str):
            return document_facts(candidate_id)

    extra_api.install = patched_install
    extra_api._ipo_document_facts_runtime_v1 = True


install()
