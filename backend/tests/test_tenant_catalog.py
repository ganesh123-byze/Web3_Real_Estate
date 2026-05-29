"""Tests for tenant rental catalog (tenant dashboard parity)."""
from __future__ import annotations

from backend.services.tenant_catalog import filter_tenant_dashboard_available


def test_filter_tenant_dashboard_available_matches_rentals_page_rules():
    rows = [
        {
            "id": 1,
            "name": "Funded Available",
            "has_investors": True,
            "rent_enabled": True,
            "active_rental": False,
            "current_cycle_paid": False,
        },
        {
            "id": 2,
            "name": "No Investors",
            "has_investors": False,
            "rent_enabled": True,
            "active_rental": False,
            "current_cycle_paid": False,
        },
        {
            "id": 3,
            "name": "Already Paid",
            "has_investors": True,
            "rent_enabled": True,
            "active_rental": False,
            "current_cycle_paid": True,
        },
        {
            "id": 4,
            "name": "Active Rental",
            "has_investors": True,
            "rent_enabled": True,
            "active_rental": True,
            "current_cycle_paid": False,
        },
        {
            "id": 5,
            "name": "No Rent Set",
            "has_investors": True,
            "rent_enabled": False,
            "active_rental": False,
            "current_cycle_paid": False,
        },
    ]
    available = filter_tenant_dashboard_available(rows)
    assert [p["id"] for p in available] == [1]


def test_tools_for_tenant_excludes_investor_list_properties():
    from backend.ai.tools import tools_for_role

    names = {t.name for t in tools_for_role("tenant")}
    assert "list_tenant_properties" in names
    assert "list_properties" not in names


def test_tools_for_investor_keeps_marketplace_list():
    from backend.ai.tools import tools_for_role

    names = {t.name for t in tools_for_role("investor")}
    assert "list_properties" in names
    assert "list_tenant_properties" not in names
