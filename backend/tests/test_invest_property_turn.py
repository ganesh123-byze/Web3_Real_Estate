"""Investor copilot: explicit invest orders target one property, not the full catalog."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from backend.ai.investor_guards import (
    format_invest_target_property_speak,
    has_explicit_invest_intent,
    has_marketplace_browse_intent,
    parse_invest_order_from_utterance,
)
from backend.ai.tools import (
    _clear_workflow_session,
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


def test_parse_invest_one_token_in_property():
    parsed = parse_invest_order_from_utterance("Invest 1 token in Gold Plaza")
    assert parsed.get("token_amount") == "1"
    assert parsed.get("property_name") == "Gold Plaza"


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
        assert invest.data.get("insufficient_funds") is True
        speak = str(invest.data.get("speak_to_user") or "")
        assert "insufficient funds" in speak.lower()
        assert "Skyview Residency" in speak
        assert invest.data.get("speak_verbatim") is True
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
    assert "Investment target: Gold Plaza" in text
    assert "Order: 1 token" in text
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
