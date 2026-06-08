"""Ownership % helpers — token_supply is whole tokens; holdings are base units."""
from __future__ import annotations

from backend.ai.owner_guards import format_owner_investors_speak
from backend.services.token_ownership_metrics import (
    ownership_percentage_of_supply,
    whole_supply_from_property,
    whole_tokens_from_base,
)


def test_whole_tokens_from_base_units():
    assert whole_tokens_from_base(0) == 0
    assert whole_tokens_from_base(4 * 10**18) == 4
    assert whole_tokens_from_base(1 * 10**18) == 1


def test_whole_supply_from_property_is_not_scaled():
    assert whole_supply_from_property(50) == 50
    assert whole_supply_from_property("10000") == 10000


def test_ownership_percentage_of_supply():
    assert ownership_percentage_of_supply(4, 50) == 8.0
    assert ownership_percentage_of_supply(1, 50) == 2.0
    assert ownership_percentage_of_supply(0, 50) == 0.0
    assert ownership_percentage_of_supply(4, 0) == 0.0


def test_format_owner_investors_speak_shows_nonzero_percentages():
    speak = format_owner_investors_speak(
        {
            "total_investors": 2,
            "properties": [
                {
                    "property_id": 9,
                    "property_name": "Marina Bay Heights",
                    "investors": [
                        {
                            "wallet_address": "0x3c1d000000000000000000000000000000007e4b",
                            "token_amount": 4,
                            "ownership_percentage": 8.0,
                        },
                        {
                            "wallet_address": "0x80550000000000000000000000000000000766a",
                            "token_amount": 1,
                            "ownership_percentage": 2.0,
                        },
                    ],
                }
            ],
        }
    )
    assert "8.00% of supply" in speak
    assert "2.00% of supply" in speak
    assert "tokens (0% of supply)" not in speak
