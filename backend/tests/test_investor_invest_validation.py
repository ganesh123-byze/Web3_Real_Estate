"""Investor guided-invest token supply validation."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import backend.ai.tools as tools
from backend.ai.investor_invest_validation import (
    invest_exceeds_available_tokens_message,
    invest_token_amount_exceeds_available,
    read_property_tokens_available,
)
from backend.services.auth import AuthUser


def _prop(*, available: str = "99"):
    return {
        "id": 11,
        "name": "Brightcone",
        "location": "USA",
        "token_address": "0xabc",
        "tokens_available": available,
        "token_sale_price_eth": "0.1",
        "monthly_rent_eth": "0.1",
    }


def _investor() -> AuthUser:
    return AuthUser(
        id=2,
        wallet_address="0x0000000000000000000000000000000000000002",
        role="investor",
        email=None,
        kyc_status="verified",
        active=True,
    )


def test_read_property_tokens_available():
    assert read_property_tokens_available(_prop(available="99")) == 99
    assert read_property_tokens_available(_prop(available="0")) == 0


def test_exceeds_available_tokens_message():
    msg = invest_exceeds_available_tokens_message(150, _prop(available="99"))
    assert "Don't exceed the number of available tokens to invest" in msg
    assert "99 token" in msg
    assert "Brightcone" in msg
    assert invest_token_amount_exceeds_available(100, _prop(available="99")) is True
    assert invest_token_amount_exceeds_available(99, _prop(available="99")) is False
    assert invest_token_amount_exceeds_available(1, _prop(available="99")) is False


def test_fill_invest_rejects_token_count_above_available():
    token = tools.set_current_thread_id("test:invest:exceed-supply")
    msg_token = tools.set_current_messages(
        [
            {"type": "ai", "content": "How many tokens would you like to buy?"},
            {"type": "human", "content": "150"},
        ]
    )
    prop = _prop(available="99")
    try:
        tools._clear_workflow_session("INVEST_PROPERTY")
        tools._set_workflow_session(
            "INVEST_PROPERTY",
            {
                "in_progress": True,
                "filled": {
                    "property_name": "Brightcone",
                    "property_id": "11",
                },
                "next_field": "token_amount",
                "property_id": 11,
            },
        )
        with patch(
            "backend.ai.tools._resolve_property_by_name",
            lambda _db, _name, **kwargs: (prop, None),
        ), patch(
            "backend.ai.tools._load_invest_property_row",
            lambda _db, _pid: prop,
        ):
            result = asyncio.run(tools._fill_invest_property({}, _investor(), MagicMock()))
        speak = str(result.data.get("speak_to_user") or "")
        assert "Don't exceed the number of available tokens" in speak
        assert "99 token" in speak
        assert result.data.get("next_field") == "token_amount"
        assert not result.data.get("awaiting_invest_confirmation")
        assert result.data.get("filled", {}).get("token_amount") in (None, "")
    finally:
        tools._clear_workflow_session("INVEST_PROPERTY")
        tools.reset_current_messages(msg_token)
        tools.reset_current_thread_id(token)


def test_fill_invest_accepts_token_count_equal_to_available():
    token = tools.set_current_thread_id("test:invest:max-supply")
    msg_token = tools.set_current_messages(
        [
            {"type": "ai", "content": "How many tokens would you like to buy?"},
            {"type": "human", "content": "99"},
        ]
    )
    prop = _prop(available="99")
    try:
        tools._clear_workflow_session("INVEST_PROPERTY")
        tools._set_workflow_session(
            "INVEST_PROPERTY",
            {
                "in_progress": True,
                "filled": {
                    "property_name": "Brightcone",
                    "property_id": "11",
                },
                "next_field": "token_amount",
                "property_id": 11,
            },
        )
        with patch(
            "backend.ai.tools._resolve_property_by_name",
            lambda _db, _name, **kwargs: (prop, None),
        ), patch(
            "backend.ai.tools._load_invest_property_row",
            lambda _db, _pid: prop,
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
                token_amount=99,
            )
            result = asyncio.run(tools._fill_invest_property({}, _investor(), MagicMock()))
        assert result.data.get("awaiting_invest_confirmation") is True
        assert "Reply Yes" in str(result.data.get("speak_to_user") or "")
    finally:
        tools._clear_workflow_session("INVEST_PROPERTY")
        tools.reset_current_messages(msg_token)
        tools.reset_current_thread_id(token)
