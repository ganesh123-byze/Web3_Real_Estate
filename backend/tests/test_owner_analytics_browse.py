"""Admin copilot: View Analytics returns portfolio overview, not create summary."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from backend.ai.owner_guards import (
    format_owner_analytics_overview_speak,
    has_owner_analytics_intent,
    owner_analytics_tool_payload,
)
from backend.ai.tools import (
    reset_current_messages,
    reset_current_thread_id,
    set_current_messages,
    set_current_thread_id,
    try_server_owner_analytics_overview,
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


def test_has_owner_analytics_intent_matches_quick_action():
    prompt = "Show me analytics across my properties."
    assert has_owner_analytics_intent(prompt) is True


def test_has_owner_analytics_intent_not_single_property_details():
    assert has_owner_analytics_intent("Show details for Gold Plaza") is False
    assert has_owner_analytics_intent("Help me create a new property.") is False


def test_format_owner_analytics_is_portfolio_not_create_summary():
    data = {
        "summary": {
            "properties_you_own": 2,
            "property_names": ["Gold Plaza", "BlueMoon Residency"],
            "total_rent_collected_eth": "1.5",
            "rent_payments_count": 3,
            "total_rent_distributed_eth": "0.8",
            "rent_distributions_count": 1,
            "active_rentals": 1,
            "investors_on_your_properties": 4,
            "properties_with_token_sales": 1,
            "total_investment_volume_eth": "10",
            "total_investments_recorded": 2,
        },
        "property_performance": [
            {
                "id": 1,
                "name": "Gold Plaza",
                "sold_percentage": 12.5,
                "tokens_sold": 1200,
                "token_supply": 10000,
            }
        ],
        "recent_transactions": [{"id": 1}, {"id": 2}],
    }
    text = format_owner_analytics_overview_speak(data)
    assert "Portfolio analytics across your properties" in text
    assert "Gold Plaza" in text
    assert "BlueMoon Residency" in text
    assert "Rent collected" in text
    assert "Investors on your properties" in text
    assert "Property performance" in text
    assert "Reply Yes to create" not in text
    assert "Token symbol" not in text


def test_owner_analytics_tool_payload_marks_verbatim():
    payload = owner_analytics_tool_payload(
        {"summary": {"properties_you_own": 1, "property_names": ["Tower"]}}
    )
    assert payload.get("owner_analytics_overview") is True
    assert payload.get("speak_verbatim") is True
    assert "Portfolio analytics" in str(payload.get("speak_to_user"))


def test_preflight_owner_analytics_after_create_prompt():
    token = set_current_thread_id("test:owner-analytics-preflight")
    msg_token = set_current_messages(
        [{"type": "human", "content": "Show me analytics across my properties."}]
    )
    overview = {
        "summary": {
            "properties_you_own": 1,
            "property_names": ["New Tower"],
            "total_rent_collected_eth": "0",
            "rent_payments_count": 0,
            "total_rent_distributed_eth": "0",
            "rent_distributions_count": 0,
            "active_rentals": 0,
            "investors_on_your_properties": 0,
            "properties_with_token_sales": 0,
            "total_investment_volume_eth": "0",
            "total_investments_recorded": 0,
        },
        "property_performance": [],
        "recent_transactions": [],
    }
    try:
        with patch(
            "backend.ai.tools._build_owner_analytics_overview",
            return_value=overview,
        ):
            result = asyncio.run(try_server_owner_analytics_overview(_owner(), MagicMock()))
        assert result is not None
        speak = str(result.data.get("speak_to_user") or "")
        assert "Portfolio analytics" in speak
        assert result.data.get("owner_analytics_overview") is True
    finally:
        reset_current_messages(msg_token)
        reset_current_thread_id(token)
