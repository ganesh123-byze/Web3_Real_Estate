"""Tests for copilot workflow session reset (chat refresh / abandoned create)."""
from __future__ import annotations

import asyncio

from backend.ai.schemas import ChatMessage
from backend.ai.tools import (
    _clear_workflow_session,
    _fill_create_property,
    _get_workflow_session,
    _set_workflow_session,
    _start_create_property,
    copilot_messages_indicate_ui_reset,
    prepare_copilot_turn,
    reset_workflow_sessions_for_thread,
    reset_current_messages,
    reset_current_thread_id,
    set_current_messages,
    set_current_thread_id,
)
from backend.services.auth import AuthUser


def _dummy_owner() -> AuthUser:
    return AuthUser(
        id=1,
        wallet_address="0x0000000000000000000000000000000000000001",
        role="property_owner",
        email=None,
        kyc_status="verified",
        active=True,
    )


def test_copilot_messages_indicate_ui_reset_after_clear():
    welcome = [ChatMessage(role="assistant", content="Hi! I'm EstateChain Copilot.")]
    assert copilot_messages_indicate_ui_reset(welcome) is True
    assert copilot_messages_indicate_ui_reset(
        welcome + [ChatMessage(role="user", content="Create a new property")]
    ) is True
    assert copilot_messages_indicate_ui_reset(
        welcome
        + [
            ChatMessage(role="user", content="Create a new property"),
            ChatMessage(role="assistant", content="What's the name?"),
            ChatMessage(role="user", content="Tower A"),
        ]
    ) is False


def test_prepare_copilot_turn_clears_stale_create_property_session():
    thread = "test:reset:thread"
    token = set_current_thread_id(thread)
    try:
        _set_workflow_session(
            "CREATE_PROPERTY",
            {
                "in_progress": True,
                "filled": {"name": "Abandoned Tower", "location": "Dubai"},
                "next_field": "total_value",
                "submitted": False,
            },
        )
        welcome = [ChatMessage(role="assistant", content="Hi! I'm EstateChain Copilot.")]
        assert prepare_copilot_turn(thread, welcome) is True
        assert _get_workflow_session("CREATE_PROPERTY") == {}
    finally:
        reset_workflow_sessions_for_thread(thread)
        reset_current_thread_id(token)


def test_start_create_property_always_clears_partial_draft():
    thread = "test:start:clears-partial"
    token = set_current_thread_id(thread)
    try:
        _set_workflow_session(
            "CREATE_PROPERTY",
            {
                "in_progress": True,
                "filled": {"name": "Stale Villa", "location": "Paris"},
                "next_field": "total_value",
                "submitted": False,
            },
        )
        res = asyncio.run(_start_create_property({}, _dummy_owner(), None))
        assert res.ok
        assert res.data.get("next_field") == "name"
        assert res.data.get("filled") == {}
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_thread_id(token)


def test_fill_create_after_refresh_does_not_resume_abandoned_fields():
    thread = "test:fill:after-refresh"
    msg_token = set_current_messages(
        [
            ChatMessage(role="assistant", content="Hi! I'm EstateChain Copilot."),
            ChatMessage(role="user", content="I want to create a new property"),
        ]
    )
    token = set_current_thread_id(thread)
    try:
        _set_workflow_session(
            "CREATE_PROPERTY",
            {
                "in_progress": True,
                "filled": {"name": "Old Name", "location": "Old City"},
                "next_field": "total_value",
                "submitted": False,
            },
        )
        res = asyncio.run(_fill_create_property({}, _dummy_owner(), None))
        assert res.ok
        filled = res.data.get("filled") or {}
        assert "name" not in filled
        assert res.data.get("next_field") == "name"
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)
