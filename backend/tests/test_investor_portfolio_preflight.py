"""Investor copilot: portfolio requests use live on-chain holdings, not stale chat memory."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from backend.ai.investor_guards import (
    format_investor_portfolio_speak,
    has_investor_portfolio_intent,
)
from backend.ai.tools import _token_sale_price_eth_from_row
from backend.ai.tools import (
    reset_current_messages,
    reset_current_thread_id,
    set_current_messages,
    set_current_thread_id,
    try_server_investor_portfolio_overview,
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


def test_token_sale_price_eth_from_token_price_base_wei():
    wei = str(10**17)
    assert _token_sale_price_eth_from_row({"token_price_base": wei}) == "0.1000"


def test_has_investor_portfolio_intent():
    assert has_investor_portfolio_intent("show my portfolio") is True
    assert has_investor_portfolio_intent("invest 1 token in Gold Plaza") is False
    assert has_investor_portfolio_intent(
        "Show me my investment portfolio with current valuations."
    ) is True


def test_format_portfolio_lists_property_names():
    text = format_investor_portfolio_speak(
        {
            "count": 2,
            "holdings": [
                {
                    "property_id": 4,
                    "property_name": "Eiffel Crown Residences",
                    "token_amount": 1,
                    "ownership_percentage": 0.2,
                    "token_sale_price_eth": "0.09",
                },
                {
                    "property_id": 1,
                    "property_name": "Siddiq villa",
                    "token_amount": 3,
                    "ownership_percentage": 0.3,
                    "token_sale_price_eth": "0.1",
                },
            ],
        },
        {"total_earned_eth": "0.5", "total_claimable_eth": "0.1", "total_claimed_eth": "0.4"},
    )
    assert "Yield & returns summary" in text
    assert "Eiffel Crown Residences (#4)" in text
    assert "Siddiq villa (#1)" in text
    assert "Total rental yield earned: 0.5 ETH" in text


def test_preflight_portfolio_refreshes_chain_and_returns_verbatim():
    token = set_current_thread_id("test:portfolio-preflight")
    msg_token = set_current_messages([{"type": "human", "content": "my portfolio"}])
    db = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = {"id": 2}
    cursor.fetchall.return_value = [
        {
            "property_id": 4,
            "property_name": "Eiffel Crown Residences",
            "location": "Paris",
            "token_symbol": "ECR",
            "token_supply": 500 * 10**18,
            "token_price_base": str(int(0.09 * 10**18)),
            "token_amount_base": 1 * 10**18,
        },
    ]
    db.cursor.return_value = cursor

    try:
        with patch(
            "backend.ai.tools._refresh_investor_portfolio_from_chain",
        ), patch(
            "backend.ai.tools._get_my_yield_summary",
        ) as yield_mock:
            from backend.ai.tools import ToolResult

            yield_mock.return_value = ToolResult(
                ok=True,
                data={
                    "total_earned_eth": "0",
                    "total_claimable_eth": "0",
                    "total_claimed_eth": "0",
                },
            )
            result = asyncio.run(try_server_investor_portfolio_overview(_investor(), db))
        assert result is not None
        assert result.data.get("investor_portfolio_overview") is True
        assert result.data.get("speak_verbatim") is True
        speak = str(result.data.get("speak_to_user") or "")
        assert "Eiffel Crown Residences (#4)" in speak
        assert "1 tokens" in speak
    finally:
        reset_current_messages(msg_token)
        reset_current_thread_id(token)
