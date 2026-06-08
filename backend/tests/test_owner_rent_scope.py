"""Owner-scoped rent analytics only include properties the admin created."""
from __future__ import annotations

from unittest.mock import MagicMock

from backend.services.owner_rent_scope import fetch_owner_rent_analytics


def test_fetch_owner_rent_analytics_empty_wallet_returns_zeros():
    cursor = MagicMock()
    result = fetch_owner_rent_analytics(cursor, "")
    assert result.total_rent_collected_wei == "0"
    assert result.total_rent_distributed_wei == "0"
    assert result.total_payments == 0
    assert result.total_distributions == 0
    assert result.active_rentals == 0
    cursor.execute.assert_not_called()


def test_fetch_owner_rent_analytics_scopes_queries_to_owner_wallet():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        {"collected": 100, "cnt": 2},
        {"distributed": 50, "cnt": 1},
        {"cnt": 3},
    ]

    result = fetch_owner_rent_analytics(cursor, "0xAbCdEf0123456789012345678901234567890AbCd")

    assert cursor.execute.call_count == 3
    for call in cursor.execute.call_args_list:
        sql = call.args[0]
        params = call.args[1]
        assert "JOIN properties p" in sql
        assert "LOWER(p.owner_wallet) = LOWER(%s)" in sql
        assert params == ("0xabcdef0123456789012345678901234567890abcd",)

    assert result.total_rent_collected_wei == "100"
    assert result.total_rent_distributed_wei == "50"
    assert result.total_payments == 2
    assert result.total_distributions == 1
    assert result.active_rentals == 3
