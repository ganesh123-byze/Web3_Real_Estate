"""Investor copilot: explicit invest orders target one property, not the full catalog."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from backend.ai.investor_guards import (
    extract_invest_property_hint_from_utterance,
    extract_last_human_utterance,
    invest_utterance_has_negative_token_amount,
    format_invest_target_property_speak,
    has_explicit_invest_intent,
    has_investor_portfolio_intent,
    has_marketplace_browse_intent,
    invest_invalid_token_amount_message,
    invest_token_amount_field_is_valid,
    invest_turn_attempts_decimal_token_amount,
    invest_utterance_has_decimal_token_amount,
    invest_utterance_is_token_count_only,
    invest_utterance_names_property,
    is_generic_invest_phrase,
    parse_invest_order_from_utterance,
    parse_invest_token_amount,
    should_clear_stale_invest_token_amount,
    wants_to_begin_invest_workflow,
)
from backend.ai.tools import (
    _clear_workflow_session,
    _fill_invest_property,
    _set_workflow_session,
    reset_current_messages,
    reset_current_thread_id,
    set_current_messages,
    set_current_thread_id,
    try_server_invest_property_turn,
    try_server_investor_marketplace_browse,
)
from backend.services.auth import AuthUser


def _investor() -> AuthUser:
    return AuthUser(
        id=2,
        wallet_address="0x0000000000000000000000000000000000000002",
        role="investor",
        email=None,
        kyc_status="verified",
        active=True,
    )


def test_portfolio_phrase_is_not_invest_intent():
    utterance = "Show me my investment portfolio with current valuations."
    assert has_investor_portfolio_intent(utterance) is True
    assert has_explicit_invest_intent(utterance) is False


def test_extract_last_human_utterance_reads_api_chat_message_role():
    from backend.ai.schemas import ChatMessage

    assert extract_last_human_utterance([ChatMessage(role="user", content="invest")]) == "invest"
    assert extract_last_human_utterance(
        [
            ChatMessage(role="assistant", content="Hello"),
            ChatMessage(role="user", content="I want to invest"),
        ]
    ) == "I want to invest"


def test_bare_invest_preflight_with_chat_message_role():
    from backend.ai.schemas import ChatMessage

    token = set_current_thread_id("test:invest-chatmessage-preflight")
    msg_token = set_current_messages([ChatMessage(role="user", content="invest")])
    try:
        _clear_workflow_session("INVEST_PROPERTY")
        result = asyncio.run(try_server_invest_property_turn(_investor(), MagicMock()))
        assert result is not None
        speak = str(result.data.get("speak_to_user") or "")
        assert "Which property" in speak
        assert "Blocked" not in speak
    finally:
        _clear_workflow_session("INVEST_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_bare_invest_starts_guided_workflow():
    assert wants_to_begin_invest_workflow("invest") is True
    assert has_explicit_invest_intent("invest") is True
    assert is_generic_invest_phrase("invest") is True
    assert is_generic_invest_phrase("I want to invest") is True
    assert not invest_utterance_names_property("invest")
    assert not invest_utterance_names_property("I want to invest")
    assert extract_invest_property_hint_from_utterance("invest") == ""
    assert parse_invest_order_from_utterance("invest") == {}


def test_bare_invest_preflight_starts_workflow_not_property_resolution():
    token = set_current_thread_id("test:invest-bare-start")
    msg_token = set_current_messages([{"type": "human", "content": "invest"}])
    try:
        _clear_workflow_session("INVEST_PROPERTY")
        result = asyncio.run(try_server_invest_property_turn(_investor(), MagicMock()))
        assert result is not None
        speak = str(result.data.get("speak_to_user") or "")
        assert "Which property" in speak
        assert "No investable property found" not in speak
        assert result.data.get("next_field") == "property_name"
    finally:
        _clear_workflow_session("INVEST_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_i_want_to_invest_preflight_asks_for_property_name():
    token = set_current_thread_id("test:invest-i-want")
    msg_token = set_current_messages(
        [{"type": "human", "content": "I want to invest"}]
    )
    try:
        _clear_workflow_session("INVEST_PROPERTY")
        result = asyncio.run(try_server_invest_property_turn(_investor(), MagicMock()))
        assert result is not None
        speak = str(result.data.get("speak_to_user") or "")
        assert "Which property" in speak
        assert "No investable property found" not in speak
    finally:
        _clear_workflow_session("INVEST_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_guided_invest_full_flow_property_tokens_confirm():
    token = set_current_thread_id("test:invest-guided-flow")
    msg_token = set_current_messages([{"type": "human", "content": "invest"}])
    prop = {
        "id": 5,
        "name": "Gold Plaza",
        "location": "Hyderabad",
        "token_symbol": "GP",
        "token_address": "0xabc",
        "tokens_available": "100",
        "token_sale_price_eth": "1",
        "monthly_rent_eth": "0.5",
        "sold_percentage": "0",
        "token_supply": "500",
    }
    try:
        _clear_workflow_session("INVEST_PROPERTY")
        set_current_messages([{"type": "human", "content": "invest"}])
        with patch(
            "backend.ai.tools._resolve_property_by_name",
            return_value=(prop, None),
        ), patch(
            "backend.ai.tools.check_investor_can_fund_investment",
        ) as funding:
            from backend.services.investment_funding import InvestmentFundingCheck

            funding.return_value = InvestmentFundingCheck(
                ok=True,
                required_wei=1,
                balance_wei=10**18,
                required_eth="0",
                balance_eth="1",
                shortfall_wei=0,
                shortfall_eth="0",
                sale_price_per_token_wei=1,
                token_amount=3,
            )
            with patch(
                "backend.ai.tools._load_invest_property_row", return_value=prop
            ):
                start = asyncio.run(
                    try_server_invest_property_turn(_investor(), MagicMock())
                )
                assert "Which property" in str(start.data.get("speak_to_user") or "")

                set_current_messages(
                    [
                        {"type": "human", "content": "invest"},
                        {"type": "ai", "content": start.data.get("speak_to_user")},
                        {"type": "human", "content": "Gold Plaza"},
                    ]
                )
                named = asyncio.run(
                    try_server_invest_property_turn(_investor(), MagicMock())
                )
                speak_named = str(named.data.get("speak_to_user") or "")
                assert "How many tokens" in speak_named
                assert "Gold Plaza" in speak_named
                assert named.data.get("next_field") == "token_amount"

                set_current_messages(
                    [
                        {"type": "human", "content": "invest"},
                        {"type": "ai", "content": start.data.get("speak_to_user")},
                        {"type": "human", "content": "Gold Plaza"},
                        {"type": "ai", "content": speak_named},
                        {"type": "human", "content": "3"},
                    ]
                )
                confirm = asyncio.run(
                    try_server_invest_property_turn(_investor(), MagicMock())
                )
                speak_confirm = str(confirm.data.get("speak_to_user") or "")
                assert confirm.data.get("awaiting_invest_confirmation") is True
                assert "Reply Yes" in speak_confirm
                assert "Investment summary" in speak_confirm

                set_current_messages(
                    [
                        {"type": "human", "content": "invest"},
                        {"type": "ai", "content": start.data.get("speak_to_user")},
                        {"type": "human", "content": "Gold Plaza"},
                        {"type": "ai", "content": speak_named},
                        {"type": "human", "content": "3"},
                        {"type": "ai", "content": speak_confirm},
                        {"type": "human", "content": "No"},
                    ]
                )
                cancelled = asyncio.run(
                    try_server_invest_property_turn(_investor(), MagicMock())
                )
                assert "cancelled" in str(
                    cancelled.data.get("speak_to_user") or ""
                ).lower()
    finally:
        _clear_workflow_session("INVEST_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_parse_invest_one_token_in_property():
    parsed = parse_invest_order_from_utterance("Invest 1 token in Gold Plaza")
    assert parsed.get("token_amount") == "1"
    assert parsed.get("property_name") == "Gold Plaza"


def test_negative_token_amounts_are_rejected_not_property_names():
    assert invest_utterance_has_negative_token_amount("-1") is True
    assert invest_utterance_has_negative_token_amount("-5 tokens") is True
    assert parse_invest_order_from_utterance("-1") == {}
    assert parse_invest_token_amount("-5 tokens") is None
    assert extract_invest_property_hint_from_utterance("-1") == ""
    assert not invest_utterance_names_property("-1")
    msg = invest_invalid_token_amount_message("-1", reason="negative")
    assert "negative" in msg.lower()
    assert "1 or greater" in msg.lower()


def test_fill_invest_rejects_negative_token_answer():
    token = set_current_thread_id("test:invest-negative-token")
    msg_token = set_current_messages(
        [
            {"type": "ai", "content": "How many tokens would you like to buy?"},
            {"type": "human", "content": "-1"},
        ]
    )
    prop = {
        "id": 9,
        "name": "sky view towers",
        "token_address": "0xabc",
        "tokens_available": "100",
        "token_sale_price_eth": "0.2",
        "sold_percentage": "0",
    }
    try:
        _clear_workflow_session("INVEST_PROPERTY")
        _set_workflow_session(
            "INVEST_PROPERTY",
            {
                "in_progress": True,
                "filled": {
                    "property_name": "sky view towers",
                    "property_id": "9",
                },
                "next_field": "token_amount",
                "property_id": 9,
            },
        )
        with patch(
            "backend.ai.tools._resolve_property_by_name",
            return_value=(prop, None),
        ):
            result = asyncio.run(_fill_invest_property({}, _investor(), MagicMock()))
        speak = str(result.data.get("speak_to_user") or "")
        assert "negative" in speak.lower()
        assert "No investable property found" not in speak
        assert result.data.get("next_field") == "token_amount"
        assert result.data.get("filled", {}).get("token_amount") in (None, "")
    finally:
        _clear_workflow_session("INVEST_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_decimal_token_amounts_are_rejected_not_truncated():
    assert invest_utterance_has_decimal_token_amount("0.1 token") is True
    assert invest_utterance_has_decimal_token_amount("1.5 tokens") is True
    assert invest_utterance_has_decimal_token_amount(
        "invest 0.1 token in Gold Plaza"
    ) is True
    assert parse_invest_token_amount("0.1 token") is None
    assert parse_invest_token_amount("1.5 tokens") is None
    assert parse_invest_order_from_utterance("invest 0.1 token in Gold Plaza") == {
        "property_name": "Gold Plaza",
    }
    assert parse_invest_order_from_utterance("1.5 tokens") == {}
    assert not invest_token_amount_field_is_valid("0.1")
    assert not invest_token_amount_field_is_valid("1.5")
    assert invest_token_amount_field_is_valid("5")
    msg = invest_invalid_token_amount_message("0.1")
    assert "decimal" in msg.lower()
    assert "whole numbers" in msg.lower()
    assert "not decimals" in msg.lower()


def test_fill_invest_rejects_decimal_token_answer():
    token = set_current_thread_id("test:invest-decimal-token")
    msg_token = set_current_messages(
        [
            {"type": "ai", "content": "How many tokens would you like to buy?"},
            {"type": "human", "content": "0.1"},
        ]
    )
    prop = {
        "id": 5,
        "name": "Gold Plaza",
        "token_address": "0xabc",
        "tokens_available": "100",
        "token_sale_price_eth": "1",
        "sold_percentage": "0",
    }
    try:
        _clear_workflow_session("INVEST_PROPERTY")
        _set_workflow_session(
            "INVEST_PROPERTY",
            {
                "in_progress": True,
                "filled": {
                    "property_name": "Gold Plaza",
                    "property_id": "5",
                },
                "next_field": "token_amount",
                "property_id": 5,
            },
        )
        with patch(
            "backend.ai.tools._resolve_property_by_name",
            return_value=(prop, None),
        ):
            result = asyncio.run(_fill_invest_property({}, _investor(), MagicMock()))
        speak = str(result.data.get("speak_to_user") or "")
        assert "decimal" in speak.lower()
        assert "whole numbers" in speak.lower()
        assert result.data.get("next_field") == "token_amount"
        assert result.data.get("filled", {}).get("token_amount") in (None, "")
        assert not result.data.get("awaiting_invest_confirmation")
    finally:
        _clear_workflow_session("INVEST_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_preflight_rejects_decimal_token_in_one_shot_order():
    token = set_current_thread_id("test:invest-decimal-one-shot")
    msg_token = set_current_messages(
        [{"type": "human", "content": "invest 0.1 token in Gold Plaza"}]
    )
    prop = {
        "id": 5,
        "name": "Gold Plaza",
        "token_address": "0xabc",
        "tokens_available": "100",
        "token_sale_price_eth": "1",
        "sold_percentage": "0",
    }
    try:
        _clear_workflow_session("INVEST_PROPERTY")
        assert invest_turn_attempts_decimal_token_amount(
            "invest 0.1 token in Gold Plaza"
        ) is True
        with patch(
            "backend.ai.tools._resolve_property_by_name",
            return_value=(prop, None),
        ):
            result = asyncio.run(
                try_server_invest_property_turn(_investor(), MagicMock())
            )
        assert result is not None
        speak = str(result.data.get("speak_to_user") or "")
        assert "decimal" in speak.lower()
        assert result.data.get("next_field") == "token_amount"
        assert result.data.get("filled", {}).get("token_amount") not in ("1", "0")
    finally:
        _clear_workflow_session("INVEST_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_bare_digit_is_token_count_not_property_id():
    assert invest_utterance_is_token_count_only("1") is True
    assert parse_invest_order_from_utterance("1") == {"token_amount": "1"}
    assert should_clear_stale_invest_token_amount("1") is False


def test_property_id_only_should_clear_stale_token():
    assert should_clear_stale_invest_token_amount("Invest in #12") is True
    assert should_clear_stale_invest_token_amount("Invest 3 tokens in #12") is False
    assert should_clear_stale_invest_token_amount("Invest 1 token in Gold Plaza") is False


def test_token_only_reply_keeps_property_and_submits():
    token = set_current_thread_id("test:invest-token-only-submit")
    msg_token = set_current_messages(
        [
            {"type": "human", "content": "Invest in #7"},
            {"type": "ai", "content": "How many tokens would you like to buy?"},
            {"type": "human", "content": "1"},
        ]
    )
    prop = {
        "id": 7,
        "name": "Burj Vista Residences",
        "token_address": "0xabc",
        "tokens_available": "100",
        "token_sale_price_eth": "0.1",
        "monthly_rent_eth": "0.01",
        "sold_percentage": "1",
        "token_supply": "500",
    }
    try:
        _clear_workflow_session("INVEST_PROPERTY")
        _set_workflow_session(
            "INVEST_PROPERTY",
            {
                "in_progress": True,
                "submitted": False,
                "filled": {
                    "property_name": "Burj Vista Residences",
                    "property_id": "7",
                },
                "next_field": "token_amount",
                "property_id": 7,
            },
        )
        with patch(
            "backend.ai.tools._resolve_property_by_name",
            return_value=(prop, None),
        ), patch(
            "backend.ai.tools.check_investor_can_fund_investment",
        ) as funding:
            from backend.services.investment_funding import InvestmentFundingCheck

            funding.return_value = InvestmentFundingCheck(
                ok=True,
                required_wei=1,
                balance_wei=10**18,
                required_eth="0",
                balance_eth="1",
                shortfall_wei=0,
                shortfall_eth="0",
                sale_price_per_token_wei=1,
                token_amount=1,
            )
            with patch("backend.ai.tools._load_invest_property_row", return_value=prop):
                result = asyncio.run(_fill_invest_property({}, _investor(), MagicMock()))
        assert result.data.get("property_id") == 7
        assert result.data.get("awaiting_invest_confirmation") is True
        assert result.data.get("submitted") is False
        assert result.data.get("filled", {}).get("token_amount") == "1"
        assert "Reply Yes" in str(result.data.get("speak_to_user") or "")
        assert "How many tokens" not in str(result.data.get("speak_to_user") or "")
    finally:
        _clear_workflow_session("INVEST_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_invest_property_id_asks_for_token_count_not_previous_amount():
    token = set_current_thread_id("test:invest-hash-id-only")
    msg_token = set_current_messages(
        [{"type": "human", "content": "Invest in property #7"}]
    )
    prop = {
        "id": 7,
        "name": "Burj Vista Residences",
        "token_address": "0xabc",
        "tokens_available": "100",
        "token_sale_price_eth": "1",
        "sold_percentage": "0",
    }
    try:
        _clear_workflow_session("INVEST_PROPERTY")
        _set_workflow_session(
            "INVEST_PROPERTY",
            {
                "in_progress": True,
                "submitted": False,
                "filled": {
                    "property_name": "Old Tower",
                    "token_amount": "9",
                    "property_id": "3",
                },
                "next_field": "token_amount",
                "property_id": 3,
            },
        )
        with patch(
            "backend.ai.tools._resolve_property_by_name",
            return_value=(prop, None),
        ):
            result = asyncio.run(_fill_invest_property({}, _investor(), MagicMock()))
        assert result.data.get("submitted") is False
        assert result.data.get("next_field") == "token_amount"
        assert "token_amount" in (result.data.get("missing") or [])
        speak = str(result.data.get("speak_to_user") or "")
        assert "How many tokens" in speak
        assert "Burj Vista" in speak
        assert "Investment summary" in speak
        assert "How many tokens" in speak
        assert "MetaMask" not in speak
        assert result.data.get("filled", {}).get("token_amount") in (None, "")
    finally:
        _clear_workflow_session("INVEST_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_parse_invest_spoken_one_token_voice():
    parsed = parse_invest_order_from_utterance(
        "invest one token in skyview residency"
    )
    assert parsed.get("token_amount") == "1"
    assert "skyview" in (parsed.get("property_name") or "").lower()
    assert has_explicit_invest_intent("invest one token in skyview residency") is True


def test_preflight_insufficient_funds_verbatim_message():
    token = set_current_thread_id("test:invest-insufficient")
    msg_token = set_current_messages(
        [{"type": "human", "content": "Invest 1 token in Skyview Residency"}]
    )
    prop = {
        "id": 9,
        "name": "Skyview Residency",
        "token_address": "0xabc",
        "tokens_available": "50",
        "token_sale_price_wei": str(10**18),
        "token_sale_price_eth": "1",
        "sold_percentage": "0",
    }
    try:
        _clear_workflow_session("INVEST_PROPERTY")
        from backend.services.investment_funding import InvestmentFundingCheck

        shortfall = 9 * 10**17
        funding = InvestmentFundingCheck(
            ok=False,
            required_wei=10**18,
            balance_wei=10**17,
            required_eth="1.0",
            balance_eth="0.1",
            shortfall_wei=shortfall,
            shortfall_eth="0.9",
            sale_price_per_token_wei=10**18,
            token_amount=1,
            speak_to_user=(
                "You have insufficient funds in your account. "
                "Buying 1 token(s) in Skyview Residency requires 1.0 ETH, "
                "but your wallet balance is 0.1 ETH (about 0.9 ETH short). "
                "Add ETH to your wallet or reduce the number of tokens, then try again."
            ),
            instruction="Do not open MetaMask.",
        )
        with patch(
            "backend.ai.tools._resolve_property_by_name",
            return_value=(prop, None),
        ), patch(
            "backend.ai.tools.check_investor_can_fund_investment",
            return_value=funding,
        ), patch(
            "backend.ai.tools._load_invest_property_row",
            return_value=prop,
        ):
            invest = asyncio.run(try_server_invest_property_turn(_investor(), MagicMock()))
        assert invest is not None
        assert invest.data.get("awaiting_invest_confirmation") is True
        set_current_messages(
            [
                {"type": "human", "content": "Invest 1 token in Skyview Residency"},
                {"type": "ai", "content": invest.data.get("speak_to_user")},
                {"type": "human", "content": "Yes"},
            ]
        )
        with patch(
            "backend.ai.tools._resolve_property_by_name",
            return_value=(prop, None),
        ), patch(
            "backend.ai.tools.check_investor_can_fund_investment",
            return_value=funding,
        ), patch(
            "backend.ai.tools._load_invest_property_row",
            return_value=prop,
        ):
            confirmed = asyncio.run(try_server_invest_property_turn(_investor(), MagicMock()))
        assert confirmed is not None
        assert confirmed.data.get("insufficient_funds") is True
        speak = str(confirmed.data.get("speak_to_user") or "")
        assert "insufficient funds" in speak.lower()
        assert "Skyview Residency" in speak
        assert confirmed.data.get("speak_verbatim") is True
        assert "Here are the properties open for investment" not in speak
    finally:
        _clear_workflow_session("INVEST_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_marketplace_browse_not_triggered_for_explicit_invest():
    utterance = "Invest 10 tokens into Oceanview Apartments"
    assert has_marketplace_browse_intent(utterance) is False


def test_format_invest_target_is_single_property_not_catalog():
    text = format_invest_target_property_speak(
        {
            "id": 5,
            "name": "Gold Plaza",
            "location": "Hyderabad",
            "token_symbol": "GP",
            "sold_percentage": "12",
            "tokens_available": "900",
            "token_sale_price_eth": "0.5",
            "monthly_rent_eth": "1",
        },
        token_amount=1,
    )
    assert "Investment summary" in text
    assert "Property name: Gold Plaza (#5)" in text
    assert "Location: Hyderabad" in text
    assert "Tokens available: 900" in text
    assert "Price per token: 0.5 ETH" in text
    assert "Monthly rent: 1 ETH" in text
    assert "Avg. rental yield:" not in text
    assert "Order size: 1 token" in text
    assert "Here are the properties open for investment" not in text


def test_preflight_invest_order_not_marketplace_catalog():
    token = set_current_thread_id("test:invest-preflight-single")
    msg_token = set_current_messages(
        [{"type": "human", "content": "Invest 1 token in Gold Plaza"}]
    )
    prop = {
        "id": 5,
        "name": "Gold Plaza",
        "location": "Hyderabad",
        "token_symbol": "GP",
        "token_address": "0xabc",
        "tokens_available": "100",
        "token_sale_price_eth": "1",
        "sold_percentage": "0",
    }
    try:
        _clear_workflow_session("INVEST_PROPERTY")
        with patch(
            "backend.ai.tools._resolve_property_by_name",
            return_value=(prop, None),
        ), patch(
            "backend.ai.tools.check_investor_can_fund_investment",
        ) as funding:
            from backend.services.investment_funding import InvestmentFundingCheck

            funding.return_value = InvestmentFundingCheck(
                ok=True,
                required_wei=1,
                balance_wei=10**18,
                required_eth="0",
                balance_eth="1",
                shortfall_wei=0,
                shortfall_eth="0",
                sale_price_per_token_wei=1,
                token_amount=1,
            )
            funding_patch = patch(
                "backend.ai.tools._load_invest_property_row",
                return_value=prop,
            )
            with funding_patch:
                browse = asyncio.run(try_server_investor_marketplace_browse(_investor(), None))
                invest = asyncio.run(try_server_invest_property_turn(_investor(), MagicMock()))
        assert browse is None
        assert invest is not None
        speak = str(invest.data.get("speak_to_user") or "")
        assert "Gold Plaza" in speak
        assert "Here are the properties open for investment" not in speak
        assert invest.data.get("invest_property_target") is True
    finally:
        _clear_workflow_session("INVEST_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_voice_bare_invest_strips_trailing_punctuation():
    assert is_generic_invest_phrase("Invest.") is True
    assert wants_to_begin_invest_workflow("I want to invest.") is True
    assert not invest_utterance_names_property("Invest.")


def test_voice_bare_invest_preflight_on_voice_thread():
    from backend.ai.schemas import ChatMessage

    token = set_current_thread_id("voice:0x0000000000000000000000000000000000000002")
    msg_token = set_current_messages([ChatMessage(role="user", content="Invest.")])
    try:
        _clear_workflow_session("INVEST_PROPERTY")
        result = asyncio.run(try_server_invest_property_turn(_investor(), MagicMock()))
        assert result is not None
        speak = str(result.data.get("speak_to_user") or "")
        assert "Which property" in speak
        assert "Blocked" not in speak
        assert result.data.get("next_field") == "property_name"
    finally:
        _clear_workflow_session("INVEST_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_voice_spoken_decimal_token_amounts_are_rejected():
    assert invest_utterance_has_decimal_token_amount("zero point one token") is True
    assert invest_utterance_has_decimal_token_amount(
        "invest one point five tokens in Gold Plaza"
    ) is True
    assert invest_turn_attempts_decimal_token_amount(
        "zero point one",
        next_field="token_amount",
    ) is True
    assert parse_invest_token_amount("one point five tokens") is None


def test_voice_spoken_negative_token_amounts_are_rejected():
    assert invest_utterance_has_negative_token_amount("minus one token") is True
    assert invest_utterance_has_negative_token_amount("negative five") is True
    assert parse_invest_order_from_utterance("minus one") == {}
    assert extract_invest_property_hint_from_utterance("negative one") == ""


def test_fill_invest_rejects_voice_spoken_decimal_token_answer():
    token = set_current_thread_id("voice:invest-spoken-decimal")
    msg_token = set_current_messages(
        [
            {"type": "ai", "content": "How many tokens would you like to buy?"},
            {"type": "human", "content": "zero point one"},
        ]
    )
    prop = {
        "id": 9,
        "name": "sky view towers",
        "token_address": "0xabc",
        "tokens_available": "100",
        "token_sale_price_eth": "0.2",
        "sold_percentage": "0",
    }
    try:
        _clear_workflow_session("INVEST_PROPERTY")
        _set_workflow_session(
            "INVEST_PROPERTY",
            {
                "in_progress": True,
                "filled": {
                    "property_name": "sky view towers",
                    "property_id": "9",
                },
                "next_field": "token_amount",
                "property_id": 9,
            },
        )
        with patch(
            "backend.ai.tools._resolve_property_by_name",
            return_value=(prop, None),
        ):
            result = asyncio.run(_fill_invest_property({}, _investor(), MagicMock()))
        speak = str(result.data.get("speak_to_user") or "")
        assert "decimal" in speak.lower()
        assert result.data.get("speak_verbatim") is True
        assert result.data.get("next_field") == "token_amount"
    finally:
        _clear_workflow_session("INVEST_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_fill_invest_rejects_voice_spoken_negative_token_answer():
    token = set_current_thread_id("voice:invest-spoken-negative")
    msg_token = set_current_messages(
        [
            {"type": "ai", "content": "How many tokens would you like to buy?"},
            {"type": "human", "content": "minus one"},
        ]
    )
    prop = {
        "id": 9,
        "name": "sky view towers",
        "token_address": "0xabc",
        "tokens_available": "100",
        "token_sale_price_eth": "0.2",
        "sold_percentage": "0",
    }
    try:
        _clear_workflow_session("INVEST_PROPERTY")
        _set_workflow_session(
            "INVEST_PROPERTY",
            {
                "in_progress": True,
                "filled": {
                    "property_name": "sky view towers",
                    "property_id": "9",
                },
                "next_field": "token_amount",
                "property_id": 9,
            },
        )
        with patch(
            "backend.ai.tools._resolve_property_by_name",
            return_value=(prop, None),
        ):
            result = asyncio.run(_fill_invest_property({}, _investor(), MagicMock()))
        speak = str(result.data.get("speak_to_user") or "")
        assert "negative" in speak.lower()
        assert "No investable property found" not in speak
        assert result.data.get("speak_verbatim") is True
    finally:
        _clear_workflow_session("INVEST_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)
