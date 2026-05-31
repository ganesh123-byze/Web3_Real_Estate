"""Pre-submit confirmation for create-property in the property-owner chatbot."""
from __future__ import annotations

import asyncio

import backend.ai.tools as tools
from backend.ai.tools import (
    _clear_workflow_session,
    _fill_create_property,
    reset_current_messages,
    reset_current_thread_id,
    set_current_messages,
    set_current_thread_id,
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


def _complete_filled() -> dict[str, str]:
    return {
        "name": "Mega Estate",
        "location": "Dubai",
        "total_value": "100",
        "token_supply": "200000",
        "token_symbol": "MEGA",
        "monthly_rent_eth": "55",
    }


def test_confirmation_summary_lists_all_fields():
    summary = format_create_property_confirmation_summary(_complete_filled())
    assert "Mega Estate" in summary
    assert "Dubai" in summary
    assert "100" in summary
    assert "Reply Yes" in summary


def test_fill_create_prompts_rent_limit_before_monthly_rent():
    token = set_current_thread_id("test:create:rent-prompt")
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        res = asyncio.run(
            _fill_create_property(
                {
                    "name": "Brightwave",
                    "location": "USA",
                    "total_value": "100",
                    "token_supply": "1000",
                    "token_symbol": "BW",
                },
                _owner(),
                None,
            )
        )
        assert res.ok
        assert res.data.get("next_field") == "monthly_rent_eth"
        assert "100 ETH" in str(res.data.get("speak_to_user"))
        assert res.data.get("awaiting_create_confirmation") is not True
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_thread_id(token)


def test_fill_create_rejects_monthly_rent_at_or_above_100():
    token = set_current_thread_id("test:create:rent-reject")
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        tools._set_workflow_session(
            "CREATE_PROPERTY",
            {
                "in_progress": True,
                "filled": {
                    "name": "Tower",
                    "location": "NYC",
                    "total_value": "10",
                    "token_supply": "1000",
                    "token_symbol": "TWR",
                },
                "next_field": "monthly_rent_eth",
            },
        )
        res = asyncio.run(
            _fill_create_property({"monthly_rent_eth": "1000"}, _owner(), None)
        )
        assert res.ok
        assert res.data.get("rent_over_limit") is True
        assert "100 ETH" in str(res.data.get("speak_to_user"))
        assert "monthly_rent_eth" not in (res.data.get("filled") or {})
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_thread_id(token)


def test_fill_create_prompts_confirmation_when_all_fields_present():
    token = set_current_thread_id("test:create:confirm-prompt")
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        res = asyncio.run(_fill_create_property(_complete_filled(), _owner(), None))
        assert res.ok
        assert res.data.get("awaiting_create_confirmation") is True
        assert not res.data.get("submitted")
        assert not any(a.type == "SUBMIT_FORM" for a in res.actions)
        assert "Mega Estate" in str(res.data.get("speak_to_user"))
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_thread_id(token)


def test_fill_create_submits_after_user_confirms_yes():
    token = set_current_thread_id("test:create:confirm-yes")
    msg_token = None
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        gate = asyncio.run(_fill_create_property(_complete_filled(), _owner(), None))
        assert gate.data.get("awaiting_create_confirmation") is True

        msg_token = set_current_messages([{"type": "human", "content": "yes"}])
        proceed = asyncio.run(
            _fill_create_property({"confirm_create": True}, _owner(), None)
        )
        assert proceed.ok
        assert proceed.data.get("submitted") is True
        assert any(a.type == "SUBMIT_FORM" for a in proceed.actions)
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        if msg_token is not None:
            reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_fill_create_yes_with_redundant_field_args_submits():
    """LLM re-sending unchanged fields with Yes must not loop confirmation."""
    token = set_current_thread_id("test:create:confirm-yes-redundant")
    msg_token = set_current_messages([{"type": "human", "content": "yes"}])
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
        res = asyncio.run(
            _fill_create_property({**_complete_filled(), "confirm_create": True}, _owner(), None)
        )
        assert res.ok
        assert res.data.get("submitted") is True
        assert any(a.type == "SUBMIT_FORM" for a in res.actions)
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_fill_create_blocks_submit_when_rent_exceeds_on_chain_cap():
    token = set_current_thread_id("test:create:rent-on-chain-cap")
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        tools._set_workflow_session(
            "CREATE_PROPERTY",
            {
                "in_progress": True,
                "filled": {**_complete_filled(), "monthly_rent_eth": "1000"},
                "awaiting_create_confirmation": True,
            },
        )
        res = asyncio.run(
            _fill_create_property({"confirm_create": True}, _owner(), None)
        )
        assert res.ok
        assert res.data.get("submit_blocked") is True
        assert "100 ETH" in str(res.data.get("speak_to_user"))
        assert not any(a.type == "SUBMIT_FORM" for a in res.actions)
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_thread_id(token)


def test_fill_create_clears_draft_when_user_says_no():
    token = set_current_thread_id("test:create:confirm-no")
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
        res = asyncio.run(
            _fill_create_property({"confirm_create": False}, _owner(), None)
        )
        assert res.ok
        assert res.data.get("property_create_cancelled") is True
        assert not (res.data.get("filled") or {})
        assert res.data.get("next_field") == "name"
        assert not any(a.type == "SUBMIT_FORM" for a in res.actions)
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_thread_id(token)


def test_fill_create_field_edit_during_confirmation_re_prompts():
    token = set_current_thread_id("test:create:confirm-edit")
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
        res = asyncio.run(
            _fill_create_property({"location": "Abu Dhabi"}, _owner(), None)
        )
        assert res.ok
        assert res.data.get("awaiting_create_confirmation") is True
        assert (res.data.get("filled") or {}).get("location") == "Abu Dhabi"
        assert "Abu Dhabi" in str(res.data.get("speak_to_user"))
        assert not any(a.type == "SUBMIT_FORM" for a in res.actions)
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_thread_id(token)


def test_fill_create_yes_from_client_history_only():
    token = set_current_thread_id("test:create:yes-history")
    msg_token = set_current_messages(
        [
            {
                "type": "ai",
                "content": (
                    "Here are the property details I have:\n"
                    "- Name: villa\nReply Yes to create and deploy the listing."
                ),
            },
            {"type": "human", "content": "yes"},
        ]
    )
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        tools._set_workflow_session(
            "CREATE_PROPERTY",
            {
                "in_progress": True,
                "filled": {
                    "name": "villa",
                    "location": "usa",
                    "total_value": "100",
                    "token_supply": "1000",
                    "token_symbol": "ETH",
                    "monthly_rent_eth": "0.01",
                },
                "awaiting_create_confirmation": True,
            },
        )
        res = asyncio.run(_fill_create_property({}, _owner(), None))
        assert res.ok
        assert res.data.get("submitted") is True
        assert any(a.type == "SUBMIT_FORM" for a in res.actions)
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)
