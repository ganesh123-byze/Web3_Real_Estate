"""Server preflight emits canonical create-property confirmation (Edit/Delete)."""
from __future__ import annotations

import asyncio

import backend.ai.tools as tools
from backend.ai.tools import (
    _clear_workflow_session,
    reset_current_messages,
    reset_current_thread_id,
    set_current_messages,
    set_current_thread_id,
    try_server_create_property_confirmation,
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


def test_preflight_confirmation_includes_edit_and_delete():
    tid = set_current_thread_id("test:preflight-confirm")
    msg_token = set_current_messages(
        [
            {"type": "ai", "content": "What's the ticker symbol for the token?"},
            {"type": "human", "content": "eth"},
            {"type": "ai", "content": tools.create_property_monthly_rent_collection_prompt()},
            {"type": "human", "content": "1"},
        ]
    )
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        tools._set_workflow_session(
            "CREATE_PROPERTY",
            {
                "in_progress": True,
                "filled": {
                    "name": "google",
                    "location": "USA",
                    "total_value": "1000",
                    "token_supply": "100",
                    "token_symbol": "eth",
                },
                "next_field": "monthly_rent_eth",
            },
        )
        result = asyncio.run(try_server_create_property_confirmation(_owner(), None))
        assert result is not None
        speak = str(result.data.get("speak_to_user") or "")
        assert "To edit," in speak
        assert "To delete" in speak
        assert "google" in speak
        assert result.data.get("awaiting_create_confirmation") is True
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(tid)


def test_preflight_skips_when_still_missing_fields():
    tid = set_current_thread_id("test:preflight-skip")
    msg_token = set_current_messages([])
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        tools._set_workflow_session(
            "CREATE_PROPERTY",
            {"in_progress": True, "filled": {"name": "Only Name"}, "next_field": "location"},
        )
        assert asyncio.run(try_server_create_property_confirmation(_owner(), None)) is None
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(tid)
