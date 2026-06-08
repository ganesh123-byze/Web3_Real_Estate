"""Tests for copilot chat stat number formatting."""
from __future__ import annotations

from backend.ai.chat_stat_format import (
    format_chat_stat_eth_amount,
    format_chat_stat_number,
    format_chat_stat_percentage,
    format_chat_stat_percentage_label,
    normalize_chat_stat_text,
)


def test_format_chat_stat_number_whole_values():
    assert format_chat_stat_number(50) == "50"
    assert format_chat_stat_number("12.0") == "12"
    assert format_chat_stat_number("0") == "0"


def test_format_chat_stat_number_caps_decimals_at_three():
    assert format_chat_stat_number("8.33333333333333333333333333333333") == "8.333"
    assert format_chat_stat_number("0.13333333333333334") == "0.133"
    assert format_chat_stat_number("25.8976") == "25.898"


def test_format_chat_stat_percentage_strips_percent_sign():
    assert format_chat_stat_percentage("12.5%") == "12.5"
    assert format_chat_stat_percentage_label("8.333333333333333") == "8.333%"


def test_format_chat_stat_eth_amount():
    assert format_chat_stat_eth_amount("0.200000000000000000") == "0.2"
    assert format_chat_stat_eth_amount("8.897") == "8.897"


def test_normalize_chat_stat_text_rewrites_long_decimals():
    raw = (
        "Marina Bay Heights (#8) - 8.33333333333333333333333333333333% sold, "
        "0.13333333333333334 ETH/token"
    )
    out = normalize_chat_stat_text(raw)
    assert "8.33333333333333333333333333333333" not in out
    assert "8.333" in out
    assert "0.13333333333333334" not in out
    assert "0.133" in out
