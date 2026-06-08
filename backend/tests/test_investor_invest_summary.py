"""Investor guided-invest property and order summary cards."""
from __future__ import annotations

from backend.ai.investor_invest_summary import (
    INVEST_ORDER_SUMMARY_HEADING,
    INVEST_PROPERTY_SUMMARY_HEADING,
    format_invest_confirmation_summary,
    format_invest_order_summary_speak,
    format_invest_property_summary_speak,
)
from backend.ai.investor_guards import format_invest_target_property_speak


def _brightcone():
    return {
        "id": 11,
        "name": "Brightcone",
        "location": "USA",
        "tokens_available": "99",
        "token_sale_price_eth": "0.1",
        "monthly_rent_eth": "0.1",
    }


def test_property_summary_heading_and_fields():
    text = format_invest_property_summary_speak(_brightcone())
    assert text.startswith(INVEST_PROPERTY_SUMMARY_HEADING)
    assert "Property Name: Brightcone (#11)" in text
    assert "Location: USA" in text
    assert "Monthly Rent: 0.1 ETH" in text
    assert "Tokens Available: 99" in text
    assert "Price per token" not in text
    assert "Token buying" not in text
    assert "Total amount" not in text


def test_investment_summary_includes_token_buying_and_total():
    text = format_invest_order_summary_speak(_brightcone(), 3)
    assert text.startswith(INVEST_ORDER_SUMMARY_HEADING)
    assert "Property Name: Brightcone (#11)" in text
    assert "Location: USA" in text
    assert "Monthly Rent: 0.1 ETH" in text
    assert "Tokens Available: 99" in text
    assert "Token buying: 3 tokens" in text
    assert "Total amount: 0.3 ETH" in text
    assert "Price per token" not in text


def test_confirmation_summary_includes_yes_no_footer():
    text = format_invest_confirmation_summary(_brightcone(), 2)
    assert "Investment summary" in text
    assert "Token buying: 2 tokens" in text
    assert "Total amount: 0.2 ETH" in text
    assert "Reply Yes" in text


def test_format_invest_target_property_speak_routes_by_token_amount():
    prop = _brightcone()
    preview = format_invest_target_property_speak(prop)
    assert "Property summary" in preview
    assert "Price per token" not in preview

    order = format_invest_target_property_speak(prop, token_amount=5)
    assert "Investment summary" in order
    assert "Token buying: 5 tokens" in order
    assert "Total amount: 0.5 ETH" in order
