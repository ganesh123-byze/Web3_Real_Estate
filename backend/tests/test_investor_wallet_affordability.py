"""Investor copilot: wallet-based whole-token affordability guidance."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import backend.ai.tools as tools
from backend.ai.investor_guards import extract_invest_property_hint_from_utterance, has_explicit_invest_intent
from backend.ai.investor_quick_actions import is_investor_advisory_intent
from backend.ai.investor_wallet_affordability import (
    compute_affordable_whole_tokens,
    extract_wallet_affordability_property_hint,
    format_investor_wallet_affordability_speak,
    has_investor_wallet_affordability_intent,
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


def _prop() -> dict:
    return {
        "id": 7,
        "name": "Gold Plaza",
        "location": "Mumbai",
        "token_symbol": "GP",
        "token_address": "0xabc",
        "tokens_available": "100",
        "token_sale_price_eth": "0.1",
    }


def test_wallet_affordability_intent_matches_user_phrase():
    prompt = (
        "Based on my wallet balance how many tokens should I buy in property Gold Plaza?"
    )
    assert has_investor_wallet_affordability_intent(prompt) is True


def test_wallet_affordability_is_advisory_not_invest_order():
    prompt = "Based on my wallet balance how many tokens should I buy in Gold Plaza?"
    assert is_investor_advisory_intent(prompt) is True
    assert has_explicit_invest_intent(prompt) is False
    assert extract_invest_property_hint_from_utterance(prompt) == ""


def test_explicit_buy_order_is_not_affordability_intent():
    assert has_investor_wallet_affordability_intent("Buy 5 tokens in Gold Plaza") is False


def test_extract_property_hint_from_affordability_question():
    hint = extract_wallet_affordability_property_hint(
        "How many tokens can I afford to buy in Gold Plaza with my wallet balance?"
    )
    assert hint == "Gold Plaza"


def test_compute_affordable_whole_tokens_floors_and_caps_supply():
    # 1 ETH balance, 0.1 ETH/token => 10 tokens; supply caps at 7
    balance_wei = 10**18
    price_wei = 10**17
    assert compute_affordable_whole_tokens(balance_wei, price_wei, tokens_available=7) == 7
    assert compute_affordable_whole_tokens(balance_wei, price_wei, tokens_available=100) == 10
    assert compute_affordable_whole_tokens(price_wei - 1, price_wei, tokens_available=100) == 0


def test_format_speak_mentions_whole_tokens_only():
    text = format_investor_wallet_affordability_speak(
        _prop(),
        affordable_tokens=5,
        balance_wei=10**18,
        sale_price_per_token_wei=10**17,
    )
    assert "5" in text
    assert "whole" in text.lower()
    assert "fractional" in text.lower()
    assert "Gold Plaza" in text


def test_wallet_affordability_preflight_returns_estimate():
    prop = _prop()
    with patch(
        "backend.ai.tools._latest_human_utterance",
        return_value="Based on my wallet balance how many tokens should I buy in Gold Plaza?",
    ), patch.object(tools, "_resolve_property_by_name", return_value=(prop, None)), patch(
        "backend.ai.tools.read_wallet_balance_wei",
        return_value=10**18,
    ), patch(
        "backend.ai.tools.read_property_sale_price_wei",
        return_value=10**17,
    ):
        result = asyncio.run(tools.try_server_investor_wallet_affordability(_investor(), None))

    assert result is not None
    assert result.ok
    assert result.data.get("affordable_whole_tokens") == 10
    assert result.data.get("whole_tokens_only") is True
    assert "whole" in str(result.data.get("speak_to_user")).lower()
    assert not any(a.type == "OPEN_MODAL" for a in (result.actions or []))


def test_wallet_affordability_preflight_asks_for_property_when_missing():
    with patch(
        "backend.ai.tools._latest_human_utterance",
        return_value="Based on my wallet balance how many tokens should I buy?",
    ):
        result = asyncio.run(tools.try_server_investor_wallet_affordability(_investor(), None))

    assert result is not None
    assert result.data.get("needs_property_name") is True
    assert "property name" in str(result.data.get("speak_to_user")).lower()
