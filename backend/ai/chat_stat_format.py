"""Shared number formatting for copilot chat stats (text + voice).

Keeps percentages, ETH amounts, and other decimals readable — never more than
three digits after the decimal point unless the value is a whole number.
"""
from __future__ import annotations

import math
import re
from typing import Any

CHAT_STAT_MAX_DECIMALS = 3


def format_chat_stat_number(
    raw: Any,
    *,
    max_decimals: int = CHAT_STAT_MAX_DECIMALS,
) -> str:
    """Format a numeric stat for chat display (no unit suffix)."""
    text = str(raw or "0").strip().replace("%", "").replace(",", "")
    if not text:
        return "0"
    try:
        value = float(text)
    except (TypeError, ValueError):
        return str(raw).strip() if raw not in (None, "") else "0"
    if not math.isfinite(value):
        return "0"
    if value == int(value):
        return str(int(value))
    places = max(0, int(max_decimals))
    formatted = f"{value:.{places}f}".rstrip("0").rstrip(".")
    return formatted or "0"


def format_chat_stat_percentage(
    raw: Any,
    *,
    max_decimals: int = CHAT_STAT_MAX_DECIMALS,
) -> str:
    """Percentage value without a trailing % sign."""
    return format_chat_stat_number(raw, max_decimals=max_decimals)


def format_chat_stat_eth_amount(
    raw: Any,
    *,
    max_decimals: int = CHAT_STAT_MAX_DECIMALS,
) -> str:
    """ETH amount for inline chat stats (no 'ETH' suffix)."""
    return format_chat_stat_number(raw, max_decimals=max_decimals)


def format_chat_stat_percentage_label(
    raw: Any,
    *,
    max_decimals: int = CHAT_STAT_MAX_DECIMALS,
) -> str:
    """Percentage with % suffix, e.g. '8.333%'."""
    return f"{format_chat_stat_percentage(raw, max_decimals=max_decimals)}%"


_LONG_DECIMAL_RE = re.compile(r"(?<![\d.])(\d+\.\d{4,})(?![\d])")


def normalize_chat_stat_text(
    text: str,
    *,
    max_decimals: int = CHAT_STAT_MAX_DECIMALS,
) -> str:
    """Normalize any long decimal literals embedded in a chat line."""
    if not text:
        return ""

    def _replace(match: re.Match[str]) -> str:
        return format_chat_stat_number(match.group(1), max_decimals=max_decimals)

    return _LONG_DECIMAL_RE.sub(_replace, text)
