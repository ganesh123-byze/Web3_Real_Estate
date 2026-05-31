"""High-value create-property confirmation in the property-owner chatbot."""
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
from backend.ai.workflow_parsers import (
    assess_high_value_create_property,
    assess_monthly_rent_over_chatbot_limit,
    parse_yes_no_confirmation,
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


def test_assess_high_value_when_token_supply_large():
    out = assess_high_value_create_property(
        {
            "name": "Tower",
            "location": "NYC",
            "total_value": "10",
            "token_supply": "100000",
            "token_symbol": "TWR",
        }
    )
    assert out["is_high"] is True
    assert any("Token supply" in r for r in out["reasons"])


def test_assess_not_high_for_typical_low_values():
    out = assess_high_value_create_property(
        {
            "name": "Villa",
            "location": "Miami",
            "total_value": "10",
            "token_supply": "10000",
            "token_symbol": "VIL",
            "monthly_rent_eth": "0.5",
        }
    )
    assert out["is_high"] is False


def test_high_rent_does_not_trigger_high_value_confirmation():
    """Rent is capped separately; moderate rent must not add high-value reasons."""
    out = assess_high_value_create_property(
        {
            "name": "Tower",
            "location": "NYC",
            "total_value": "10",
            "token_supply": "10000",
            "token_symbol": "TWR",
            "monthly_rent_eth": "12",
        }
    )
    assert out["is_high"] is False


def test_rent_over_fifty_is_blocked():
    out = assess_monthly_rent_over_chatbot_limit({"monthly_rent_eth": "51"})
    assert out["over_limit"] is True
    assert "50" in str(out["speak_to_user"])
    assert assess_monthly_rent_over_chatbot_limit({"monthly_rent_eth": "49"})["over_limit"] is False


def test_fill_create_blocks_rent_over_fifty():
    token = set_current_thread_id("test:create:rent-cap")
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        res = asyncio.run(
            _fill_create_property(
                {
                    "name": "Sky Tower",
                    "location": "Dubai",
                    "total_value": "10",
                    "token_supply": "10000",
                    "token_symbol": "SKY",
                    "monthly_rent_eth": "55",
                },
                _owner(),
                None,
            )
        )
        assert res.ok
        assert res.data.get("rent_over_limit") is True
        assert "monthly_rent_eth" not in (res.data.get("filled") or {})
        assert not any(a.type == "SUBMIT_FORM" for a in res.actions)
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_thread_id(token)


def test_parse_yes_no_confirmation():
    assert parse_yes_no_confirmation("Yes") is True
    assert parse_yes_no_confirmation("no thanks") is False
    assert parse_yes_no_confirmation("maybe later") is None


def test_fill_create_gates_submit_until_user_confirms_yes():
    token = set_current_thread_id("test:create:high-value-gate")
    msg_token = set_current_messages(
        [
            {"type": "ai", "content": "What's the monthly rent?"},
            {"type": "human", "content": "20"},
        ]
    )
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        filled = {
            "name": "Mega Estate",
            "location": "Dubai",
            "total_value": "100",
            "token_supply": "200000",
            "token_symbol": "MEGA",
            "monthly_rent_eth": "12",
        }
        gate = asyncio.run(
            _fill_create_property({**filled, "submit": True}, _owner(), None)
        )
        assert gate.ok
        assert gate.data.get("awaiting_high_value_confirmation") is True
        assert not gate.actions
        assert "Yes" in str(gate.data.get("speak_to_user"))

        proceed = asyncio.run(
            _fill_create_property(
                {"confirm_high_values": True, "submit": True},
                _owner(),
                None,
            )
        )
        assert proceed.ok
        assert proceed.data.get("submitted") is True
        assert any(a.type == "SUBMIT_FORM" for a in proceed.actions)
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_fill_create_cancels_when_user_says_no():
    token = set_current_thread_id("test:create:high-value-cancel")
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        tools._set_workflow_session(
            "CREATE_PROPERTY",
            {
                "in_progress": True,
                "filled": {
                    "name": "Big",
                    "location": "LA",
                    "total_value": "80",
                    "token_supply": "90000",
                    "token_symbol": "BIG",
                },
                "awaiting_high_value_confirmation": True,
                "high_values_confirmed": False,
            },
        )
        res = asyncio.run(
            _fill_create_property({"confirm_high_values": False}, _owner(), None)
        )
        assert res.ok
        assert res.data.get("cancelled") is True
        assert res.data.get("property_create_cancelled") is True
        assert not any(a.type == "SUBMIT_FORM" for a in res.actions)
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_thread_id(token)


def test_fill_create_yes_after_cancel_says_listing_canceled():
    token = set_current_thread_id("test:create:high-value-yes-after-cancel")
    msg_token = set_current_messages(
        [
            {"type": "ai", "content": "Do you want to proceed? Reply Yes or No."},
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
                    "name": "Big",
                    "location": "LA",
                    "total_value": "80",
                    "token_supply": "90000",
                    "token_symbol": "BIG",
                    "monthly_rent_eth": "12",
                },
                "property_create_cancelled": True,
                "awaiting_high_value_confirmation": False,
                "high_values_confirmed": False,
            },
        )
        res = asyncio.run(
            _fill_create_property({"submit": True}, _owner(), None)
        )
        assert res.ok
        assert res.data.get("property_create_cancelled") is True
        assert "canceled" in str(res.data.get("speak_to_user")).lower()
        assert not any(a.type == "SUBMIT_FORM" for a in res.actions)
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_fill_create_yes_with_client_history_only():
    """Yes after high-value gate must submit using server session (no tool history)."""
    token = set_current_thread_id("test:create:yes-client-history")
    msg_token = set_current_messages(
        [
            {
                "type": "ai",
                "content": (
                    "These property values are on the high side... "
                    "Do you want to proceed? Reply Yes or No."
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
                "awaiting_high_value_confirmation": True,
                "high_values_confirmed": False,
                "next_field": None,
            },
        )
        res = asyncio.run(_fill_create_property({"submit": True}, _owner(), None))
        assert res.ok
        assert res.data.get("submitted") is True
        assert not res.data.get("missing")
        assert any(a.type == "SUBMIT_FORM" for a in res.actions)
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_fill_create_yes_survives_assistant_created_successfully_in_history():
    token = set_current_thread_id("test:create:yes-history-boundary")
    msg_token = set_current_messages(
        [
            {"type": "assistant", "content": "Property 'villa' created successfully."},
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
                "awaiting_high_value_confirmation": True,
                "high_values_confirmed": False,
            },
        )
        res = asyncio.run(_fill_create_property({}, _owner(), None))
        assert res.ok
        assert res.data.get("submitted") is True
        assert res.data.get("filled", {}).get("name") == "villa"
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_start_create_property_does_not_clear_high_value_draft():
    token = set_current_thread_id("test:create:start-during-confirm")
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        tools._set_workflow_session(
            "CREATE_PROPERTY",
            {
                "in_progress": True,
                "filled": {"name": "villa", "location": "usa", "total_value": "100"},
                "awaiting_high_value_confirmation": True,
            },
        )
        from backend.ai.tools import _start_create_property

        res = asyncio.run(_start_create_property({}, _owner(), None))
        assert res.ok
        assert res.data.get("awaiting_high_value_confirmation") is True
        assert (res.data.get("filled") or {}).get("name") == "villa"
        session = tools._get_workflow_session("CREATE_PROPERTY")
        assert session.get("awaiting_high_value_confirmation") is True
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_thread_id(token)
