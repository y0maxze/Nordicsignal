"""Final data-quality normalization for official Euronext insider details.

Euronext detail prose can cause the generic parser to capture the issuer sentence
as part of an associated entity name. This layer does not fetch data or register a
route; it only normalizes rows returned by insider_market_v2_runtime.
"""

import insider_market_v2_runtime as market
import insider_runtime


def _normalize_row(row):
    row = dict(row or {})
    segment = row.get("summary") or row.get("title") or ""
    entity, related_person, role = market._associated_actor(segment)
    if entity:
        entity = insider_runtime._clean_entity_candidate(entity)
        row["entity"] = entity
        row["insider"] = entity
        row["actor_type"] = "company"
        row["person"] = None
        row["related_primary_insider"] = related_person
        row["role"] = row.get("role") or role
    elif row.get("entity"):
        clean = insider_runtime._clean_entity_candidate(row.get("entity"))
        row["entity"] = clean
        if not row.get("person"):
            row["insider"] = clean
    return row


def install():
    if getattr(market, "_detail_normalization_installed", False):
        return
    original = market._euronext_ajax_rows

    def normalized_ajax_rows(announcement, allow_network=True):
        rows, used_network = original(announcement, allow_network=allow_network)
        normalized = [_normalize_row(row) for row in (rows or [])]
        node_id = str((announcement or {}).get("node_id") or "").strip()
        if node_id and normalized:
            market._detail_cache_put(node_id, normalized)
        return normalized, used_network

    market._euronext_ajax_rows = normalized_ajax_rows
    market._detail_normalization_installed = True


install()
