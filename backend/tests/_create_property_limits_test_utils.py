"""Shared mocks for create-property limit tests (avoids live RPC in workflow tests)."""
from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch

from backend.services.property_create_limits import (
    MIN_DEPLOYER_BALANCE_ETH,
    MIN_OWNER_BALANCE_ETH,
    CreatePropertyLimits,
    _compute_max_monthly_rent,
    _compute_max_total_value,
)


def generous_create_property_limits(
    *,
    wallet: str = "0x0000000000000000000000000000000000000001",
    owner_balance_eth: Decimal = Decimal("100"),
    deployer_balance_eth: Decimal = Decimal("1"),
) -> CreatePropertyLimits:
    return CreatePropertyLimits(
        owner_wallet=wallet,
        owner_balance_eth=owner_balance_eth,
        deployer_balance_eth=deployer_balance_eth,
        max_monthly_rent_eth=_compute_max_monthly_rent(owner_balance_eth),
        max_total_value_eth=_compute_max_total_value(owner_balance_eth),
        min_owner_balance_eth=MIN_OWNER_BALANCE_ETH,
        min_deployer_balance_eth=MIN_DEPLOYER_BALANCE_ETH,
        platform_deploy_ready=True,
        owner_balance_sufficient=True,
        deployer_warning=None,
        deployment_block_reason=None,
        owner_block_reason=None,
    )


@contextmanager
def patch_generous_create_property_limits(**kwargs):
    limits = generous_create_property_limits(**kwargs)
    with (
        patch(
            "backend.ai.tools.assess_create_property_limits",
            return_value=limits,
        ),
        patch(
            "backend.services.property_create_limits.assess_create_property_limits",
            return_value=limits,
        ),
    ):
        yield limits
