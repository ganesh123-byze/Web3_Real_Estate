"""Property-owner scoped rent metrics and listings for the admin panel."""

from __future__ import annotations

from typing import Any

from backend.api.schemas import RentAnalytics
from backend.services.auth import normalize_address


def _normalized_owner_wallet(owner_wallet: str) -> str:
    return normalize_address(owner_wallet or "")


def fetch_owner_rent_analytics(cursor, owner_wallet: str) -> RentAnalytics:
    """Aggregate rent KPIs for properties created by ``owner_wallet``."""
    wallet = _normalized_owner_wallet(owner_wallet)
    if not wallet:
        return RentAnalytics(
            total_rent_collected_wei="0",
            total_rent_distributed_wei="0",
            total_payments=0,
            total_distributions=0,
            active_rentals=0,
        )

    cursor.execute(
        """
        SELECT COALESCE(SUM(CAST(rp.amount_wei AS DECIMAL(36,0))), 0) AS collected,
               COUNT(*) AS cnt
        FROM rent_payments rp
        JOIN properties p ON p.id = rp.property_id
        WHERE LOWER(p.owner_wallet) = LOWER(%s)
        """,
        (wallet,),
    )
    payments = cursor.fetchone() or {}

    cursor.execute(
        """
        SELECT COALESCE(SUM(CAST(rd.total_distributed AS DECIMAL(36,0))), 0) AS distributed,
               COUNT(*) AS cnt
        FROM rent_distributions rd
        JOIN properties p ON p.id = rd.property_id
        WHERE LOWER(p.owner_wallet) = LOWER(%s)
        """,
        (wallet,),
    )
    dists = cursor.fetchone() or {}

    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM tenant_rentals tr
        JOIN properties p ON p.id = tr.property_id
        WHERE LOWER(p.owner_wallet) = LOWER(%s) AND tr.status = 'active'
        """,
        (wallet,),
    )
    active = cursor.fetchone() or {}

    return RentAnalytics(
        total_rent_collected_wei=str(int(payments.get("collected") or 0)),
        total_rent_distributed_wei=str(int(dists.get("distributed") or 0)),
        total_payments=int(payments.get("cnt") or 0),
        total_distributions=int(dists.get("cnt") or 0),
        active_rentals=int(active.get("cnt") or 0),
    )


def fetch_owner_rent_distributions(cursor, owner_wallet: str) -> list[dict[str, Any]]:
    wallet = _normalized_owner_wallet(owner_wallet)
    if not wallet:
        return []

    cursor.execute(
        """
        SELECT rd.*, p.name AS property_name
        FROM rent_distributions rd
        JOIN properties p ON p.id = rd.property_id
        WHERE LOWER(p.owner_wallet) = LOWER(%s)
        ORDER BY rd.distributed_at DESC
        """,
        (wallet,),
    )
    rows = cursor.fetchall() or []
    for row in rows:
        row["distributed_at"] = (
            row["distributed_at"].isoformat() if row.get("distributed_at") else ""
        )
    return rows


def fetch_owner_rent_payments(cursor, owner_wallet: str) -> list[dict[str, Any]]:
    wallet = _normalized_owner_wallet(owner_wallet)
    if not wallet:
        return []

    cursor.execute(
        """
        SELECT rp.*, p.name AS property_name, t.wallet_address AS tenant_wallet,
               u.full_name AS tenant_full_name,
               COALESCE(NULLIF(u.display_id, ''),
                 CASE WHEN u.role = 'property_owner' THEN 'ADM-'
                      WHEN u.role = 'tenant' THEN 'TEN-'
                      ELSE 'INV-' END || LPAD(u.id::text, 3, '0')) AS tenant_display_id,
               COALESCE(u.profile_role, u.role) AS tenant_profile_role
        FROM rent_payments rp
        JOIN tenants t ON t.id = rp.tenant_id
        JOIN properties p ON p.id = rp.property_id
        LEFT JOIN users u ON LOWER(u.wallet_address) = LOWER(t.wallet_address)
        WHERE LOWER(p.owner_wallet) = LOWER(%s)
        ORDER BY rp.payment_date DESC
        """,
        (wallet,),
    )
    rows = cursor.fetchall() or []
    for row in rows:
        row["payment_date"] = (
            row["payment_date"].isoformat() if row.get("payment_date") else ""
        )
    return rows


def fetch_owner_active_rentals(cursor, owner_wallet: str) -> list[dict[str, Any]]:
    wallet = _normalized_owner_wallet(owner_wallet)
    if not wallet:
        return []

    cursor.execute(
        """
        SELECT tr.*, p.name AS property_name, p.location,
               t.wallet_address AS tenant_wallet
        FROM tenant_rentals tr
        JOIN tenants t ON t.id = tr.tenant_id
        JOIN properties p ON p.id = tr.property_id
        WHERE LOWER(p.owner_wallet) = LOWER(%s)
        ORDER BY tr.created_at DESC
        """,
        (wallet,),
    )
    rows = cursor.fetchall() or []
    for row in rows:
        if row.get("rental_start_date"):
            row["rental_start_date"] = row["rental_start_date"].isoformat()
        if row.get("rental_end_date"):
            row["rental_end_date"] = row["rental_end_date"].isoformat()
        if row.get("created_at"):
            row["created_at"] = row["created_at"].isoformat()
    return rows
