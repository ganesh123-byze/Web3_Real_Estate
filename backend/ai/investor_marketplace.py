"""Investor copilot marketplace browse — intent detection and catalog formatting."""
from __future__ import annotations

import re
from typing import Any

from backend.ai.chat_stat_format import (
    format_chat_stat_eth_amount,
    format_chat_stat_percentage_label,
)
from backend.ai.investor_voice_parsers import normalize_invest_voice_utterance

INVESTOR_MARKETPLACE_CATALOG_HEADING = "Here are the properties open for investment"
_PROPERTY_YIELD_SUMMARY_HEADING = "Yield & returns summary"

_INVEST_TRANSACTIONAL = re.compile(
    r"\b("
    r"(?:please\s+)?(?:buy|purchase)\s+(?:\d+|one|two|three|four|five|a|an|single)\s+tokens?|"
    r"(?:please\s+)?invest\s+(?:\d+|one|two|three|four|five|a|an|single)\s+tokens?\s+(?:in|into|of)\b|"
    r"(?:please\s+)?invest\s+(?:\d+\s+)?(?:tokens?\s+)?(?:in|into|of)\b|"
    r"(?:please\s+)?invest\s+\d+\b|"
    r"open\s+(?:the\s+)?invest(?:ment)?\s+dialog|"
    r"i\s+want\s+to\s+(?:buy|invest)|"
    r"i(?:'d|\s+would)\s+like\s+to\s+(?:buy|invest)|"
    r"let(?:'s|\s+us)\s+invest|"
    r"start\s+investing\s+in|"
    r"put\s+money\s+into|"
    r"buy\s+into\b"
    r")\b",
    re.IGNORECASE,
)

_INVESTOR_MARKETPLACE_BROWSE = re.compile(
    r"(?i)"
    r"(?:\b(?:take\s+me\s+to|go\s+to|open)\s+(?:the\s+)?(?:investor\s+)?marketplace\b)|"
    r"(?:\bbrowse\s+(?:the\s+)?marketplace\b)|"
    r"(?:\bmarketplace\s+(?:opportunities|listings?)\b)|"
    r"(?:\b(?:show|list|what|which).*\bavailable\b.*\b(?:invest|investment|token)\b)|"
    r"(?:\bpropert(?:y|ies).*\b(?:available|to\s+invest|for\s+sale|opportunities)\b)|"
    r"(?:\bavailable\s+propert(?:y|ies).*\b(?:invest|investment)\b)|"
    r"(?:\bwhat(?:'s|\s+is|\s+are)\s+available\s+(?:to\s+)?invest\b)|"
    r"(?:\bcompare\s+propert(?:y|ies)\b)|"
    r"(?:\bbest\s+propert(?:y|ies)\b)|"
    r"(?:\b(?:show|list)\s+me\s+(?:the\s+)?available\s+propert(?:y|ies)\b)"
)


def _normalize_text(text: str) -> str:
    return normalize_invest_voice_utterance(text)


def _format_token_count(raw: Any) -> str:
    try:
        value = float(str(raw or "0"))
    except (TypeError, ValueError):
        return "0"
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def has_marketplace_browse_intent(text: str) -> bool:
    """True when the investor wants to browse marketplace listings — not place an order."""
    utterance = _normalize_text(text)
    if not utterance:
        return False
    if _INVEST_TRANSACTIONAL.search(utterance) and not re.search(
        r"(?i)\b(?:show|list|available|what|which|browse|marketplace|opportunities)\b",
        utterance,
    ):
        return False
    if _INVESTOR_MARKETPLACE_BROWSE.search(utterance):
        return True
    if re.search(r"(?i)\b(?:show|list|what|which).*\bavailable\b", utterance) and re.search(
        r"(?i)\b(?:invest|investment|marketplace|token)\b",
        utterance,
    ):
        return True
    if re.search(r"(?i)\bpropert(?:y|ies)\b", utterance) and re.search(
        r"(?i)\b(?:for\s+sale|to\s+invest|investment\s+opportunities?)\b",
        utterance,
    ):
        return True
    return False


