"""Voice create-property: ok during collection vs ok after summary deploy."""
from __future__ import annotations

import asyncio

import backend.ai.tools as tools
from backend.ai.tools import (
    _clear_workflow_session,
    _latest_human_create_property_confirm,
    create_property_server_submit_eligible,
    reset_current_messages,
    reset_current_thread_id,
    set_current_messages,
    set_current_thread_id,
    try_server_apply_create_property_field_answer,
    try_server_create_property_confirmation,
)
from backend.ai.workflow_parsers import (
    create_property_monthly_rent_is_skip,
    format_create_property_confirmation_summary,
)
from backend.services.auth import AuthUser
from backend.tests.test_create_property_high_value_confirm import _complete_filled


def _owner() -> AuthUser:
    return AuthUser(
        id=1,
        wallet_address="0x0000000000000000000000000000000000000001",
        role="property_owner",
        email=None,
        kyc_status="verified",
        active=True,
    )


def test_ok_is_monthly_rent_skip_not_deploy_confirm():
    assert create_property_monthly_rent_is_skip("ok") is True


def test_ok_not_create_confirm_while_collecting_monthly_rent():
    token = set_current_thread_id("test:voice-ok-rent-skip")
    msg_token = set_current_messages([{"type": "human", "content": "ok"}])
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        filled = {k: v for k, v in _complete_filled().items() if k != "monthly_rent_eth"}
        tools._set_workflow_session(
            "CREATE_PROPERTY",
            {
                "in_progress": True,
                "filled": filled,
                "next_field": "monthly_rent_eth",
            },
        )
        assert _latest_human_create_property_confirm() is None
        result = asyncio.run(
            try_server_apply_create_property_field_answer(_owner(), None)
        )
        assert result is not None
        assert result.data.get("awaiting_create_confirmation") is True
        assert "Reply Yes" in (result.data.get("speak_to_user") or "")
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_ok_triggers_submit_after_server_confirmation_summary():
    token = set_current_thread_id("test:voice-ok-submit")
    msg_token = set_current_messages([{"type": "human", "content": "ok"}])
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        tools._set_workflow_session(
            "CREATE_PROPERTY",
            {
                "in_progress": True,
                "filled": _complete_filled(),
                "awaiting_create_confirmation": True,
            },
        )
        assert _latest_human_create_property_confirm() is True
        eligible, name = create_property_server_submit_eligible(_owner())
        assert eligible is True
        assert name == "Mega Estate"
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_ok_triggers_submit_after_llm_summary_in_history():
    summary = format_create_property_confirmation_summary(_complete_filled())
    token = set_current_thread_id("test:voice-ok-llm-summary")
    msg_token = set_current_messages(
        [
            {"type": "assistant", "content": summary},
            {"type": "human", "content": "ok"},
        ]
    )
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        tools._set_workflow_session(
            "CREATE_PROPERTY",
            {
                "in_progress": True,
                "filled": _complete_filled(),
            },
        )
        assert _latest_human_create_property_confirm() is True
        eligible, name = create_property_server_submit_eligible(_owner())
        assert eligible is True
        assert name == "Mega Estate"
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_preflight_confirmation_after_ok_skips_monthly_rent():
    token = set_current_thread_id("test:voice-ok-preflight-confirm")
    msg_token = set_current_messages([{"type": "human", "content": "ok"}])
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        filled = {k: v for k, v in _complete_filled().items() if k != "monthly_rent_eth"}
        tools._set_workflow_session(
            "CREATE_PROPERTY",
            {
                "in_progress": True,
                "filled": filled,
                "next_field": "monthly_rent_eth",
            },
        )
        assert asyncio.run(try_server_create_property_confirmation(_owner(), None)) is None
        apply_result = asyncio.run(
            try_server_apply_create_property_field_answer(_owner(), None)
        )
        assert apply_result is not None
        assert apply_result.data.get("awaiting_create_confirmation") is True
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_voice_applies_spoken_high_total_value():
    token = set_current_thread_id("test:voice-high-value-total")
    msg_token = set_current_messages([{"type": "human", "content": "ten million"}])
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        tools._set_workflow_session(
            "CREATE_PROPERTY",
            {
                "in_progress": True,
                "filled": {"name": "Gold Tower", "location": "Mumbai"},
                "next_field": "total_value",
            },
        )
        result = asyncio.run(
            try_server_apply_create_property_field_answer(_owner(), None)
        )
        assert result is not None
        assert result.data.get("filled", {}).get("total_value") == "10000000"
        assert result.data.get("next_field") == "token_supply"
        speak = str(result.data.get("speak_to_user") or "").lower()
        assert "wallet" not in speak
        assert "maximum" not in speak
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_voice_high_value_submit_eligible_after_summary():
    filled = {
        **(_complete_filled()),
        "total_value": "100000000",
        "token_supply": "5000000",
    }
    summary = format_create_property_confirmation_summary(filled)
    token = set_current_thread_id("test:voice-high-value-submit")
    msg_token = set_current_messages(
        [
            {"type": "assistant", "content": summary},
            {"type": "human", "content": "yes create this property"},
        ]
    )
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        tools._set_workflow_session(
            "CREATE_PROPERTY",
            {
                "in_progress": True,
                "filled": filled,
                "awaiting_create_confirmation": True,
            },
        )
        eligible, name = create_property_server_submit_eligible(_owner())
        assert eligible is True
        assert name == "Mega Estate"
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)
