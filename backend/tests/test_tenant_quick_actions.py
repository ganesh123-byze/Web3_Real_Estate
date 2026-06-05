"""Tenant quick actions must not be parsed as pay-rent property names."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import backend.ai.tools as tools
from backend.ai.tenant_guards import (
    extract_pay_rent_property_hint_from_utterance,
    pay_rent_utterance_names_property,
)
from backend.ai.tenant_quick_actions import (
    TENANT_QUICK_ACTION_IDS,
    is_tenant_advisory_intent,
    tenant_turn_interrupts_workflow,
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


def test_tenant_quick_action_ids_cover_ui_shortcuts():
    actions = [
        ("tenant.pay", "I want to pay this month's rent."),
        ("tenant.rental", "Show me my current rental details and lease."),
        ("tenant.history", "Show my rent payment history."),
        ("tenant.transactions", "Show me all my recent transactions."),
    ]
    for action_id, prompt in actions:
        assert action_id in TENANT_QUICK_ACTION_IDS
        if action_id == "tenant.pay":
            assert tenant_turn_interrupts_workflow(prompt, quick_action_id=action_id) is False
        else:
            assert tenant_turn_interrupts_workflow(prompt, quick_action_id=action_id) is True


def test_advisory_prompts_are_not_property_hints():
    prompts = [
        "Show me my current rental details and lease.",
        "Show my rent payment history.",
        "Show me all my recent transactions.",
        "Show available properties for rent.",
    ]
    for prompt in prompts:
        assert is_tenant_advisory_intent(prompt) is True
        assert extract_pay_rent_property_hint_from_utterance(prompt) == ""
        assert pay_rent_utterance_names_property(prompt) is False


def test_abort_clears_active_pay_rent_session_for_rental_quick_action():
    token = tools.set_current_thread_id("test:tenant-quick-action-abort")
    msg_token = tools.set_current_messages(
        [
            {
                "type": "human",
                "content": "Show me my current rental details and lease.",
                "quick_action_id": "tenant.rental",
            }
        ]
    )
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
        assert tools.abort_pay_rent_workflow_if_interrupted(
            "Show me my current rental details and lease."
        )
        assert tools._get_workflow_session("PAY_RENT") == {}
    finally:
        tools._clear_workflow_session("PAY_RENT")
        tools.reset_current_messages(msg_token)
        tools.reset_current_thread_id(token)


def test_pay_rent_preflight_ignores_rental_quick_action_while_collecting_property():
    token = tools.set_current_thread_id("test:tenant-quick-action-preflight")
    prompt = "Show my rent payment history."
    msg_token = tools.set_current_messages(
        [{"type": "human", "content": prompt, "quick_action_id": "tenant.history"}]
    )
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
        with patch.object(tools, "canonical_role", return_value="tenant"):
            result = asyncio.run(tools.try_server_tenant_pay_rent_turn(_tenant(), None))
        assert result is None
        assert tools._get_workflow_session("PAY_RENT") == {}
    finally:
        tools._clear_workflow_session("PAY_RENT")
        tools.reset_current_messages(msg_token)
        tools.reset_current_thread_id(token)