def marketplace_browse_turn_matches(
    utterance: str,
    *,
    quick_action_id: str | None = None,
) -> bool:
    """True when this turn should return the marketplace catalog preflight."""
    if quick_action_id == "investor.marketplace":
        return True
    return has_marketplace_browse_intent(utterance)


def derive_property_yield_metrics(prop: dict[str, Any]) -> dict[str, float] | None:
    """Match investor UI: gross annual yield and net projected yield (66% of gross)."""
    try:
        monthly_rent = float(prop.get("monthly_rent_eth") or 0)
        token_price = float(prop.get("token_sale_price_eth") or 0)
        supply = float(prop.get("token_supply") or 0)
    except (TypeError, ValueError):
        return None
    if monthly_rent <= 0 or token_price <= 0 or supply <= 0:
        return None
    nav_eth = token_price * supply
    annual_rent_eth = monthly_rent * 12
    gross_annual_yield_pct = (annual_rent_eth / nav_eth) * 100
    net_projected_yield_pct = gross_annual_yield_pct * 0.66
    return {
        "gross_annual_yield_pct": gross_annual_yield_pct,
        "net_projected_yield_pct": net_projected_yield_pct,
    }


def _format_property_yield_section(prop: dict[str, Any]) -> list[str]:
    metrics = derive_property_yield_metrics(prop)
    if not metrics:
        try:
            monthly_rent = float(prop.get("monthly_rent_eth") or 0)
        except (TypeError, ValueError):
            monthly_rent = 0.0
        if monthly_rent > 0:
            return [
                f"Monthly rent: {format_chat_stat_eth_amount(monthly_rent)} ETH",
            ]
        return ["Monthly rent: —"]

    lines = [
        _PROPERTY_YIELD_SUMMARY_HEADING,
        f"Monthly rent: {format_chat_stat_eth_amount(prop.get('monthly_rent_eth'))} ETH",
        (
            "Gross annual yield: "
            f"{format_chat_stat_percentage_label(metrics['gross_annual_yield_pct'])}"
        ),
        (
            "Net projected yield: "
            f"{format_chat_stat_percentage_label(metrics['net_projected_yield_pct'])}"
        ),
    ]
    return lines


def format_investor_marketplace_catalog_speak(
    investable: list[dict[str, Any]],
    *,
    total_listed: int,
) -> str:
    """Verbatim marketplace summary for investor browse turns (chat + voice)."""
    if not investable:
        if total_listed <= 0:
            return (
                "There are no properties on the investor marketplace yet. "
                "Check back when property owners list new tokenized assets."
            )
        return (
            f"There are {total_listed} listing(s) on the marketplace, but none are "
            "open for investment right now — tokens may be fully sold or contracts "
            "are still deploying. Ask again later or say which property you want details on."
        )

    lines = [INVESTOR_MARKETPLACE_CATALOG_HEADING, ""]
    for index, prop in enumerate(investable, start=1):
        name = str(prop.get("name") or f"Property {prop.get('id')}")
        pid = prop.get("id")
        location = str(prop.get("location") or "").strip()
        available = _format_token_count(prop.get("tokens_available"))
        token_price = format_chat_stat_eth_amount(prop.get("token_sale_price_eth"))
        sold_pct = format_chat_stat_percentage_label(prop.get("sold_percentage"))

        lines.append(f"Property: {name} (#{pid})")
        lines.append(f"Location: {location or '—'}")
        lines.append(f"Sale progress: {sold_pct} sold")
        lines.append(f"Tokens available: {available}")
        if token_price and token_price not in ("0", "0.0"):
            raw_price = str(prop.get("token_sale_price_eth") or "").strip()
            fractional = raw_price.split(".")[-1] if "." in raw_price else ""
            if len(fractional.rstrip("0")) > 2:
                lines.append(f"Price per token: {token_price} ETH/token")
            else:
                lines.append(f"Price per token: {token_price} ETH")
        else:
            lines.append("Price per token: —")
        lines.extend(_format_property_yield_section(prop))
        if index < len(investable):
            lines.append("")

    lines.extend(
        [
            "",
            "I've opened the marketplace. Say which property you'd like to invest in "
            "(name or #id), or ask for more details on any listing above.",
        ]
    )
    return "\n".join(lines)
