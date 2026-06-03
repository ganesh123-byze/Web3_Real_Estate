"""Admin transaction list is scoped to properties the signed-in owner created."""
from __future__ import annotations

from backend.api._helpers import append_sql_owned_property_filter


def test_append_sql_owned_property_filter_adds_owner_match():
    conditions: list[str] = []
    params: list = []
    append_sql_owned_property_filter(
        conditions,
        params,
        wallet="0xAbCdEf0123456789012345678901234567890AbCd",
    )
    assert len(conditions) == 1
    assert "owner_wallet" in conditions[0]
    assert params == ["0xabcdef0123456789012345678901234567890abcd"]


def test_append_sql_owned_property_filter_skips_empty_wallet():
    conditions: list[str] = []
    params: list = []
    append_sql_owned_property_filter(conditions, params, wallet="")
    assert conditions == []
    assert params == []
