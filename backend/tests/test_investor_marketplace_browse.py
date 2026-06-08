"""Investor copilot: marketplace browse returns property details, not navigation-only."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from backend.ai.investor_marketplace import (
    INVESTOR_MARKETPLACE_CATALOG_HEADING,
    derive_property_yield_metrics,
    format_investor_marketplace_catalog_speak,
    has_marketplace_browse_intent,
    marketplace_browse_turn_matches,
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


def test_has_marketplace_browse_intent_natural_phrases():
    assert has_marketplace_browse_intent("Show me available properties") is True
    assert has_marketplace_browse_intent("What are available properties to invest") is True


def test_marketplace_browse_turn_matches_quick_action_id():
    assert marketplace_browse_turn_matches("", quick_action_id="investor.marketplace") is True


def test_has_marketplace_browse_intent_not_explicit_buy():
    assert has_marketplace_browse_intent("Invest 10 tokens into Gold Plaza") is False


def test_format_marketplace_catalog_caps_long_percentage_decimals():
    investable = [
        {
            "id": 8,
            "name": "Marina Bay Heights",
            "location": "Singapore",
            "token_symbol": "MBH",
            "sold_percentage": "8.33333333333333333333333333333333",
            "tokens_available": "55",
            "token_sale_price_eth": "0.13333333333333334",
            "monthly_rent_eth": "0.3",
        }
    ]
    text = format_investor_marketplace_catalog_speak(investable, total_listed=4)
    assert "8.33333333333333333333333333333333" not in text
    assert "8.333% sold" in text
    assert "0.13333333333333334" not in text
    assert "0.133 ETH/token" in text


def test_format_marketplace_catalog_lists_property_details():
    investable = [
        {
            "id": 7,
            "name": "Gold Plaza",
            "location": "Gujarat",
            "token_symbol": "GP",
            "token_supply": "10000",
            "sold_percentage": "12.5",
            "tokens_available": "8800",
            "token_sale_price_eth": "0.01",
            "monthly_rent_eth": "1",
        }
    ]
    text = format_investor_marketplace_catalog_speak(investable, total_listed=12)
    assert INVESTOR_MARKETPLACE_CATALOG_HEADING in text
    assert "Property: Gold Plaza (#7)" in text
    assert "Location: Gujarat" in text
    assert "Tokens available: 8800" in text
    assert "Price per token: 0.01 ETH" in text
    assert "Yield & returns summary" in text
    assert "Monthly rent: 1 ETH" in text
    assert "Gross annual yield:" in text
    assert "twelve" not in text.lower()
    assert "I've opened the marketplace" in text


def test_derive_property_yield_metrics_matches_ui_formula():
    metrics = derive_property_yield_metrics(
        {
            "monthly_rent_eth": "1",
            "token_sale_price_eth": "0.01",
            "token_supply": "10000",
        }
    )
    assert metrics is not None
    assert metrics["gross_annual_yield_pct"] == 12.0
    assert metrics["net_projected_yield_pct"] == 7.92


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
