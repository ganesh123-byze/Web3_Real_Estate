"""Rent cycle is property-scoped: one payment covers all tenants for that cycle."""
from __future__ import annotations

from datetime import datetime, timedelta

from backend.api.rent_cycle import (
    compute_rent_period_status,
    property_rent_period_status,
    tenant_rent_period_status,
)


class _FakeCursor:
    def __init__(self, rows_by_query: dict[str, list[dict]]):
        self._rows_by_query = rows_by_query
        self._last_sql = ""

    def execute(self, sql, params=None):
        self._last_sql = " ".join(sql.split())
        self._params = params

    def fetchone(self):
        if "property_id = %s AND payment_status" in self._last_sql:
            property_id = self._params[0]
            rows = self._rows_by_query.get(f"property:{property_id}", [])
            return rows[0] if rows else None
        if "LOWER(t.wallet_address)" in self._last_sql:
            wallet, property_id = self._params
            key = f"wallet:{wallet.lower()}:{property_id}"
            rows = self._rows_by_query.get(key, [])
            return rows[0] if rows else None
        return None


def test_property_cycle_paid_when_any_tenant_paid():
    paid_at = datetime.utcnow() - timedelta(days=5)
    cursor = _FakeCursor(
        {
            "property:42": [{"payment_date": paid_at, "tenant_id": 1}],
            "wallet:0xtenantb:42": [],
        }
    )
    prop_status = property_rent_period_status(cursor, 42)
    tenant_b = tenant_rent_period_status(cursor, "0xTenantB", 42)

    assert prop_status["current_cycle_paid"] is True
    assert prop_status["can_pay_rent"] is False
    assert tenant_b["current_cycle_paid"] is False


def test_property_cycle_unpaid_when_no_confirmed_payment():
    cursor = _FakeCursor({})
    status = property_rent_period_status(cursor, 99)
    assert status["current_cycle_paid"] is False
    assert status["can_pay_rent"] is True


def test_compute_rent_period_status_after_anniversary():
    paid_at = datetime.utcnow() - timedelta(days=40)
    status = compute_rent_period_status({"payment_date": paid_at})
    assert status["current_cycle_paid"] is False
    assert status["can_pay_rent"] is True
