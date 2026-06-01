"""Copilot property visibility must match dashboard UI (active + fully created)."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from backend.ai.copilot_property_scope import (
    ACTIVE_PROPERTY_SQL,
    active_property_join,
    active_property_left_join,
    copilot_property_list_meta,
    count_dashboard_listable_active,
    fetch_active_property,
    filter_dashboard_listable_properties,
    property_unavailable_message,
    transaction_excludes_archived_property,
)
from backend.ai.tools import _list_properties


def _row(
    *,
    pid: int,
    name: str,
    token_address: str = "0xabc",
    supply: str = "1000",
    available: str = "1000",
    sold: str = "0",
    is_active: bool = True,
) -> dict:
    return {
        "id": pid,
        "name": name,
        "token_address": token_address,
        "token_supply": Decimal(supply),
        "tokens_available": Decimal(available),
        "tokens_sold": Decimal(sold),
        "is_active": is_active,
    }


def test_active_property_sql_matches_archive_semantics():
    assert "is_active" in ACTIVE_PROPERTY_SQL
    assert "TRUE" in ACTIVE_PROPERTY_SQL


def test_active_property_join_excludes_archived_rows():
    join = active_property_join("p.id = o.property_id")
    assert "JOIN properties p ON p.id = o.property_id" in join
    assert "is_active" in join


def test_active_property_left_join_excludes_archived_rows():
    join = active_property_left_join("p.id = t.property_id")
    assert "LEFT JOIN properties p" in join
    assert "is_active" in join


def test_transaction_excludes_archived_property():
    clause = transaction_excludes_archived_property()
    assert "property_id IS NULL" in clause
    assert "p.id IS NOT NULL" in clause


def test_filter_dashboard_listable_excludes_incomplete_and_archived(monkeypatch):
    cursor = MagicMock()
    rows = [
        _row(pid=1, name="Visible"),
        _row(pid=2, name="No Token", token_address=""),
        _row(pid=3, name="Archived", is_active=False),
        _row(pid=4, name="Pending Inventory", available="500", sold="0"),
    ]

    def fake_enrich(_cursor, item):
        return dict(item)

    monkeypatch.setattr(
        "backend.ai.copilot_property_scope.enrich_property_with_supply",
        fake_enrich,
    )
    monkeypatch.setattr(
        "backend.ai.copilot_property_scope.property_is_dashboard_listable",
        lambda item: bool(str(item.get("token_address") or "").strip())
        and bool(item.get("is_active", True))
        and (item.get("tokens_available", 0) + item.get("tokens_sold", 0))
        >= item.get("token_supply", 0),
    )

    visible = filter_dashboard_listable_properties(cursor, rows)
    assert [r["name"] for r in visible] == ["Visible"]


def test_fetch_active_property_returns_none_for_non_listable(monkeypatch):
    cursor = MagicMock()
    cursor.fetchone.return_value = _row(pid=9, name="Draft", token_address="")

    monkeypatch.setattr(
        "backend.ai.copilot_property_scope.enrich_property_with_supply",
        lambda _c, item: dict(item),
    )
    monkeypatch.setattr(
        "backend.ai.copilot_property_scope.property_is_dashboard_listable",
        lambda _item: False,
    )
    assert fetch_active_property(cursor, 9) is None


def test_fetch_active_property_returns_enriched_when_listable(monkeypatch):
    cursor = MagicMock()
    cursor.fetchone.return_value = _row(pid=1, name="OK")

    monkeypatch.setattr(
        "backend.ai.copilot_property_scope.enrich_property_with_supply",
        lambda _c, item: {**item, "enriched": True},
    )
    monkeypatch.setattr(
        "backend.ai.copilot_property_scope.property_is_dashboard_listable",
        lambda _item: True,
    )
    row = fetch_active_property(cursor, 1)
    assert row["enriched"] is True


def test_list_properties_sql_filters_active():
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "backend.ai.tools.filter_dashboard_listable_properties",
            lambda _c, rows: rows,
        )
        assert _list_properties(cursor) == []
    sql = cursor.execute.call_args[0][0]
    assert ACTIVE_PROPERTY_SQL in sql


def test_copilot_property_list_meta():
    items = [{"id": 1, "name": "Alpha"}, {"id": 2, "name": "Beta"}]
    meta = copilot_property_list_meta(items)
    assert meta["count"] == 2
    assert meta["property_names"] == ["Alpha", "Beta"]
    assert meta["dashboard_visible_only"] is True


def test_count_dashboard_listable_active(monkeypatch):
    cursor = MagicMock()
    cursor.fetchall.return_value = [_row(pid=1, name="A"), _row(pid=2, name="B")]
    monkeypatch.setattr(
        "backend.ai.copilot_property_scope.filter_dashboard_listable_properties",
        lambda _c, rows: rows[:1],
    )
    assert count_dashboard_listable_active(cursor) == 1


def test_property_unavailable_message_mentions_dashboard():
    msg = property_unavailable_message(99)
    assert "99" in msg
    assert "dashboard" in msg.lower()
