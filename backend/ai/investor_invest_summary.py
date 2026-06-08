"""Investor guided-invest summary cards — property preview and order confirmation."""
from __future__ import annotations

from typing import Any

from backend.ai.chat_stat_format import format_chat_stat_eth_amount

INVEST_PROPERTY_SUMMARY_HEADING = "Property summary"
INVEST_ORDER_SUMMARY_HEADING = "Investment summary"

INVEST_CONFIRMATION_FOOTER = (
    "Reply Yes to proceed with this investment in MetaMask, or No to cancel."
)


def _format_token_count(raw: Any) -> str:
    try:
        value = float(str(raw or "0"))
    except (TypeError, ValueError):
        return "0"
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _format_eth_amount(raw: Any) -> str:
    return format_chat_stat_eth_amount(raw)


def _property_name_line(prop: dict[str, Any]) -> str:
    name = str(prop.get("name") or f"Property {prop.get('id')}")
    pid = prop.get("id")
    return f"Property Name: {name} (#{pid})"


def _location_line(prop: dict[str, Any]) -> str:
    location = str(prop.get("location") or "").strip()
    return f"Location: {location or '—'}"


def _monthly_rent_line(prop: dict[str, Any]) -> str:
    try:
        monthly_rent = float(prop.get("monthly_rent_eth") or 0)
    except (TypeError, ValueError):
        monthly_rent = 0.0
    if monthly_rent > 0:
        return f"Monthly Rent: {_format_eth_amount(monthly_rent)} ETH"
    return "Monthly Rent: —"


def _tokens_available_line(prop: dict[str, Any]) -> str:
    return f"Tokens Available: {_format_token_count(prop.get('tokens_available'))}"


def _token_buying_line(token_amount: int | str) -> str:
    try:
        amount_int = int(token_amount)
    except (TypeError, ValueError):
        amount_int = 0
    label = "token" if amount_int == 1 else "tokens"
    return f"Token buying: {amount_int} {label}"


def _total_amount_line(prop: dict[str, Any], token_amount: int | str) -> str:
    try:
        amount_int = int(token_amount)
        price = float(prop.get("token_sale_price_eth") or 0)
    except (TypeError, ValueError):
        return "Total amount: —"
    if amount_int < 1 or price <= 0:
        return "Total amount: —"
    total = price * amount_int
    return f"Total amount: {_format_eth_amount(total)} ETH"


def format_invest_property_summary_speak(prop: dict[str, Any]) -> str:
    """Property preview shown before collecting the token count."""
    lines = [
        INVEST_PROPERTY_SUMMARY_HEADING,
        _property_name_line(prop),
        _location_line(prop),
        _monthly_rent_line(prop),
        _tokens_available_line(prop),
    ]
    return "\n".join(lines)


def format_invest_order_summary_speak(
    prop: dict[str, Any],
    token_amount: int | str | None,
) -> str:
    """Investment order summary shown at yes/no confirmation."""
    if token_amount is None:
        return format_invest_property_summary_speak(prop)

    lines = [
        INVEST_ORDER_SUMMARY_HEADING,
        _property_name_line(prop),
        _location_line(prop),
        _monthly_rent_line(prop),
        _tokens_available_line(prop),
        _token_buying_line(token_amount),
        _total_amount_line(prop, token_amount),
    ]
    return "\n".join(lines)


def format_invest_confirmation_summary(
    prop: dict[str, Any],
    token_amount: int | str | None,
) -> str:
    """Full invest order summary with yes/no confirmation footer."""
    return f"{format_invest_order_summary_speak(prop, token_amount)}\n\n{INVEST_CONFIRMATION_FOOTER}"
