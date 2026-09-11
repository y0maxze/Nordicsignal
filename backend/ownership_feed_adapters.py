"""Server-side adapter contract for authoritative shareholder snapshots.

This module deliberately does not fetch, scrape, or authenticate to any provider.
It normalizes rows from an already-authorized source into the canonical
``ownership_snapshot_runtime.ingest_snapshot`` contract.

Why the explicit contract matters:
- field names are never guessed from a provider we have not received a sample for;
- media/news rows cannot be ingested as ownership snapshots;
- snapshot scopes are isolated so top-20 and top-200 lists are never compared as
  if they were the same population;
- a provider remains ``connection_ready=False`` until credentials/licensing and a
  real file contract have been verified outside this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Iterable, Mapping, Any

import ownership_snapshot_runtime as ownership_runtime


OFFICIAL_AUTHORITIES = {"official_register", "official_annual_register"}
REQUIRED_CANONICAL_FIELDS = {"holder_name"}
OPTIONAL_CANONICAL_FIELDS = {
    "ticker",
    "as_of_date",
    "holder_id",
    "holder_type",
    "country",
    "shares",
    "ownership_pct",
    "rank",
}


@dataclass(frozen=True)
class OwnershipFeedSpec:
    provider_key: str
    product_name: str
    authority: str
    frequency: str
    delivery: str
    machine_ingest: bool
    connection_ready: bool = False
    coverage_note: str = ""
    source_url: str | None = None


@dataclass(frozen=True)
class SnapshotBatch:
    provider: str
    ticker: str
    as_of_date: str
    holders: tuple[dict[str, Any], ...]
    source_ref: str | None


# Product capability descriptors. ``connection_ready`` stays false until the
# corresponding licensed/authorized delivery is actually configured in runtime.
EURONEXT_TOP_SHAREHOLDER_INFORMATION = OwnershipFeedSpec(
    provider_key="euronext_securities_top_shareholder_information",
    product_name="Euronext Securities Oslo — Top Shareholder Information",
    authority="official_register",
    frequency="daily_previous_banking_day",
    delivery="licensed_sftp_structured",
    machine_ingest=True,
    connection_ready=False,
    coverage_note="Ranked top-holder snapshot; use a stable scope_id/depth for comparisons.",
    source_url="https://www.euronext.com/en/products-services/top-shareholder-information",
)

EURONEXT_ORGANISATIONAL_SHAREHOLDERS = OwnershipFeedSpec(
    provider_key="euronext_securities_organisational_shareholders",
    product_name="Euronext Securities Oslo — Organisational Shareholders",
    authority="official_register",
    frequency="daily_previous_banking_day",
    delivery="licensed_sftp_csv",
    machine_ingest=True,
    connection_ready=False,
    coverage_note="Full-depth organisational owners; private individuals are filtered by the product.",
    source_url="https://www.euronext.com/en/products-services/organisational-shareholders",
)

SKATTEETATEN_AKSJONAERREGISTERET = OwnershipFeedSpec(
    provider_key="skatteetaten_aksjonaerregisteret",
    product_name="Skatteetaten — Aksjonærregisteret",
    authority="official_annual_register",
    frequency="annual",
    delivery="public_annual_extract",
    machine_ingest=True,
    connection_ready=False,
    coverage_note="Annual historical baseline only; never present as daily/current positioning.",
    source_url="https://www.skatteetaten.no/deling/aksjonarregisteret/",
)

# The free portal is useful for human verification, but we do not claim a
# documented machine API or use it as a market-wide automated feed.
EURONEXT_PUBLIC_SHAREHOLDER_PORTAL = OwnershipFeedSpec(
    provider_key="euronext_public_shareholder_portal",
    product_name="Euronext Securities Oslo — Public Shareholder Portal",
    authority="official_register",
    frequency="latest_available_interactive",
    delivery="interactive_portal",
    machine_ingest=False,
    connection_ready=False,
    coverage_note="Human lookup/verification only in NordicSignal until a documented machine interface is authorized.",
    source_url="https://www.euronext.com/en/csd/oslo/data-services/public-shareholder-portal",
)


PROVIDER_CATALOG = {
    spec.provider_key: spec
    for spec in (
        EURONEXT_TOP_SHAREHOLDER_INFORMATION,
        EURONEXT_ORGANISATIONAL_SHAREHOLDERS,
        SKATTEETATEN_AKSJONAERREGISTERET,
        EURONEXT_PUBLIC_SHAREHOLDER_PORTAL,
    )
}


def adapter_status():
    """Return capability truth without implying that a feed is connected."""
    return {
        key: {
            "product_name": spec.product_name,
            "authority": spec.authority,
            "frequency": spec.frequency,
            "delivery": spec.delivery,
            "machine_ingest": spec.machine_ingest,
            "connection_ready": spec.connection_ready,
            "coverage_note": spec.coverage_note,
            "source_url": spec.source_url,
        }
        for key, spec in PROVIDER_CATALOG.items()
    }


def _clean_ticker(value: Any) -> str:
    ticker = str(value or "").strip().upper().replace(".OL", "")
    if not ticker:
        raise ValueError("ownership feed row is missing canonical ticker")
    return ticker


def _clean_date(value: Any) -> str:
    try:
        return date.fromisoformat(str(value or "").strip()[:10]).isoformat()
    except (TypeError, ValueError):
        raise ValueError(f"invalid ownership feed as_of_date: {value!r}") from None


def _number(value: Any, *, decimal_comma: bool = False) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip().replace("\u00a0", "").replace(" ", "")
    if raw.endswith("%"):
        raw = raw[:-1]
    if decimal_comma:
        if "." in raw and "," in raw:
            raw = raw.replace(".", "").replace(",", ".")
        elif "," in raw:
            raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"invalid numeric ownership feed value: {value!r}") from None


def _integer(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        raise ValueError(f"invalid ownership feed rank: {value!r}") from None


def _validate_field_map(field_map: Mapping[str, str], *, ticker_resolver, default_as_of_date):
    unknown = set(field_map) - REQUIRED_CANONICAL_FIELDS - OPTIONAL_CANONICAL_FIELDS
    if unknown:
        raise ValueError(f"unknown canonical ownership field(s): {', '.join(sorted(unknown))}")
    missing = REQUIRED_CANONICAL_FIELDS - set(field_map)
    if missing:
        raise ValueError(f"missing required ownership field mapping(s): {', '.join(sorted(missing))}")
    if "ticker" not in field_map and ticker_resolver is None:
        raise ValueError("field_map['ticker'] or ticker_resolver is required")
    if "as_of_date" not in field_map and not default_as_of_date:
        raise ValueError("field_map['as_of_date'] or default_as_of_date is required")
    for canonical, provider_field in field_map.items():
        if not str(provider_field or "").strip():
            raise ValueError(f"empty provider field mapping for {canonical}")


def prepare_snapshot_batches(
    spec: OwnershipFeedSpec,
    rows: Iterable[Mapping[str, Any]],
    field_map: Mapping[str, str],
    *,
    scope_id: str,
    source_ref: str | None = None,
    default_as_of_date: str | None = None,
    ticker_resolver: Callable[[Mapping[str, Any]], str] | None = None,
    decimal_comma: bool = False,
) -> list[SnapshotBatch]:
    """Normalize authorized provider rows into deterministic snapshot batches.

    ``field_map`` maps canonical names to provider column names. It must be built
    from the real provider contract/sample; this function intentionally has no
    guessed aliases. ``scope_id`` must remain stable across comparable snapshots
    (for example ``top20`` vs ``top200``) so different depths cannot generate
    false entry/exit deltas.
    """
    if spec.authority not in OFFICIAL_AUTHORITIES:
        raise ValueError("ownership snapshots require an official register authority")
    scope_id = str(scope_id or "").strip().lower()
    if not scope_id:
        raise ValueError("stable ownership snapshot scope_id is required")
    _validate_field_map(field_map, ticker_resolver=ticker_resolver, default_as_of_date=default_as_of_date)
    default_date = _clean_date(default_as_of_date) if default_as_of_date else None

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise ValueError("ownership feed rows must be mapping objects")
        ticker_value = ticker_resolver(raw) if ticker_resolver else raw.get(field_map["ticker"])
        ticker = _clean_ticker(ticker_value)
        as_of = default_date or _clean_date(raw.get(field_map["as_of_date"]))
        name = str(raw.get(field_map["holder_name"]) or "").strip()
        if not name:
            raise ValueError(f"ownership feed row for {ticker} {as_of} is missing holder_name")

        def field(key: str):
            provider_key = field_map.get(key)
            return raw.get(provider_key) if provider_key else None

        holder = {
            "holder_id": str(field("holder_id") or "").strip() or None,
            "name": name,
            "holder_type": str(field("holder_type") or "").strip() or None,
            "country": str(field("country") or "").strip() or None,
            "shares": _number(field("shares"), decimal_comma=decimal_comma),
            "ownership_pct": _number(field("ownership_pct"), decimal_comma=decimal_comma),
            "rank": _integer(field("rank")),
        }
        grouped.setdefault((ticker, as_of), []).append(holder)

    provider_instance = f"{spec.provider_key}:{scope_id}"
    return [
        SnapshotBatch(
            provider=provider_instance,
            ticker=ticker,
            as_of_date=as_of,
            holders=tuple(holders),
            source_ref=source_ref,
        )
        for (ticker, as_of), holders in sorted(grouped.items())
    ]


def ingest_snapshot_batches(
    spec: OwnershipFeedSpec,
    batches: Iterable[SnapshotBatch],
    *,
    connection_ready: bool | None = None,
):
    """Persist prepared batches only after an authorized connection is enabled."""
    ready = spec.connection_ready if connection_ready is None else bool(connection_ready)
    if not spec.machine_ingest:
        raise PermissionError(f"{spec.product_name} is not approved for automated ingestion")
    if spec.authority not in OFFICIAL_AUTHORITIES:
        raise PermissionError("only official register sources may create ownership snapshots")
    if not ready:
        raise PermissionError(f"{spec.product_name} is adapter-ready but no authorized feed connection is configured")

    results = []
    for batch in batches:
        if not batch.provider.startswith(spec.provider_key + ":"):
            raise ValueError("snapshot batch provider does not match adapter spec")
        result = ownership_runtime.ingest_snapshot(
            batch.provider,
            batch.ticker,
            batch.as_of_date,
            list(batch.holders),
            source_ref=batch.source_ref,
        )
        results.append({
            "provider": batch.provider,
            "ticker": batch.ticker,
            "as_of_date": batch.as_of_date,
            **result,
        })
    return results
