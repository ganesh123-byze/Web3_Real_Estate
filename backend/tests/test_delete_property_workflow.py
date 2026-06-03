"""Admin copilot: delete property identification + confirmation flow."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import backend.ai.tools as tools
from backend.ai.tools import (
    _clear_workflow_session,
    _confirm_delete_property,
    _get_workflow_session,
    _start_delete_property,
    reset_current_messages,
    reset_current_thread_id,
    set_current_messages,
    set_current_thread_id,
    try_server_delete_property_continuation,
)
from backend.ai.workflow_parsers import (
    delete_property_identification_prompt,
    parse_delete_property_confirm_intent,
    parse_delete_property_hint_from_utterance,
    parse_delete_property_id_from_utterance,
    utterance_opens_delete_property_flow,
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


def test_parse_delete_property_id_from_utterance():
    assert parse_delete_property_id_from_utterance("7") == 7
    assert parse_delete_property_id_from_utterance("property id 12") == 12
    assert parse_delete_property_id_from_utterance("Skyzone") is None


def test_parse_delete_property_hint_from_utterance():
    assert parse_delete_property_hint_from_utterance("delete skyzone property") == "skyzone"
    assert parse_delete_property_hint_from_utterance("remove property 9") == "9"


def test_utterance_opens_delete_property_flow():
    assert utterance_opens_delete_property_flow("delete a property") is True
    assert utterance_opens_delete_property_flow("also set rent to 10") is False


def test_parse_delete_property_confirm_intent():
    assert parse_delete_property_confirm_intent("yes") is True
    assert parse_delete_property_confirm_intent("no") is False
    assert parse_delete_property_confirm_intent("delete it") is True
    assert parse_delete_property_confirm_intent("cancel") is False


def test_start_delete_prompts_for_exact_name_or_id():
    token = set_current_thread_id("test:delete:ask-id")
    try:
        _clear_workflow_session("DELETE_PROPERTY")
        res = asyncio.run(_start_delete_property({}, _owner(), None))
        assert res.ok
        assert res.data.get("speak_to_user") == delete_property_identification_prompt()
        assert res.data.get("awaiting_delete_confirmation") is False
        session = _get_workflow_session("DELETE_PROPERTY")
        assert session.get("in_progress") is True
        assert session.get("property_id") is None
    finally:
        _clear_workflow_session("DELETE_PROPERTY")
        reset_current_thread_id(token)


def test_start_delete_resolves_property_and_asks_confirmation():
    token = set_current_thread_id("test:delete:confirm-prompt")
    prop = {"id": 7, "name": "Skyzone"}
    try:
        _clear_workflow_session("DELETE_PROPERTY")
        fake_cursor = type(
            "C",
            (),
            {"close": lambda self: None},
        )()
        fake_db = type(
            "DB",
            (),
            {"cursor": lambda self, dictionary=True: fake_cursor},
        )()
        with patch(
            "backend.ai.tools._resolve_owned_property_for_user",
            return_value=(prop, None),
        ), patch(
            "backend.ai.tools.lock_property",
            return_value={"id": 7, "name": "Skyzone", "token_address": None},
        ), patch(
            "backend.ai.tools._property_has_activity",
            return_value=False,
        ):
            res = asyncio.run(
                _start_delete_property({"property_name": "Skyzone"}, _owner(), fake_db)
            )
        assert res.ok
        assert res.data.get("awaiting_delete_confirmation") is True
        assert res.data.get("property_id") == 7
        assert "Skyzone" in str(res.data.get("speak_to_user"))
        assert "Yes" in str(res.data.get("speak_to_user"))
        session = _get_workflow_session("DELETE_PROPERTY")
        assert session.get("property_id") == 7
        assert session.get("awaiting_delete_confirmation") is True
    finally:
        _clear_workflow_session("DELETE_PROPERTY")
        reset_current_thread_id(token)


def test_confirm_delete_false_cancels_without_db():
    token = set_current_thread_id("test:delete:cancel")
    try:
        _clear_workflow_session("DELETE_PROPERTY")
        tools._set_workflow_session(
            "DELETE_PROPERTY",
            {
                "in_progress": True,
                "property_id": 7,
                "property_name": "Skyzone",
                "awaiting_delete_confirmation": True,
            },
        )
        res = asyncio.run(
            _confirm_delete_property({"confirm_delete": False}, _owner(), None)
        )
        assert res.ok
        assert res.data.get("cancelled") is True
        assert "cancelled" in str(res.data.get("speak_to_user")).lower()
        assert _get_workflow_session("DELETE_PROPERTY") == {}
    finally:
        _clear_workflow_session("DELETE_PROPERTY")
        reset_current_thread_id(token)


def test_delete_continuation_handles_no_after_confirmation():
    token = set_current_thread_id("test:delete:continuation-no")
    msg_token = set_current_messages([{"type": "human", "content": "no"}])
    try:
        _clear_workflow_session("DELETE_PROPERTY")
        tools._set_workflow_session(
            "DELETE_PROPERTY",
            {
                "in_progress": True,
                "property_id": 7,
                "property_name": "Skyzone",
                "awaiting_delete_confirmation": True,
            },
        )
        result = asyncio.run(try_server_delete_property_continuation(_owner(), None))
        assert result is not None
        assert result.ok
        assert result.data.get("cancelled") is True
    finally:
        _clear_workflow_session("DELETE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)
