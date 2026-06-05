"""Tenant copilot: rental browse returns property details, not pay-rent property names."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from backend.ai.tenant_guards import (
    extract_pay_rent_property_hint_from_utterance,
    format_tenant_rental_catalog_speak,
    has_tenant_rental_browse_intent,
    pay_rent_utterance_names_property,
)
from backend.ai.tenant_quick_actions import is_tenant_advisory_intent
from backend.ai.tools import (
    _tenant_rental_catalog_data,
    try_server_tenant_rental_browse,
)
from backend.services.auth import AuthUser


def _tenant() -> AuthUser:
    return AuthUser(
        id=20,
        wallet_address="0x0000000000000000000000000000000000000020",
        role="tenant",
        email=None,
        kyc_status="verified",
        active=True,
    )


def test_has_tenant_rental_browse_intent_matches_available_properties():
    prompt = "Show me the available properties for rent."
    assert has_tenant_rental_browse_intent(prompt) is True


def test_has_tenant_rental_browse_intent_not_explicit_pay_rent_order():
    assert has_tenant_rental_browse_intent("Pay rent for Eiffel Crown Residences") is False


def test_browse_prompts_are_not_property_hints():
    prompts = [
        "Show available properties for rent",
        "What properties are available to rent?",
        "Browse rentals on the tenant dashboard",
    ]
    for prompt in prompts:
        assert is_tenant_advisory_intent(prompt) is True
        assert extract_pay_rent_property_hint_from_utterance(prompt) == ""
        assert pay_rent_utterance_names_property(prompt) is False


def test_format_tenant_rental_catalog_lists_property_details():
    available = [
        {
            "id": 4,
            "name": "Eiffel Crown Residences",
            "location": "Paris",
            "monthly_rent_eth": "1.5",
        }
    ]
    text = format_tenant_rental_catalog_speak(available, total_listed=3)
    assert "Eiffel Crown Residences" in text
    assert "Paris" in text
    assert "monthly rent 1.5 ETH" in text
    assert "Rentals page" in text


def test_tenant_rental_catalog_data_speak_verbatim():
    items = [
        {
            "id": 4,
            "name": "Tower",
            "location": "NYC",
            "has_investors": True,
            "rent_enabled": True,
            "active_rental": False,
            "can_pay_rent": True,
            "monthly_rent_eth": "0.5",
        }
    ]
    data = _tenant_rental_catalog_data(items, available_items=items)
    assert data.get("tenant_rental_catalog") is True
    assert data.get("speak_verbatim") is True
    assert "Tower" in str(data.get("speak_to_user"))


def test_rental_browse_preflight_returns_catalog():
    db = MagicMock()
    rows = [
        {
            "id": 4,
            "name": "Tower",
            "location": "NYC",
            "monthly_rent_wei": "500000000000000000",
            "monthly_rent_eth": "0.5",
            "has_investors": True,
            "rent_enabled": True,
            "active_rental": False,
            "can_pay_rent": True,
            "current_cycle_paid": False,
            "tenant_paid_current_cycle": False,
            "rent_claimed_by_other_tenant": False,
            "token_address": "0xabc",
            "token_symbol": "TWR",
            "token_sale_price_eth": "0.1",
        }
    ]

    with patch(
        "backend.ai.tools._latest_human_utterance",
        return_value="Show available properties for rent",
    ), patch(
        "backend.ai.tools.fetch_tenant_rental_properties",
        return_value=rows,
    ):
        result = asyncio.run(try_server_tenant_rental_browse(_tenant(), db))

    assert result is not None
    assert result.ok
    assert "Tower" in str(result.data.get("speak_to_user"))
    assert any(a.type == "NAVIGATE" and a.route == "/tenant/rentals" for a in result.actions)


def test_browse_aborts_active_pay_rent_session():
    import backend.ai.tools as tools

    token = tools.set_current_thread_id("test:tenant-browse-abort")
    prompt = "Show available properties for rent"
    msg_token = tools.set_current_messages([{"type": "human", "content": prompt}])
    try:
        tools._clear_workflow_session("PAY_RENT")
        tools._set_workflow_session(
            "PAY_RENT",
            {
                "in_progress": True,
                "next_field": "property_name",
                "filled": {},
            },
        )
        with patch.object(tools, "canonical_role", return_value="tenant"), patch.object(
            tools, "_latest_human_utterance", return_value=prompt
        ), patch.object(
            tools,
            "fetch_tenant_rental_properties",
            return_value=[],
        ):
            result = asyncio.run(tools.try_server_tenant_rental_browse(_tenant(), MagicMock()))
        assert result is not None
        assert tools._get_workflow_session("PAY_RENT") == {}
    finally:
        tools._clear_workflow_session("PAY_RENT")
        tools.reset_current_messages(msg_token)
        tools.reset_current_thread_id(token)
