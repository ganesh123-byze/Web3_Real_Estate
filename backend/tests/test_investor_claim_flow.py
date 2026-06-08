"""Guided investor yield-claim workflow — server preflight."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.ai import tools
from backend.ai.tools import (
    _fill_claim_yield,
    set_current_messages,
    set_current_thread_id,
)
from backend.services.auth import AuthUser


def _investor() -> AuthUser:
    return AuthUser(
        id=1,
        wallet_address="0xabc123456789012345678901234567890abcdef12",
        role="investor",
        email="inv@test.com",
        kyc_status="verified",
        active=True,
    )


def _claimable_rows():
    return [
        {
            "property_id": 4,
            "property_name": "Sunset Villas",
            "claimable_amount_wei": "1000000000000000000",
            "claimable_amount_eth": "1",
            "pending_payouts": 2,
        }
    ]


@pytest.fixture(autouse=True)
def _thread():
    token = set_current_thread_id("test:claim-flow")
    yield
    tools.reset_current_thread_id(token)


def test_claim_my_yield_preflight_shows_confirmation():
    set_current_messages([{"role": "user", "content": "claim my yield"}])
    with patch.object(tools, "_list_claimable_reward_rows", return_value=_claimable_rows()):
        result = asyncio.run(tools.try_server_investor_claim_yield_turn(_investor(), MagicMock()))
    assert result is not None
    assert result.ok
    assert result.data.get("awaiting_claim_confirmation") is True
    assert "Yield claim summary" in str(result.data.get("speak_to_user"))


def test_claim_my_yield_no_balance_message():
    set_current_messages([{"role": "user", "content": "claim my yield"}])
    with patch.object(tools, "_list_claimable_reward_rows", return_value=[]):
        result = asyncio.run(tools.try_server_investor_claim_yield_turn(_investor(), MagicMock()))
    assert result is not None
    assert "no claimable" in str(result.data.get("speak_to_user")).lower()


def test_claim_confirm_yes_opens_metamask_actions():
    tools._set_workflow_session(
        "CLAIM_REWARDS",
        {
            "in_progress": True,
            "filled": {"property_name": "Sunset Villas", "property_id": "4"},
            "awaiting_claim_confirmation": True,
            "property_id": 4,
        },
    )
    set_current_messages(
        [
            {"role": "user", "content": "claim my yield"},
            {"role": "user", "content": "yes"},
        ]
    )
    with patch.object(tools, "_list_claimable_reward_rows", return_value=_claimable_rows()):
        with patch.object(tools, "_resolve_claimable_property", return_value=(_claimable_rows()[0], None)):
            with patch.object(
                tools,
                "_execute_claim_rewards_ui",
                new_callable=AsyncMock,
                return_value=tools.ToolResult(
                    ok=True,
                    data={"speak_to_user": "Confirm in MetaMask."},
                    actions=tools._claim_actions_on_submit(4),
                ),
            ) as execute:
                result = asyncio.run(
                    _fill_claim_yield({"confirm_claim": True}, _investor(), MagicMock())
                )
    execute.assert_awaited_once()
    assert result.ok
    assert result.data.get("submitted") is True
    assert any(action.type == "SUBMIT_FORM" for action in result.actions)
