"""Create-property copilot: recover fields from LLM summaries and avoid ticker re-asks."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

from backend.ai.tools import (
    _backfill_create_property_filled_from_history,
    _clear_workflow_session,
    _fill_create_property,
    reset_current_messages,
    reset_current_thread_id,
    set_current_messages,
    set_current_thread_id,
)
from backend.ai.workflow_parsers import (
    assistant_prompted_for_create_field,
    assistant_showed_create_property_summary,
    parse_create_property_fields_from_summary,
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


def test_parse_fields_from_paraphrased_summary():
    text = (
        "Here's a summary of the property details:\n\n"
        "- Name: Gold Plaza\n"
        "- Location: Mumbai\n"
        "- Total Value: 10000 ETH\n"
        "- Token Supply: 100000\n"
        "- Token Symbol: GLD\n"
        "- Monthly Rent: 0.1 ETH\n\n"
        "Shall I go ahead and create this property?"
    )
    assert assistant_showed_create_property_summary(text)
    fields = parse_create_property_fields_from_summary(text)
    assert fields["name"] == "Gold Plaza"
    assert fields["token_symbol"] == "GLD"
    assert fields["monthly_rent_eth"] == "0.1"


def test_short_ticker_prompt_matches_token_symbol_field():
    assert assistant_prompted_for_create_field(
        'Please provide a short ticker for the token, like "GOLD" or "ETH."',
        "token_symbol",
    )


def test_backfill_recovers_gld_from_summary_when_session_empty():
    summary = (
        "Here's a summary of the property details:\n\n"
        "- Name: Gold Plaza\n"
        "- Location: Mumbai\n"
        "- Total Value: 10000 ETH\n"
        "- Token Supply: 100000\n"
        "- Token Symbol: GLD\n"
        "- Monthly Rent: 0.1 ETH\n\n"
        "Shall I go ahead and create this property?"
    )
    token = set_current_thread_id("test:create:summary-backfill")
    msg_token = set_current_messages(
        [
            {"type": "ai", "content": "Please provide a short ticker for the token."},
            {"type": "human", "content": "GLD"},
            {"type": "ai", "content": summary},
            {"type": "human", "content": "yes"},
        ]
    )
    try:
        filled = _backfill_create_property_filled_from_history({})
        assert filled.get("token_symbol") == "GLD"
        assert filled.get("name") == "Gold Plaza"
    finally:
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_yes_after_paraphrased_summary_submits_without_reasking_ticker():
    summary = (
        "Here's a summary of the property details:\n\n"
        "- Name: Gold Plaza\n"
        "- Location: Mumbai\n"
        "- Total Value: 10000 ETH\n"
        "- Token Supply: 100000\n"
        "- Token Symbol: GLD\n"
        "- Monthly Rent: 0.1 ETH\n\n"
        "Shall I go ahead and create this property?"
    )
    token = set_current_thread_id("test:create:yes-after-summary")
    msg_token = set_current_messages(
        [
            {"type": "ai", "content": summary},
            {"type": "human", "content": "yes"},
        ]
    )
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        with patch(
            "backend.ai.tools.create_property_record",
            return_value={
                "id": 99,
                "name": "Gold Plaza",
                "token_address": "0xabc",
            },
        ):
            result = asyncio.run(_fill_create_property({}, _owner(), None))
        assert result.ok
        assert result.data.get("submitted") is True
        assert result.data.get("next_field") is None
        speak = str(result.data.get("speak_to_user") or "").lower()
        assert "ticker symbol" not in speak
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)
