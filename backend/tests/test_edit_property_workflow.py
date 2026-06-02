"""Admin copilot: multiple property edits in one chat session."""
from __future__ import annotations

import asyncio

import backend.ai.tools as tools
from backend.ai.tools import (
    _clear_workflow_session,
    _fill_edit_property,
    _get_workflow_session,
    _start_edit_property,
    reset_current_messages,
    reset_current_thread_id,
    set_current_messages,
    set_current_thread_id,
    try_server_edit_property_continuation,
)
from backend.ai.workflow_parsers import (
    parse_edit_property_fields_from_utterance,
    utterance_opens_new_edit_property_flow,
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


def test_parse_edit_rent_follow_up():
    fields = parse_edit_property_fields_from_utterance("also set rent to 10")
    assert fields.get("monthly_rent_eth") == "10"


def test_new_edit_intent_not_field_follow_up():
    assert utterance_opens_new_edit_property_flow("edit skyzone property") is True
    assert utterance_opens_new_edit_property_flow("also set rent to 10") is False


def test_edit_session_keeps_property_id_after_submit():
    token = set_current_thread_id("test:edit:session-after-submit")
    try:
        _clear_workflow_session("EDIT_PROPERTY")
        tools._set_workflow_session(
            "EDIT_PROPERTY",
            {
                "property_id": 42,
                "property_name": "Skyzone",
                "in_progress": False,
                "filled": {},
                "submitted": True,
            },
        )
        session = _get_workflow_session("EDIT_PROPERTY")
        assert session.get("property_id") == 42
        assert session.get("property_name") == "Skyzone"
    finally:
        _clear_workflow_session("EDIT_PROPERTY")
        reset_current_thread_id(token)


def test_edit_continuation_preflight_submits_rent():
    token = set_current_thread_id("test:edit:continuation-rent")
    msg_token = set_current_messages(
        [{"type": "human", "content": "also set rent to 10"}]
    )
    try:
        _clear_workflow_session("EDIT_PROPERTY")
        tools._set_workflow_session(
            "EDIT_PROPERTY",
            {
                "property_id": 7,
                "property_name": "Skyzone",
                "in_progress": False,
                "submitted": True,
            },
        )
        result = asyncio.run(try_server_edit_property_continuation(_owner(), None))
        assert result is not None
        assert result.ok
        assert result.data.get("submitted") is True
        assert result.data.get("filled", {}).get("monthly_rent_eth") == "10"
        assert any(
            a.type == "SUBMIT_FORM" and a.modal == "EDIT_PROPERTY" and a.property_id == 7
            for a in result.actions
        )
        session = _get_workflow_session("EDIT_PROPERTY")
        assert session.get("property_id") == 7
    finally:
        _clear_workflow_session("EDIT_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)
