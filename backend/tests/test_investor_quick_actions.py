"""Investor quick actions must not be parsed as invest property names."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from backend.ai.investor_quick_actions import (
    INVESTOR_QUICK_ACTION_IDS,
    investor_quick_action_interrupts_workflow,
    investor_turn_interrupts_workflow,
    is_investor_advisory_intent,
)
from backend.ai import tools
from backend.ai.tools import (
    _clear_workflow_session,
    _set_workflow_session,
    abort_invest_workflow_if_interrupted,
    reset_current_messages,
    reset_current_thread_id,
    set_current_messages,
    set_current_thread_id,
    try_server_investor_marketplace_browse,
    try_server_invest_property_turn,
)
from backend.services.auth import AuthUser


def _investor() -> AuthUser:
    return AuthUser(
        id=2,
        wallet_address="0x0000000000000000000000000000000000000002",
        role="investor",
        email=None,
        kyc_status="verified",
        active=True,
    )


def test_investor_quick_action_ids_cover_frontend_actions():
    for action in [
        {
            "id": "investor.marketplace",
            "prompt": "Take me to the marketplace and show me available properties to invest in.",
        },
        {
            "id": "investor.portfolio",
            "prompt": "Show me my investment portfolio with current valuations.",
        },
        {
            "id": "investor.yield",
            "prompt": "What is my current yield and projected returns?",
        },
        {
            "id": "investor.transactions",
            "prompt": "Show me my recent transactions.",
        },
    ]:
        assert action["id"] in INVESTOR_QUICK_ACTION_IDS
        assert investor_turn_interrupts_workflow(
            action["prompt"], quick_action_id=action["id"]
        )


def test_advisory_prompts_are_not_property_hints():
    prompts = [
        "Take me to the marketplace and show me available properties to invest in.",
        "Show me my investment portfolio with current valuations.",
        "What is my current yield and projected returns?",
        "Show me my recent transactions.",
    ]
    for prompt in prompts:
        assert is_investor_advisory_intent(prompt) is True
        assert investor_quick_action_interrupts_workflow("investor.marketplace") is True


def test_abort_clears_active_invest_session_for_quick_action():
    token = set_current_thread_id("test:quick-action-abort")
    msg_token = set_current_messages(
        [
            {
                "type": "human",
                "content": "What is my current yield and projected returns?",
                "quick_action_id": "investor.yield",
            }
        ]
    )
    try:
        _clear_workflow_session("INVEST_PROPERTY")
        _set_workflow_session(
            "INVEST_PROPERTY",
            {
                "in_progress": True,
                "next_field": "property_name",
                "filled": {},
            },
        )
        assert abort_invest_workflow_if_interrupted(
            "What is my current yield and projected returns?"
        )
        assert tools._get_workflow_session("INVEST_PROPERTY") == {}
    finally:
        _clear_workflow_session("INVEST_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_marketplace_quick_action_runs_while_invest_session_was_active():
    token = set_current_thread_id("test:quick-action-marketplace")
    prompt = "Take me to the marketplace and show me available properties to invest in."
    msg_token = set_current_messages(
        [{"type": "human", "content": prompt, "quick_action_id": "investor.marketplace"}]
    )
    try:
        _clear_workflow_session("INVEST_PROPERTY")
        _set_workflow_session(
            "INVEST_PROPERTY",
            {
                "in_progress": True,
                "next_field": "property_name",
                "filled": {},
            },
        )
        with patch(
            "backend.ai.tools._list_properties_tool",
        ) as list_mock:
            from backend.ai.tools import ToolResult

            list_mock.return_value = ToolResult(
                ok=True,
                data={"speak_to_user": "Here are listings.", "marketplace_catalog": True},
            )
            result = asyncio.run(
                try_server_investor_marketplace_browse(_investor(), MagicMock())
            )
        assert result is not None
        assert result.data.get("marketplace_catalog") is True
        assert tools._get_workflow_session("INVEST_PROPERTY") == {}
    finally:
        _clear_workflow_session("INVEST_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_invest_preflight_ignores_yield_quick_action_prompt():
    token = set_current_thread_id("test:quick-action-invest-preflight")
    prompt = "What is my current yield and projected returns?"
    msg_token = set_current_messages(
        [{"type": "human", "content": prompt, "quick_action_id": "investor.yield"}]
    )
    try:
        _clear_workflow_session("INVEST_PROPERTY")
        _set_workflow_session(
            "INVEST_PROPERTY",
            {
                "in_progress": True,
                "next_field": "property_name",
                "filled": {},
            },
        )
        result = asyncio.run(try_server_invest_property_turn(_investor(), MagicMock()))
        assert result is None
        assert tools._get_workflow_session("INVEST_PROPERTY") == {}
    finally:
        _clear_workflow_session("INVEST_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)
