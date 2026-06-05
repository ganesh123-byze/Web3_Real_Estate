"""PropertyCreate accepts omitted/empty optional decimals; rejects blank required fields."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.api.schemas import PropertyCreate


def test_optional_decimals_empty_string_become_none():
    payload = PropertyCreate(
        name="  Test Villa  ",
        location=" Austin ",
        total_value="10",
        token_supply="100",
        token_symbol=" TVL ",
        token_sale_price_eth="",
        monthly_rent_eth="",
    )
    assert payload.name == "Test Villa"
    assert payload.location == "Austin"
    assert payload.token_symbol == "TVL"
    assert payload.token_sale_price_eth is None
    assert payload.monthly_rent_eth is None


def test_optional_decimals_may_be_omitted():
    payload = PropertyCreate(
        name="Test",
        location="Austin",
        total_value="10",
        token_supply="100",
        token_symbol="TVL",
    )
    assert payload.token_sale_price_eth is None
    assert payload.monthly_rent_eth is None


def test_required_decimal_blank_rejected():
    with pytest.raises(ValidationError):
        PropertyCreate(
            name="Test",
            location="Austin",
            total_value="",
            token_supply="100",
            token_symbol="TVL",
        )


def test_legacy_eth_suffix_stripped_from_optional_decimal():
    payload = PropertyCreate(
        name="Test",
        location="Austin",
        total_value="10",
        token_supply="100",
        token_symbol="TVL",
        token_sale_price_eth="0.1 ETH",
    )
    assert payload.token_sale_price_eth == Decimal("0.1")
