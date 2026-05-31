"""Unit tests for wallet-based create-property value caps."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from backend.services.property_create_limits import (
    ON_CHAIN_MAX_MONTHLY_RENT_ETH,
    assess_create_property_limits,
    monthly_rent_exceeds_cap,
    total_value_exceeds_cap,
    validate_create_property_values,
)


def _mock_balance_context(owner: str, deployer: str):
    balances = {
        owner.lower(): Decimal("2.5"),
        deployer.lower(): Decimal("0.2"),
    }

    def _read(wallet: str) -> Decimal:
        return balances.get((wallet or "").lower(), Decimal("0"))

    return (
        patch(
            "backend.services.property_create_limits._read_balance_eth",
            side_effect=_read,
        ),
        patch(
            "backend.services.property_create_limits.platform_deployer_mismatch",
            return_value=None,
        ),
        patch(
            "backend.services.property_create_limits.get_deployer_address",
            return_value=deployer,
        ),
    )


def test_assess_limits_scales_caps_from_owner_balance():
    owner = "0x00000000000000000000000000000000000000aa"
    deployer = "0x00000000000000000000000000000000000000bb"
    bal_patch, mismatch_patch, deployer_patch = _mock_balance_context(owner, deployer)
    with bal_patch, mismatch_patch, deployer_patch:
        limits = assess_create_property_limits(owner)
    assert limits.owner_balance_eth == Decimal("2.5")
    assert limits.max_monthly_rent_eth == Decimal("2.5") - Decimal("0.002")
    assert limits.max_total_value_eth == Decimal("2.5") * Decimal("50000")
    assert limits.can_deploy is True


def test_rent_cap_respects_on_chain_max():
    owner = "0x00000000000000000000000000000000000000cc"
    deployer = "0x00000000000000000000000000000000000000dd"

    def _rich(_wallet: str) -> Decimal:
        return Decimal("500")

    with (
        patch(
            "backend.services.property_create_limits._read_balance_eth",
            side_effect=_rich,
        ),
        patch(
            "backend.services.property_create_limits.platform_deployer_mismatch",
            return_value=None,
        ),
        patch(
            "backend.services.property_create_limits.get_deployer_address",
            return_value=deployer,
        ),
    ):
        limits = assess_create_property_limits(owner)
    assert limits.max_monthly_rent_eth == ON_CHAIN_MAX_MONTHLY_RENT_ETH


def test_validate_rejects_rent_and_total_above_caps():
    owner = "0x00000000000000000000000000000000000000ee"
    deployer = "0x00000000000000000000000000000000000000ff"
    bal_patch, mismatch_patch, deployer_patch = _mock_balance_context(owner, deployer)
    with bal_patch, mismatch_patch, deployer_patch:
        limits = assess_create_property_limits(owner)
    assert monthly_rent_exceeds_cap("3", limits.max_monthly_rent_eth) is True
    assert total_value_exceeds_cap("200000", limits.max_total_value_eth) is True
    rent_err = validate_create_property_values(limits, monthly_rent_eth="3")
    value_err = validate_create_property_values(limits, total_value="200000")
    assert rent_err is not None
    assert value_err is not None


def test_validate_allows_values_within_caps():
    owner = "0x0000000000000000000000000000000000000011"
    deployer = "0x0000000000000000000000000000000000000022"
    bal_patch, mismatch_patch, deployer_patch = _mock_balance_context(owner, deployer)
    with bal_patch, mismatch_patch, deployer_patch:
        limits = assess_create_property_limits(owner)
    assert (
        validate_create_property_values(
            limits,
            total_value="1000",
            monthly_rent_eth="0.5",
        )
        is None
    )
