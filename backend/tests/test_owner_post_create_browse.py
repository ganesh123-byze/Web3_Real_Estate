"""After create-property success, owner browse quick actions must not replay the summary."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from backend.ai.owner_guards import (
    has_owner_browse_intent,
    has_owner_investors_intent,
    has_owner_rent_intent,
)
from backend.ai.tools import (
    _clear_workflow_session,
    reset_current_messages,
    reset_current_thread_id,
    set_current_messages,
    set_current_thread_id,
    try_server_create_property_confirmation,
    try_server_owner_investors_overview,
    try_server_owner_rent_overview,
)
from backend.ai.workflow_parsers import format_create_property_confirmation_summary
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


def test_owner_browse_intent_matches_rent_and_investor_quick_actions():
    assert has_owner_rent_intent("Show pending rent collections and overdue tenants.")
    assert has_owner_investors_intent("Show me the investors holding shares of my properties.")
    assert has_owner_browse_intent("Show pending rent collections and overdue tenants.")


def test_preflight_investors_after_create_success_not_confirmation_summary():
    summary = format_create_property_confirmation_summary(
        {
            "name": "Skyview",
            "location": "Hyderabad",
            "total_value": "1000",
            "token_supply": "100",
            "token_symbol": "SV",
            "monthly_rent_eth": "0",
        }
    )
    deploy = (
        "Your property details for Skyview were submitted successfully. "
        "Please hold for a moment while we deploy your listing on-chain."
    )
    success = "Property 'Skyview' created successfully."
    token = set_current_thread_id("test:post-create-investors")
    msg_token = set_current_messages(
        [
            {"type": "ai", "content": summary},
            {"type": "human", "content": "yes"},
            {"type": "ai", "content": deploy},
            {"type": "ai", "content": success},
            {
                "type": "human",
                "content": "Show me the investors holding shares of my properties.",
            },
        ]
    )
    investors_payload = {
        "total_investors": 2,
        "properties": [
            {
                "property_id": 1,
                "property_name": "Skyview",
                "investors": [
                    {
                        "wallet_address": "0xabc",
                        "token_amount": 10,
                        "ownership_percentage": 10,
                    }
                ],
            }
        ],
    }
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        with patch(
            "backend.ai.tools._get_my_investors",
            return_value=MagicMock(ok=True, data=investors_payload, actions=[]),
        ):
            investors = asyncio.run(try_server_owner_investors_overview(_owner(), MagicMock()))
            confirm = asyncio.run(try_server_create_property_confirmation(_owner(), None))
        assert investors is not None
        speak = str(investors.data.get("speak_to_user") or "")
        assert "Investors on your properties" in speak
        assert "Reply Yes to create" not in speak
        assert confirm is None
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_preflight_rent_after_deploy_pending_not_confirmation_summary():
    summary = format_create_property_confirmation_summary(
        {
            "name": "Tower",
            "location": "Dubai",
            "total_value": "500",
            "token_supply": "50",
            "token_symbol": "TW",
            "monthly_rent_eth": "1",
        }
    )
    deploy = (
        "Your property details for Tower were submitted successfully. "
        "Please hold for a moment while we deploy your listing on-chain."
    )
    token = set_current_thread_id("test:post-create-rent-deploy")
    msg_token = set_current_messages(
        [
            {"type": "ai", "content": summary},
            {"type": "human", "content": "yes"},
            {"type": "ai", "content": deploy},
            {
                "type": "human",
                "content": "Show pending rent collections and overdue tenants.",
            },
        ]
    )
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        with patch(
            "backend.ai.tools._get_rent_analytics",
            return_value=MagicMock(
                ok=True,
                data={"total_rent_collected_eth": "1.5", "payments_count": 1, "active_rentals": 1},
                actions=[],
            ),
        ), patch(
            "backend.ai.tools._get_my_rent_collections",
            return_value=MagicMock(ok=True, data={"payments": []}, actions=[]),
        ):
            rent = asyncio.run(try_server_owner_rent_overview(_owner(), MagicMock()))
            confirm = asyncio.run(try_server_create_property_confirmation(_owner(), None))
        assert rent is not None
        speak = str(rent.data.get("speak_to_user") or "")
        assert "Rent and yield" in speak
        assert "Here are the property details" not in speak
        assert confirm is None
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)
