"""Pre-submit confirmation for create-property in the property-owner chatbot."""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

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
from backend.tests._create_property_limits_test_utils import patch_generous_create_property_limits


@pytest.fixture(autouse=True)
def _generous_create_property_limits():
    with patch_generous_create_property_limits():
        yield


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


def test_total_value_collection_prompt():
    from backend.services.property_create_limits import (
        CreatePropertyLimits,
        total_value_collection_prompt,
    )

    limits = CreatePropertyLimits(
        owner_wallet="0x1",
        owner_balance_eth=Decimal("2.5"),
        deployer_balance_eth=Decimal("1"),
        max_monthly_rent_eth=Decimal("2.498"),
        max_total_value_eth=Decimal("125000"),
        min_owner_balance_eth=Decimal("0.001"),
        min_deployer_balance_eth=Decimal("0.05"),
        platform_deploy_ready=True,
        owner_balance_sufficient=True,
        deployer_warning=None,
        deployment_block_reason=None,
        owner_block_reason=None,
    )
    prompt = total_value_collection_prompt(limits)
    assert "2.5" in prompt
    assert "125000" in prompt
    assert "total property value" in prompt.lower()


def test_parse_yes_no_strips_trailing_punctuation():
    from backend.ai.workflow_parsers import parse_yes_no_confirmation

    assert parse_yes_no_confirmation("yes'") is True
    assert parse_yes_no_confirmation("Yes.") is True


def test_backfill_recovers_fields_when_llm_skipped_tool_calls():
    from backend.ai.tools import (
        _backfill_create_property_filled_from_history,
        _clear_workflow_session,
        reset_current_messages,
        reset_current_thread_id,
        set_current_messages,
        set_current_thread_id,
    )

    token = set_current_thread_id("test:create:backfill")
    msg_token = set_current_messages(
        [
            {"type": "ai", "content": "What's the name of the property?"},
            {"type": "human", "content": "brightwave"},
            {"type": "ai", "content": "Where is it located?"},
            {"type": "human", "content": "usa"},
            {
                "type": "ai",
                "content": "Your wallet can support a total property value of up to 10 ETH. What's the total value?",
            },
            {"type": "human", "content": "1000"},
        ]
    )
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        filled = _backfill_create_property_filled_from_history({})
        assert filled.get("name") == "brightwave"
        assert filled.get("location") == "usa"
        assert filled.get("total_value") == "1000"
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_fill_create_blocks_confirmation_when_total_value_exceeds_cap():
    token = set_current_thread_id("test:create:confirm-cap-block")
    msg_token = set_current_messages(
        [
            {"type": "ai", "content": "What's the name of the property?"},
            {"type": "human", "content": "brightwave"},
            {"type": "ai", "content": "Where is it located?"},
            {"type": "human", "content": "usa"},
            {"type": "ai", "content": "What's the total property value in ETH?"},
            {"type": "human", "content": "1000"},
            {"type": "ai", "content": "How many ownership tokens should we mint?"},
            {"type": "human", "content": "1000"},
            {"type": "ai", "content": "What ticker symbol do you want?"},
            {"type": "human", "content": "eth"},
            {"type": "ai", "content": "What's the monthly rent in ETH?"},
            {"type": "human", "content": "99"},
        ]
    )
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        with patch_generous_create_property_limits(owner_balance_eth=Decimal("0.0002")):
            res = asyncio.run(_fill_create_property({}, _owner(), None))
        assert res.ok
        assert res.data.get("total_value_over_limit") is True or res.data.get(
            "submit_blocked"
        )
        assert not res.data.get("awaiting_create_confirmation")
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_fill_create_prompts_total_value_cap_before_total_value():
    token = set_current_thread_id("test:create:total-value-prompt")
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        res = asyncio.run(
            _fill_create_property(
                {
                    "name": "Brightwave",
                    "location": "USA",
                },
                _owner(),
                None,
            )
        )
        assert res.ok
        assert res.data.get("next_field") == "total_value"
        assert "wallet balance" in str(res.data.get("speak_to_user")).lower()
        assert res.data.get("value_caps") is not None
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_thread_id(token)


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
        assert res.data.get("value_caps") is not None
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


def test_fill_create_restores_draft_after_failure_message():
    token = set_current_thread_id("test:create:restore-after-failure")
    msg_token = set_current_messages(
        [
            {
                "type": "assistant",
                "content": "Failed to create property: Property was saved but setup failed.",
            },
        ]
    )
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        tools._set_workflow_session(
            "CREATE_PROPERTY",
            {
                "submitting": True,
                "filled": _complete_filled(),
            },
        )
        res = asyncio.run(_fill_create_property({}, _owner(), None))
        assert res.ok
        assert res.data.get("awaiting_create_confirmation") is True
        assert (res.data.get("filled") or {}).get("name") == "Mega Estate"
        assert "did not succeed" in str(res.data.get("speak_to_user")).lower()
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_fill_create_retries_submit_after_failure_without_recollecting():
    token = set_current_thread_id("test:create:retry-after-failure")
    msg_token = set_current_messages(
        [
            {"type": "assistant", "content": "Failed to create property: setup failed."},
            {"type": "human", "content": "yes"},
        ]
    )
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        tools._set_workflow_session(
            "CREATE_PROPERTY",
            {
                "submitting": True,
                "filled": _complete_filled(),
            },
        )
        res = asyncio.run(_fill_create_property({"confirm_create": True}, _owner(), None))
        assert res.ok
        assert res.data.get("submitted") is True
        assert any(a.type == "SUBMIT_FORM" for a in res.actions)
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)
