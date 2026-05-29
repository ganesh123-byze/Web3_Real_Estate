"""Tests for admin dashboard list visibility after property create."""
from __future__ import annotations

from decimal import Decimal

from backend.api._helpers import property_is_dashboard_listable
from backend.api.routers.properties import _property_stream_done_event


def test_property_is_dashboard_listable_requires_token_and_inventory():
    assert property_is_dashboard_listable(
        {
            "token_address": "0xabc",
            "token_supply": Decimal("1000"),
            "tokens_available": Decimal("1000"),
            "tokens_sold": Decimal("0"),
        }
    )
    assert not property_is_dashboard_listable(
        {
            "token_address": "",
            "token_supply": Decimal("1000"),
            "tokens_available": Decimal("1000"),
            "tokens_sold": Decimal("0"),
        }
    )
    assert not property_is_dashboard_listable(
        {
            "token_address": "0xabc",
            "token_supply": Decimal("1000"),
            "tokens_available": Decimal("500"),
            "tokens_sold": Decimal("0"),
        }
    )


def test_stream_done_event_exposes_id_only_on_terminal_step():
    final = {
        "id": 42,
        "name": "Harbor",
        "token_address": "0xabc",
        "token_supply": Decimal("1000"),
        "tokens_available": Decimal("1000"),
        "tokens_sold": Decimal("0"),
    }
    event = _property_stream_done_event(42, final)
    assert event["step"] == "done"
    assert event["property_id"] == 42
    assert event["property"]["id"] == 42
    assert event.get("list_refresh") is True
