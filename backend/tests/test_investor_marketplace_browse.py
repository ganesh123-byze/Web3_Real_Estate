"""Investor copilot: marketplace browse returns property details, not navigation-only."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from backend.ai.investor_guards import (
    format_investor_marketplace_catalog_speak,
    has_marketplace_browse_intent,
)
from backend.ai.tools import (
    _investor_marketplace_catalog_data,
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


def test_has_marketplace_browse_intent_matches_quick_action():
    prompt = "Take me to the marketplace and show me available properties to invest in."
    assert has_marketplace_browse_intent(prompt) is True


def test_has_marketplace_browse_intent_not_explicit_buy():
    assert has_marketplace_browse_intent("Invest 10 tokens into Gold Plaza") is False


def test_format_marketplace_catalog_lists_property_details():
    investable = [
        {
            "id": 7,
            "name": "Gold Plaza",
            "location": "Gujarat",
            "token_symbol": "GP",
            "sold_percentage": "12.5",
            "tokens_available": "8800",
            "token_sale_price_eth": "0.01",
            "monthly_rent_eth": "1",
        }
    ]
    text = format_investor_marketplace_catalog_speak(investable, total_listed=12)
    assert "Gold Plaza" in text
    assert "Gujarat" in text
    assert "8800 tokens available" in text
    assert "0.01 ETH/token" in text
    assert "monthly rent 1 ETH" in text
    assert "twelve" not in text.lower()
    assert "I've opened the marketplace" in text


def test_investor_marketplace_catalog_data_speak_verbatim():
    items = [
        {
            "id": 1,
            "name": "Tower",
            "location": "NYC",
            "token_symbol": "TWR",
            "token_address": "0xabc",
            "tokens_available": "100",
            "sold_percentage": "0",
            "token_sale_price_eth": "0.1",
            "monthly_rent_eth": "0",
        }
    ]
    data = _investor_marketplace_catalog_data(items)
    assert data.get("marketplace_catalog") is True
    assert data.get("speak_verbatim") is True
    assert "Tower" in str(data.get("speak_to_user"))


def test_marketplace_browse_preflight_returns_catalog():
    db = MagicMock()
    items = [
        {
            "id": 1,
            "name": "Tower",
            "location": "NYC",
            "token_symbol": "TWR",
            "token_address": "0xabc",
            "tokens_available": "100",
            "sold_percentage": "0",
            "token_sale_price_eth": "0.1",
            "monthly_rent_eth": "0",
        }
    ]
    with patch("backend.ai.tools._latest_human_utterance", return_value="Browse marketplace"), patch(
        "backend.ai.tools._list_properties", return_value=items
    ):
        result = asyncio.run(try_server_investor_marketplace_browse(_investor(), db))
    assert result is not None
    assert result.ok
    assert "Tower" in str(result.data.get("speak_to_user"))
    assert any(a.type == "NAVIGATE" and a.route == "/investor/marketplace" for a in result.actions)
