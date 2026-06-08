"""Token holding metrics — whole-token counts and ownership % of property supply."""
from __future__ import annotations

from decimal import Decimal

from backend.config.settings import TOKEN_DECIMALS
from backend.services.blockchain import from_base_units


def whole_tokens_from_base(token_amount_base: int) -> int:
    """Convert on-chain base units (wei-style) to whole token count."""
    if not token_amount_base:
        return 0
    return int(from_base_units(token_amount_base, TOKEN_DECIMALS))


def whole_supply_from_property(supply: int | str | Decimal | None) -> int:
    """Property token_supply is stored as a human whole number, not base units."""
    try:
        return int(Decimal(str(supply or 0)))
    except (TypeError, ValueError, ArithmeticError):
        return 0


def ownership_percentage_of_supply(
    tokens_whole: int,
    supply_whole: int,
    *,
    digits: int = 2,
) -> float:
    """Share of total minted supply held by one wallet (0–100)."""
    if supply_whole <= 0 or tokens_whole <= 0:
        return 0.0
    return round((tokens_whole / supply_whole) * 100, digits)
