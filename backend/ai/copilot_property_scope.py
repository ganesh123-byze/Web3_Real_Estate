"""Copilot (chatbot) queries — only active listings, never archived (is_active=false)."""
from __future__ import annotations

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


def fetch_active_property(cursor, property_id: int) -> dict | None:
    cursor.execute(
        f"SELECT * FROM properties WHERE id = %s AND {ACTIVE_PROPERTY_SQL}",
        (int(property_id),),
    )
    return cursor.fetchone()


def property_unavailable_message(property_id: int | str) -> str:
    return (
        f"Property {property_id} is not available — it may have been archived or removed. "
        "Only active listings are shown in chat."
    )
