"""Admin copilot read tools are scoped to properties the signed-in owner created."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from backend.ai.tools import (
    _build_owner_analytics_overview,
    _get_all_transactions,
    _get_property_details,
)
from backend.services.auth import AuthUser


def _owner() -> AuthUser:
    return AuthUser(
        id=1,
        wallet_address="0x0000000000000000000000000000000000000001",
        role="property_owner",
        email=None,
        kyc_status="verified",
        active=True,
    )


def test_owner_analytics_summary_is_owned_scope_only():
    cursor = MagicMock()
    cursor.fetchall.side_effect = [
        [{"id": 3, "name": "Gold Plaza", "owner_wallet": "0x01", "token_address": "0xt", "token_supply": 1000, "tokens_available": 500, "tokens_sold": 500, "is_active": True}],
        [],
        [],
        [],
        [],
        [],
        [],
        [],
        [],
    ]
    cursor.fetchone.side_effect = [
        {"collected": 0, "payments_count": 0},
        {"distributed": 0, "distributions_count": 0},
        {"active": 0},
        {"n": 2},
        {"n": 0, "spent": 0},
    ]

    with patch("backend.ai.tools.filter_dashboard_listable_properties", side_effect=lambda _c, rows: rows), patch(
        "backend.ai.tools._serialize_property",
        side_effect=lambda row: {
            "id": row["id"],
            "name": row["name"],
            "owner_wallet": row["owner_wallet"],
            "sold_percentage": 50,
            "tokens_sold": 500,
            "token_supply": 1000,
            "monthly_rent_eth": "1",
        },
    ):
        data = _build_owner_analytics_overview(cursor, _owner())

    assert data["summary"]["scope"] == "owned_properties_only"
    assert data["summary"]["properties_you_own"] == 1
    assert data["summary"]["property_names"] == ["Gold Plaza"]
    assert "platform_investors" not in data["summary"]
    executed = " ".join(str(call.args[0]) for call in cursor.execute.call_args_list)
    assert "owner_wallet" in executed.lower()


def test_get_all_transactions_adds_owner_filter_for_property_owner():
    db = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    db.cursor.return_value = cursor

    asyncio.run(_get_all_transactions({"limit": 5}, _owner(), db))

    query = cursor.execute.call_args.args[0]
    assert "owner_wallet" in query.lower()


def test_get_property_details_rejects_other_admin_property():
    db = MagicMock()
    cursor = MagicMock()
    db.cursor.return_value = cursor
    foreign = {
        "id": 9,
        "name": "Other Admin Tower",
        "owner_wallet": "0x0000000000000000000000000000000000000099",
        "is_active": True,
    }

    with patch("backend.ai.tools.fetch_active_property", return_value=foreign):
        result = asyncio.run(_get_property_details({"property_id": 9}, _owner(), db))

    assert result.ok is False
    assert "you created" in str(result.error).lower()
