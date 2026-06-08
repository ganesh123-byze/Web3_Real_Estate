"""Invest workflow must not load archived properties."""
from __future__ import annotations

from unittest.mock import MagicMock

from backend.ai.tools import _load_invest_property_row


def test_load_invest_property_row_returns_none_for_archived(monkeypatch):
    db = MagicMock()
    cursor = MagicMock()
    db.cursor.return_value = cursor

    monkeypatch.setattr(
        "backend.ai.tools.fetch_copilot_property",
        lambda _cursor, _pid: None,
    )

    assert _load_invest_property_row(db, 42) is None
    db.cursor.assert_called_once()
