"""Tenant rental catalog — same source of truth as GET /tenant/properties."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from backend.api._helpers import enrich_property_with_supply
from backend.services.tenant_rent_eligibility import (
    build_tenant_property_rent_fields,
    tenant_property_is_visible,
)


def tenant_active_rental_property_ids(cursor, tenant_wallet: str) -> set[int]:
    """Property ids where the wallet has an active row in tenant_rentals."""
    wallet = (tenant_wallet or "").strip()
    if not wallet:
        return set()
    cursor.execute(
        """
        SELECT tr.property_id
        FROM tenant_rentals tr
        JOIN tenants t ON t.id = tr.tenant_id
        WHERE LOWER(t.wallet_address) = LOWER(%s) AND tr.status = 'active'
        """,
        (wallet,),
    )
    return {int(row["property_id"]) for row in (cursor.fetchall() or [])}


def fetch_tenant_rental_properties(
    cursor,
    *,
    tenant_wallet: str | None = None,
) -> list[dict[str, Any]]:
    """Properties on the tenant dashboard: active listings with token holders."""
    cursor.execute(
        """
        SELECT * FROM properties p
        WHERE COALESCE(p.is_active, TRUE) = TRUE
        AND EXISTS (
            SELECT 1 FROM token_ownerships t
            WHERE t.property_id = p.id AND t.token_amount > 0
        )
        ORDER BY p.id DESC
        """
    )
    rows = cursor.fetchall() or []
    active_rental_ids = (
        tenant_active_rental_property_ids(cursor, tenant_wallet)
        if tenant_wallet
        else set()
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        enriched = enrich_property_with_supply(cursor, row)
        rent_wei = enriched.get("monthly_rent_wei") or "0"
        enriched["rent_enabled"] = rent_wei not in (None, "", "0")
        property_id = int(enriched["id"])
        active_rental = property_id in active_rental_ids
        rent_fields = build_tenant_property_rent_fields(
            cursor, property_id, tenant_wallet=tenant_wallet
        )
        enriched.update(rent_fields)
        enriched["has_investors"] = Decimal(enriched.get("tokens_sold") or 0) > 0
        enriched["active_rental"] = active_rental
        if tenant_wallet and not tenant_property_is_visible(rent_fields, active_rental=active_rental):
            continue
        result.append(enriched)
    return result


def filter_tenant_dashboard_available(properties: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Match the tenant Rentals page \"Available\" section."""
    out: list[dict[str, Any]] = []
    for prop in properties:
        if not prop.get("has_investors"):
            continue
        if prop.get("active_rental"):
            continue
        if not prop.get("can_pay_rent"):
            continue
        if not prop.get("rent_enabled"):
            continue
        out.append(prop)
    return out
