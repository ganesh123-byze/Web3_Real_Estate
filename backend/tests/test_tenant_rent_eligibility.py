"""Exclusive tenant rent eligibility (one payer per property)."""
from __future__ import annotations

from datetime import datetime, timedelta

from backend.services.tenant_rent_eligibility import (
    build_tenant_property_rent_fields,
    tenant_may_pay_rent,
    tenant_property_is_visible,
)


class _FakeCursor:
    def __init__(self, property_payment=None, active_holder=None, wallet_payment=None):
        self._property_payment = property_payment
        self._active_holder = active_holder
        self._wallet_payment = wallet_payment
        self._last_sql = ""

    def execute(self, sql, params=None):
        self._last_sql = " ".join(sql.split())
        self._params = params

    def fetchone(self):
        if "property_id = %s AND payment_status" in self._last_sql:
            return self._property_payment
        if "tr.property_id = %s AND tr.status = 'active'" in self._last_sql:
            return self._active_holder
        if "LOWER(t.wallet_address)" in self._last_sql:
            return self._wallet_payment
        return None


def test_other_tenant_cannot_pay_when_property_cycle_paid():
    paid_at = datetime.utcnow() - timedelta(days=3)
    cursor = _FakeCursor(
        property_payment={"payment_date": paid_at, "tenant_id": 1},
        active_holder=None,
        wallet_payment=None,
    )
    fields = build_tenant_property_rent_fields(cursor, 7, tenant_wallet="0xTenantB")
    assert fields["current_cycle_paid"] is True
    assert tenant_may_pay_rent(fields) is False
    assert tenant_property_is_visible(fields, active_rental=False) is False


def test_other_tenant_blocked_when_active_rental_holder_differs():
    cursor = _FakeCursor(
        property_payment=None,
        active_holder={"tenant_id": 1, "wallet_address": "0xTenantA"},
        wallet_payment=None,
    )
    fields = build_tenant_property_rent_fields(cursor, 7, tenant_wallet="0xTenantB")
    assert fields["rent_claimed_by_other_tenant"] is True
    assert tenant_may_pay_rent(fields) is False


def test_assigned_tenant_can_pay_when_cycle_open():
    cursor = _FakeCursor(
        property_payment=None,
        active_holder={"tenant_id": 1, "wallet_address": "0xTenantA"},
        wallet_payment=None,
    )
    fields = build_tenant_property_rent_fields(cursor, 7, tenant_wallet="0xTenantA")
    assert fields["rent_claimed_by_other_tenant"] is False
    assert tenant_may_pay_rent(fields) is True
    assert tenant_property_is_visible(fields, active_rental=True) is True
