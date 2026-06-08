"""Investor guided-invest field validation — token count vs listing supply."""
from __future__ import annotations

from typing import Any


def read_property_tokens_available(prop: dict[str, Any]) -> int:
    """Whole tokens still available for sale on the listing."""
    try:
        return max(0, int(str(prop.get("tokens_available") or "0")))
    except (TypeError, ValueError):
        return 0


def parse_invest_token_count(token_amount: int | str | None) -> int | None:
    try:
        value = int(str(token_amount or "").strip())
    except (TypeError, ValueError):
        return None
    return value if value >= 1 else None


def invest_token_amount_exceeds_available(
    token_amount: int | str | None,
    prop: dict[str, Any],
) -> bool:
    """True when the user asked to buy more tokens than the listing has left."""
    amount = parse_invest_token_count(token_amount)
    if amount is None:
        return False
    return amount > read_property_tokens_available(prop)


def invest_exceeds_available_tokens_message(
    token_amount: int | str | None,
    prop: dict[str, Any],
) -> str:
    """Verbatim error when the order size is above tokens_available."""
    available = read_property_tokens_available(prop)
    name = str(prop.get("name") or f"Property {prop.get('id')}")
    if available <= 0:
        return (
            f"{name} has no tokens available for sale right now. "
            "Choose another property or try again later."
        )
    return (
        "Don't exceed the number of available tokens to invest. "
        f"{name} has {available} token{'s' if available != 1 else ''} available — "
        f"please enter {available} or fewer."
    )
