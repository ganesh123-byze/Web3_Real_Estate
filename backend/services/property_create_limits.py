"""Dynamic create-property value caps from the signed-in owner wallet and platform deployer gas."""
from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException

from backend.api._helpers import validate_monthly_rent_for_chain
from backend.services.blockchain import (
    from_wei,
    get_deployer_address,
    get_native_balance,
    get_web3,
    platform_deployer_mismatch,
    to_wei,
)
from backend.services.wallet_funding import format_eth_display, read_native_balance_wei

# Must stay aligned with RentDistribution.sol (rentWei <= 100 ether).
ON_CHAIN_MAX_MONTHLY_RENT_ETH = Decimal("100")

MIN_OWNER_BALANCE_ETH = Decimal(os.getenv("CREATE_PROPERTY_MIN_OWNER_BALANCE_ETH", "0.001"))
MIN_DEPLOYER_BALANCE_ETH = Decimal(os.getenv("CREATE_PROPERTY_MIN_DEPLOYER_BALANCE_ETH", "0.05"))
# total_value cap scales with owner Sepolia balance (listing size vs wallet liquidity).
TOTAL_VALUE_BALANCE_MULTIPLIER = Decimal(
    os.getenv("CREATE_PROPERTY_TOTAL_VALUE_BALANCE_MULTIPLIER", "50000")
)
# Reserve headroom on owner wallet when capping monthly rent (gas + sanity buffer).
OWNER_RENT_BALANCE_HEADROOM = Decimal(os.getenv("CREATE_PROPERTY_RENT_BALANCE_HEADROOM", "0.002"))


@dataclass(frozen=True)
class CreatePropertyLimits:
    """Caps and readiness for one property-owner create flow."""

    owner_wallet: str
    owner_balance_eth: Decimal
    deployer_balance_eth: Decimal
    max_monthly_rent_eth: Decimal
    max_total_value_eth: Decimal
    min_owner_balance_eth: Decimal
    min_deployer_balance_eth: Decimal
    platform_deploy_ready: bool
    owner_balance_sufficient: bool
    deployer_warning: dict | None
    deployment_block_reason: str | None
    owner_block_reason: str | None

    @property
    def can_deploy(self) -> bool:
        return (
            self.platform_deploy_ready
            and self.owner_balance_sufficient
            and not self.deployment_block_reason
            and not self.owner_block_reason
        )

    def as_tool_payload(self) -> dict[str, str | bool | None]:
        return {
            "owner_wallet": self.owner_wallet,
            "owner_balance_eth": _format_eth(self.owner_balance_eth),
            "deployer_balance_eth": _format_eth(self.deployer_balance_eth),
            "max_monthly_rent_eth": _format_eth(self.max_monthly_rent_eth),
            "max_total_value_eth": _format_eth(self.max_total_value_eth),
            "min_owner_balance_eth": _format_eth(self.min_owner_balance_eth),
            "min_deployer_balance_eth": _format_eth(self.min_deployer_balance_eth),
            "platform_deploy_ready": self.platform_deploy_ready,
            "owner_balance_sufficient": self.owner_balance_sufficient,
            "can_deploy": self.can_deploy,
            "deployment_block_reason": self.deployment_block_reason,
            "owner_block_reason": self.owner_block_reason,
        }


