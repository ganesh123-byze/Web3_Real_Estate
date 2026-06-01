"""Copilot (chatbot) queries — same visibility as dashboard UI (active + fully created)."""
from __future__ import annotations

from typing import Any

from backend.api._helpers import enrich_property_with_supply, property_is_dashboard_listable

# Archived properties are stored with is_active=FALSE (see delete_property archive path).
ACTIVE_PROPERTY_SQL = "COALESCE(is_active, TRUE) = TRUE"


def active_property_join(on: str, alias: str = "p") -> str:
    """INNER JOIN properties alias with active-only filter. ``on`` e.g. ``p.id = o.property_id``."""
    return f"JOIN properties {alias} ON {on} AND COALESCE({alias}.is_active, TRUE) = TRUE"


def active_property_left_join(on: str, alias: str = "p") -> str:
    """LEFT JOIN properties alias; archived rows do not match."""
    return f"LEFT JOIN properties {alias} ON {on} AND COALESCE({alias}.is_active, TRUE) = TRUE"


def transaction_excludes_archived_property(alias: str = "p", tx_alias: str = "t") -> str:
    """Use after joining transactions to properties (LEFT JOIN active only)."""
    return f"AND ({tx_alias}.property_id IS NULL OR {alias}.id IS NOT NULL)"


def filter_dashboard_listable_properties(cursor, rows: list[dict]) -> list[dict]:
    """Match admin/investor UI: active, token deployed, sale inventory finalized."""
    listable: list[dict] = []
    for row in rows or []:
        enriched = enrich_property_with_supply(cursor, row)
        if property_is_dashboard_listable(enriched):
            listable.append(enriched)
    return listable


def count_dashboard_listable_active(cursor) -> int:
    cursor.execute(
        f"SELECT * FROM properties WHERE {ACTIVE_PROPERTY_SQL} ORDER BY id DESC"
    )
    return len(filter_dashboard_listable_properties(cursor, cursor.fetchall() or []))


def fetch_active_property(cursor, property_id: int) -> dict | None:
    cursor.execute(
        f"SELECT * FROM properties WHERE id = %s AND {ACTIVE_PROPERTY_SQL}",
        (int(property_id),),
    )
    row = cursor.fetchone()
    if not row:
        return None
    enriched = enrich_property_with_supply(cursor, row)
    if not property_is_dashboard_listable(enriched):
        return None
    return enriched


def property_unavailable_message(property_id: int | str) -> str:
    return (
        f"Property {property_id} is not available in chat — it may be archived, still "
        "being created, or not shown on the dashboard yet. Ask again after the listing "
        "appears on your Properties page, or pick a property from the current list."
    )


def copilot_property_list_meta(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Structured fields the model should use for counts and names (not memory)."""
    return {
        "count": len(items),
        "property_names": [p.get("name") for p in items if p.get("name")],
        "dashboard_visible_only": True,
    }
