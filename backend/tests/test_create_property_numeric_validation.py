"""Create-property copilot rejects non-numeric value, supply, and rent answers."""
from __future__ import annotations

import asyncio

from backend.ai.tools import (
    _clear_workflow_session,
    _fill_create_property,
    reset_current_messages,
    reset_current_thread_id,
    set_current_messages,
    set_current_thread_id,
    try_server_apply_create_property_field_answer,
)
from backend.ai.workflow_parsers import (
    create_property_field_collection_speak,
    create_property_invalid_field_message,
    create_property_numeric_field_is_valid,
    create_property_token_symbol_is_valid,
    normalize_create_property_field,
    sanitize_create_property_fields,
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


def test_normalize_rejects_non_numeric_total_value_and_supply():
    assert normalize_create_property_field("total_value", "nc") == ""
    assert normalize_create_property_field("token_supply", ";snm") == ""
    assert normalize_create_property_field("monthly_rent_eth", "wo") == ""
    assert normalize_create_property_field("total_value", "10000") == "10000"
    assert normalize_create_property_field("token_supply", "100000") == "100000"
    assert normalize_create_property_field("monthly_rent_eth", "0.1") == "0.1"
    assert normalize_create_property_field("monthly_rent_eth", "skip") == "0"


def test_normalize_rejects_negative_total_value_and_supply():
    assert normalize_create_property_field("total_value", "-100") == ""
    assert normalize_create_property_field("total_value", "negative 50") == ""
    assert normalize_create_property_field("token_supply", "-500") == ""
    assert normalize_create_property_field("token_supply", "- 1000") == ""
    assert normalize_create_property_field("total_value", "\u2212100") == ""
    assert normalize_create_property_field("token_supply", "minus 25") == ""


def test_invalid_field_message_mentions_positive_only():
    msg = create_property_invalid_field_message("total_value", "-50")
    assert "positive" in msg.lower()
    msg_supply = create_property_invalid_field_message("token_supply", "-10")
    assert "positive" in msg_supply.lower()


def test_token_symbol_requires_two_to_ten_chars():
    assert normalize_create_property_field("token_symbol", "ETH") == "ETH"
    assert normalize_create_property_field("token_symbol", "A") == ""
    assert normalize_create_property_field("token_symbol", "abcdefghijk") == ""
    assert create_property_token_symbol_is_valid("GP")
    assert not create_property_token_symbol_is_valid("x")


def test_field_collection_speak_covers_full_flow():
    assert "name" in (create_property_field_collection_speak("name") or "").lower()
    assert "located" in (create_property_field_collection_speak("location") or "").lower()
    assert "total property value" in (create_property_field_collection_speak("total_value") or "").lower()
    assert "tokens" in (create_property_field_collection_speak("token_supply") or "").lower()
    assert "ticker" in (create_property_field_collection_speak("token_symbol", {"name": "Gold"}) or "").lower()
    assert "100 ETH" in (create_property_field_collection_speak("monthly_rent_eth") or "")


def test_sanitize_drops_invalid_numeric_fields():
    cleaned, invalid = sanitize_create_property_fields(
        {
            "name": "hoona",
            "total_value": "nc",
            "token_supply": "100",
        }
    )
    assert invalid == "total_value"
    assert "total_value" not in cleaned
    assert cleaned["token_supply"] == "100"


def test_fill_create_rejects_invalid_total_value_answer():
    token = set_current_thread_id("test:create:invalid-total-value")
    msg_token = set_current_messages(
        [
            {"type": "ai", "content": "What's the total property value in ETH?"},
            {"type": "human", "content": "nc"},
        ]
    )
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        tools_session = {
            "in_progress": True,
            "filled": {"name": "hoona", "location": "nlcnac"},
            "next_field": "total_value",
        }
        from backend.ai import tools

        tools._set_workflow_session("CREATE_PROPERTY", tools_session)
        result = asyncio.run(_fill_create_property({}, _owner(), None))
        assert result.ok
        assert result.data.get("next_field") == "total_value"
        assert "total_value" not in (result.data.get("filled") or {})
        speak = str(result.data.get("speak_to_user") or "").lower()
        assert "valid" in speak or "number" in speak
        assert "nc" in speak
        assert not result.data.get("awaiting_create_confirmation")
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_numeric_field_validator_accepts_spoken_amounts():
    assert create_property_numeric_field_is_valid("total_value", "one lakh")
    assert create_property_numeric_field_is_valid("token_supply", "100,000")
    assert create_property_numeric_field_is_valid("monthly_rent_eth", "no")


def test_large_total_value_accepted_and_advances():
    assert normalize_create_property_field("total_value", "12345678") == "12345678"
    token = set_current_thread_id("test:create:large-total-value")
    msg_token = set_current_messages(
        [
            {"type": "ai", "content": "What's the total property value in ETH?"},
            {"type": "human", "content": "12345678"},
        ]
    )
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        from backend.ai import tools

        tools._set_workflow_session(
            "CREATE_PROPERTY",
            {
                "in_progress": True,
                "filled": {"name": "sadf", "location": "sdsfd"},
                "next_field": "total_value",
            },
        )
        result = asyncio.run(try_server_apply_create_property_field_answer(_owner(), None))
        assert result is not None
        assert result.data.get("filled", {}).get("total_value") == "12345678"
        assert result.data.get("next_field") == "token_supply"
        speak = str(result.data.get("speak_to_user") or "").lower()
        assert "reasonable" not in speak
        assert "wallet" not in speak
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)