def _format_eth(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _read_balance_eth(wallet_address: str) -> Decimal:
    web3 = get_web3()
    if not wallet_address or not web3.is_address(wallet_address):
        return Decimal("0")
    checksum = web3.to_checksum_address(wallet_address)
    return from_wei(read_native_balance_wei(checksum))


def _compute_max_monthly_rent(owner_balance_eth: Decimal) -> Decimal:
    """Rent capped by on-chain max and by owner wallet (cannot exceed balance minus headroom)."""
    chain_cap = ON_CHAIN_MAX_MONTHLY_RENT_ETH
    if owner_balance_eth <= OWNER_RENT_BALANCE_HEADROOM:
        return Decimal("0")
    wallet_cap = owner_balance_eth - OWNER_RENT_BALANCE_HEADROOM
    if wallet_cap <= 0:
        return Decimal("0")
    return min(chain_cap, wallet_cap)


def _compute_max_total_value(owner_balance_eth: Decimal) -> Decimal:
    if owner_balance_eth <= 0:
        return Decimal("0")
    return owner_balance_eth * TOTAL_VALUE_BALANCE_MULTIPLIER


def assess_create_property_limits(owner_wallet: str) -> CreatePropertyLimits:
    """Fetch live balances and derive caps for the signed-in property owner."""
    web3 = get_web3()
    if not owner_wallet or not web3.is_address(owner_wallet):
        return CreatePropertyLimits(
            owner_wallet=owner_wallet or "",
            owner_balance_eth=Decimal("0"),
            deployer_balance_eth=Decimal("0"),
            max_monthly_rent_eth=Decimal("0"),
            max_total_value_eth=Decimal("0"),
            min_owner_balance_eth=MIN_OWNER_BALANCE_ETH,
            min_deployer_balance_eth=MIN_DEPLOYER_BALANCE_ETH,
            platform_deploy_ready=False,
            owner_balance_sufficient=False,
            deployer_warning={"code": "INVALID_OWNER_WALLET", "message": "No valid wallet connected."},
            deployment_block_reason="Connect a valid Sepolia wallet before creating a property.",
            owner_block_reason="Connect a valid Sepolia wallet before creating a property.",
        )

    owner_checksum = web3.to_checksum_address(owner_wallet)
    owner_balance_eth = _read_balance_eth(owner_checksum)

    deployer_warning = platform_deployer_mismatch()
    deployer_balance_eth = Decimal("0")
    deployment_block_reason: str | None = None

    try:
        deployer_address = get_deployer_address()
        deployer_balance_eth = _read_balance_eth(deployer_address)
    except Exception:
        deployment_block_reason = (
            "Platform deployer is not configured. Property creation cannot complete on-chain."
        )

    if deployer_warning:
        deployment_block_reason = str(
            deployer_warning.get("message")
            or "Platform deployer configuration is invalid."
        )
    elif deployer_balance_eth < MIN_DEPLOYER_BALANCE_ETH:
        deployment_block_reason = (
            "Platform deployer wallet needs more Sepolia ETH for on-chain setup "
            f"(has {_format_eth(deployer_balance_eth)} ETH, needs at least "
            f"{_format_eth(MIN_DEPLOYER_BALANCE_ETH)} ETH). Try again later."
        )

    owner_block_reason: str | None = None
    if owner_balance_eth < MIN_OWNER_BALANCE_ETH:
        owner_block_reason = (
            f"Your wallet needs at least {_format_eth(MIN_OWNER_BALANCE_ETH)} Sepolia ETH "
            f"to create a property (current balance: {_format_eth(owner_balance_eth)} ETH). "
            "Add Sepolia ETH to your connected wallet and try again."
        )

    max_monthly_rent = _compute_max_monthly_rent(owner_balance_eth)
    max_total_value = _compute_max_total_value(owner_balance_eth)

    return CreatePropertyLimits(
        owner_wallet=owner_checksum,
        owner_balance_eth=owner_balance_eth,
        deployer_balance_eth=deployer_balance_eth,
        max_monthly_rent_eth=max_monthly_rent,
        max_total_value_eth=max_total_value,
        min_owner_balance_eth=MIN_OWNER_BALANCE_ETH,
        min_deployer_balance_eth=MIN_DEPLOYER_BALANCE_ETH,
        platform_deploy_ready=deployment_block_reason is None,
        owner_balance_sufficient=owner_block_reason is None,
        deployer_warning=deployer_warning,
        deployment_block_reason=deployment_block_reason,
        owner_block_reason=owner_block_reason,
    )


def monthly_rent_skip_value(value: str) -> bool:
    return (value or "").strip().lower() in {"0", "skip", "none", "no", "n/a", ""}


def monthly_rent_exceeds_cap(value: str, max_eth: Decimal) -> bool:
    if monthly_rent_skip_value(value):
        return False
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return False
    if amount <= 0:
        return False
    return amount > max_eth


def total_value_exceeds_cap(value: str, max_eth: Decimal) -> bool:
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return False
    if amount <= 0:
        return False
    return amount > max_eth


def validate_create_property_values(
    limits: CreatePropertyLimits,
    *,
    total_value: str | None = None,
    monthly_rent_eth: str | None = None,
) -> str | None:
    """Return a user-facing error string, or None when values are within caps."""
    if limits.owner_block_reason:
        return limits.owner_block_reason
    if limits.deployment_block_reason:
        return limits.deployment_block_reason

    if total_value not in (None, ""):
        if total_value_exceeds_cap(total_value, limits.max_total_value_eth):
            return (
                f"Total property value cannot exceed {_format_eth(limits.max_total_value_eth)} ETH "
                f"for your current wallet balance ({_format_eth(limits.owner_balance_eth)} ETH). "
                "Lower the total value or add Sepolia ETH to your wallet."
            )

    if monthly_rent_eth not in (None, "") and not monthly_rent_skip_value(monthly_rent_eth):
        if monthly_rent_exceeds_cap(monthly_rent_eth, limits.max_monthly_rent_eth):
            return (
                f"Monthly rent cannot exceed {_format_eth(limits.max_monthly_rent_eth)} ETH "
                f"(based on your wallet balance of {_format_eth(limits.owner_balance_eth)} ETH "
                f"and the {_format_eth(ON_CHAIN_MAX_MONTHLY_RENT_ETH)} ETH on-chain cap). "
                "Lower the rent, say 0/skip, or add Sepolia ETH to your wallet."
            )
        try:
            rent_wei = to_wei(Decimal(str(monthly_rent_eth)))
            if rent_wei > 0:
                validate_monthly_rent_for_chain(rent_wei)
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            return detail
        except (TypeError, ValueError, InvalidOperation, ArithmeticError) as exc:
            return str(exc)

    return None


def monthly_rent_rejection_message(value: str, limits: CreatePropertyLimits) -> str:
    max_rent = _format_eth(limits.max_monthly_rent_eth)
    return (
        f"{value} ETH is too high — monthly rent must be at most {max_rent} ETH. "
        f"{monthly_rent_collection_prompt(limits)}"
    )


def total_value_collection_prompt(limits: CreatePropertyLimits) -> str:
    max_value = _format_eth(limits.max_total_value_eth)
    balance = _format_eth(limits.owner_balance_eth)
    if limits.max_total_value_eth <= 0:
        return (
            f"Your wallet balance is {balance} ETH — add Sepolia ETH before setting a total property value."
        )
    return (
        f"Your wallet balance is {balance} ETH. Total property value can be at most {max_value} ETH "
        f"(based on your wallet balance). What's the total property value in ETH?"
    )


def total_value_rejection_message(value: str, limits: CreatePropertyLimits) -> str:
    max_value = _format_eth(limits.max_total_value_eth)
    balance = _format_eth(limits.owner_balance_eth)
    return (
        f"{value} ETH is too high — total property value cannot exceed {max_value} ETH "
        f"for your current wallet balance ({balance} ETH). "
        f"{total_value_collection_prompt(limits)}"
    )


def monthly_rent_collection_prompt(limits: CreatePropertyLimits) -> str:
    max_rent = _format_eth(limits.max_monthly_rent_eth)
    balance = _format_eth(limits.owner_balance_eth)
    if limits.max_monthly_rent_eth <= 0:
        return (
            f"Your wallet balance is {balance} ETH — add Sepolia ETH before setting monthly rent, "
            "or say 0 or skip if you do not want rent yet."
        )
    return (
        f"Your wallet balance is {balance} ETH. Monthly rent must be at most {max_rent} ETH "
        f"(capped by your balance and the {_format_eth(ON_CHAIN_MAX_MONTHLY_RENT_ETH)} ETH on-chain limit). "
        "What's the monthly rent in ETH? Say 0 or skip if you don't want rent yet."
    )
