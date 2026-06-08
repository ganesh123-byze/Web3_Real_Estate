"""End-to-end investor guided-invest workflow (marketplace → property → tokens → MetaMask)."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from backend.ai.investor_invest_flow import INVEST_PROPERTY_ASK, INVEST_TOKEN_ASK
from backend.ai.investor_marketplace import format_investor_marketplace_catalog_speak
from backend.ai.tools import (
    _clear_workflow_session,
    reset_current_messages,
    reset_current_thread_id,
    set_current_messages,
    set_current_thread_id,
    try_server_investor_marketplace_browse,
    try_server_invest_property_turn,
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


def _gold_plaza_prop():
    return {
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


def test_invest_property_ask_mentions_name_or_id():
    assert "name or #id" in INVEST_PROPERTY_ASK.lower()
    assert "how many tokens" in INVEST_TOKEN_ASK.lower()


def test_marketplace_quick_action_returns_investable_catalog():
    token = set_current_thread_id("test:flow:marketplace-qa")
    prompt = "Take me to the marketplace and show me available properties to invest in."
    msg_token = set_current_messages(
        [
            {
                "type": "human",
                "content": prompt,
                "quick_action_id": "investor.marketplace",
            }
        ]
    )
    db = MagicMock()
    items = [_gold_plaza_prop()]
    try:
        _clear_workflow_session("INVEST_PROPERTY")
        with patch("backend.ai.tools._list_properties", return_value=items):
            result = asyncio.run(try_server_investor_marketplace_browse(_investor(), db))
        assert result is not None
        speak = str(result.data.get("speak_to_user") or "")
        assert "Gold Plaza" in speak
        assert result.data.get("marketplace_catalog") is True
        assert any(
            a.type == "NAVIGATE" and a.route == "/investor/marketplace"
            for a in result.actions
        )
    finally:
        _clear_workflow_session("INVEST_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_bare_invest_asks_for_property_name_or_id():
    token = set_current_thread_id("test:flow:bare-invest")
    msg_token = set_current_messages([{"type": "human", "content": "I want to invest"}])
    try:
        _clear_workflow_session("INVEST_PROPERTY")
        result = asyncio.run(try_server_invest_property_turn(_investor(), MagicMock()))
        assert result is not None
        speak = str(result.data.get("speak_to_user") or "")
        assert INVEST_PROPERTY_ASK.split(".")[0] in speak or "name or #id" in speak.lower()
        assert result.data.get("next_field") == "property_name"
    finally:
        _clear_workflow_session("INVEST_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_unknown_property_id_is_rejected_with_clear_message():
    token = set_current_thread_id("test:flow:unknown-id")
    msg_token = set_current_messages(
        [
            {"type": "human", "content": "invest"},
            {"type": "ai", "content": INVEST_PROPERTY_ASK},
            {"type": "human", "content": "#999"},
        ]
    )
    prop = _gold_plaza_prop()
    try:
        _clear_workflow_session("INVEST_PROPERTY")
        with patch(
            "backend.ai.tools._resolve_property_by_name",
            return_value=(None, "No investable property found with id #999."),
        ), patch("backend.ai.tools._load_invest_property_row", return_value=prop):
            result = asyncio.run(try_server_invest_property_turn(_investor(), MagicMock()))
        assert result is not None
        speak = str(result.data.get("speak_to_user") or "")
        assert "#999" in speak
        assert "No investable property found" in speak
        assert result.data.get("next_field") == "property_name"
    finally:
        _clear_workflow_session("INVEST_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_full_invest_flow_through_metamask_submit():
    token = set_current_thread_id("test:flow:full-yes-submit")
    prop = _gold_plaza_prop()
    start_speak = INVEST_PROPERTY_ASK
    try:
        _clear_workflow_session("INVEST_PROPERTY")

        set_current_messages([{"type": "human", "content": "invest"}])
        with patch(
            "backend.ai.tools._resolve_property_by_name",
            return_value=(prop, None),
        ), patch("backend.ai.tools.check_investor_can_fund_investment") as funding:
            from backend.services.investment_funding import InvestmentFundingCheck

            funding.return_value = InvestmentFundingCheck(
                ok=True,
                required_wei=3 * 10**18,
                balance_wei=10**19,
                required_eth="3",
                balance_eth="10",
                shortfall_wei=0,
                shortfall_eth="0",
                sale_price_per_token_wei=10**18,
                token_amount=3,
            )
            with patch("backend.ai.tools._load_invest_property_row", return_value=prop):
                start = asyncio.run(
                    try_server_invest_property_turn(_investor(), MagicMock())
                )
                assert "name or #id" in str(start.data.get("speak_to_user") or "").lower()

                set_current_messages(
                    [
                        {"type": "human", "content": "invest"},
                        {"type": "ai", "content": start_speak},
                        {"type": "human", "content": "Gold Plaza"},
                    ]
                )
                named = asyncio.run(
                    try_server_invest_property_turn(_investor(), MagicMock())
                )
                assert INVEST_TOKEN_ASK in str(named.data.get("speak_to_user") or "")
                assert "Gold Plaza" in str(named.data.get("speak_to_user") or "")

                set_current_messages(
                    [
                        {"type": "human", "content": "invest"},
                        {"type": "ai", "content": start_speak},
                        {"type": "human", "content": "Gold Plaza"},
                        {"type": "ai", "content": named.data.get("speak_to_user")},
                        {"type": "human", "content": "3"},
                    ]
                )
                confirm = asyncio.run(
                    try_server_invest_property_turn(_investor(), MagicMock())
                )
                assert confirm.data.get("awaiting_invest_confirmation") is True
                assert "Reply Yes" in str(confirm.data.get("speak_to_user") or "")

                set_current_messages(
                    [
                        {"type": "human", "content": "invest"},
                        {"type": "ai", "content": start_speak},
                        {"type": "human", "content": "Gold Plaza"},
                        {"type": "ai", "content": named.data.get("speak_to_user")},
                        {"type": "human", "content": "3"},
                        {"type": "ai", "content": confirm.data.get("speak_to_user")},
                        {"type": "human", "content": "Yes"},
                    ]
                )
                submitted = asyncio.run(
                    try_server_invest_property_turn(_investor(), MagicMock())
                )
                assert submitted.data.get("submitted") is True
                assert any(
                    a.type == "SUBMIT_FORM" and a.modal == "INVEST_PROPERTY"
                    for a in submitted.actions
                )
                assert any(a.type == "NAVIGATE" for a in submitted.actions)
                assert "MetaMask" in str(submitted.data.get("speak_to_user") or "")
    finally:
        _clear_workflow_session("INVEST_PROPERTY")
        reset_current_thread_id(token)


def test_marketplace_catalog_then_hash_id_resolves_property():
    token = set_current_thread_id("test:flow:marketplace-hash-id")
    catalog = format_investor_marketplace_catalog_speak(
        [_gold_plaza_prop()],
        total_listed=1,
    )
    prop = _gold_plaza_prop()
    msg_token = set_current_messages(
        [
            {
                "type": "human",
                "content": "Browse marketplace",
                "quick_action_id": "investor.marketplace",
            },
            {"type": "ai", "content": catalog},
            {"type": "human", "content": "#5"},
        ]
    )
    try:
        _clear_workflow_session("INVEST_PROPERTY")
        with patch(
            "backend.ai.tools._resolve_property_by_name",
            return_value=(prop, None),
        ), patch("backend.ai.tools._load_invest_property_row", return_value=prop):
            result = asyncio.run(try_server_invest_property_turn(_investor(), MagicMock()))
        assert result is not None
        speak = str(result.data.get("speak_to_user") or "")
        assert INVEST_TOKEN_ASK in speak
        assert "Gold Plaza" in speak
    finally:
        _clear_workflow_session("INVEST_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)
