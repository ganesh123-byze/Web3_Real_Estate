"""Who may pay rent for a property — one paying tenant per property per cycle."""
from __future__ import annotations

from typing import Any

from backend.api.rent_cycle import (
    property_rent_period_status,
    serialize_period_fields,
    tenant_rent_period_status,
)


def get_property_active_rental_holder(cursor, property_id: int) -> dict[str, Any] | None:
    """The active tenant_rentals row for this property, if any."""
    cursor.execute(
        """
        SELECT tr.tenant_id, t.wallet_address
        FROM tenant_rentals tr
        JOIN tenants t ON t.id = tr.tenant_id
        WHERE tr.property_id = %s AND tr.status = 'active'
        ORDER BY tr.created_at DESC
        LIMIT 1
        """,
        (property_id,),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def _wallet_matches(a: str | None, b: str | None) -> bool:
    left = (a or "").strip().lower()
    right = (b or "").strip().lower()
    return bool(left) and left == right


def build_tenant_property_rent_fields(
    cursor,
    property_id: int,
    *,
    tenant_wallet: str | None = None,
) -> dict[str, Any]:
    """Rent cycle + exclusive tenant flags for tenant catalog and pay-rent APIs."""
    period = property_rent_period_status(cursor, property_id)
    fields = serialize_period_fields(period)

    tenant_paid_current_cycle = False
    if tenant_wallet:
        tenant_period = tenant_rent_period_status(cursor, tenant_wallet, property_id)
        tenant_paid_current_cycle = bool(tenant_period.get("current_cycle_paid"))

    can_pay = bool(fields.get("can_pay_rent"))
    claimed_by_other = False

    holder = get_property_active_rental_holder(cursor, property_id)
    if holder and tenant_wallet and not _wallet_matches(holder.get("wallet_address"), tenant_wallet):
        claimed_by_other = True
        can_pay = False

    if fields.get("current_cycle_paid"):
        can_pay = False

    fields["can_pay_rent"] = can_pay
    fields["rent_claimed_by_other_tenant"] = claimed_by_other
    fields["tenant_paid_current_cycle"] = tenant_paid_current_cycle
    return fields


def tenant_may_pay_rent(fields: dict[str, Any]) -> bool:
    return bool(fields.get("can_pay_rent"))


def tenant_property_is_visible(fields: dict[str, Any], *, active_rental: bool) -> bool:
    """Tenant sees the property if they rent it or may still pay rent."""
    if active_rental:
        return True
    if fields.get("tenant_paid_current_cycle"):
        return True
    return tenant_may_pay_rent(fields)


def pay_rent_blocked_message(fields: dict[str, Any], *, property_name: str = "this property") -> str:
    if fields.get("rent_claimed_by_other_tenant"):
        return (
            f"{property_name} already has an active tenant. "
            "Only that tenant can pay rent for this property."
        )
    if fields.get("current_cycle_paid"):
        label = fields.get("rent_cycle_label") or "this billing period"
        next_due = fields.get("next_rent_due_at")
        if next_due:
            return (
                f"Rent for {property_name} is already paid for {label}. "
                f"Next due {next_due}."
            )
        return f"Rent for {property_name} is already paid for the current period."
    return f"Rent payment is not available for {property_name}."
