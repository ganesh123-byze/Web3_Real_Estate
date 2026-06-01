"""Copilot must not surface archived (is_active=false) properties."""
from __future__ import annotations

from unittest.mock import MagicMock

from backend.ai.copilot_property_scope import (
    ACTIVE_PROPERTY_SQL,
    active_property_join,
    active_property_left_join,
    fetch_active_property,
    property_unavailable_message,
    transaction_excludes_archived_property,
)
from backend.ai.tools import _list_properties


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


def test_fetch_active_property_queries_active_only():
    cursor = MagicMock()
    cursor.fetchone.return_value = {"id": 1, "is_active": True}
    row = fetch_active_property(cursor, 42)
    assert row["id"] == 1
    sql = cursor.execute.call_args[0][0]
    assert "is_active" in sql
    assert cursor.execute.call_args[0][1] == (42,)


def test_fetch_active_property_returns_none_when_archived():
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    assert fetch_active_property(cursor, 7) is None


def test_list_properties_sql_filters_active():
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    assert _list_properties(cursor) == []
    sql = cursor.execute.call_args[0][0]
    assert ACTIVE_PROPERTY_SQL in sql


def test_property_unavailable_message_mentions_archived():
    msg = property_unavailable_message(99)
    assert "99" in msg
    assert "archived" in msg.lower()
