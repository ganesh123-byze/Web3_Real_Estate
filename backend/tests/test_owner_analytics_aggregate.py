"""Owner analytics wei aggregates must not use DECIMAL(36,18) on wei columns."""
from backend.ai.owner_analytics_aggregate import fetch_owner_investment_volume
from backend.services.wei_aggregate_sql import sum_varchar_wei_sql


def test_sum_varchar_wei_sql_uses_decimal_36_0():
    sql = sum_varchar_wei_sql("t.amount_spent", alias="spent_wei")
    assert "DECIMAL(36,0)" in sql
    assert "DECIMAL(36,18)" not in sql
    assert "spent_wei" in sql


def test_fetch_owner_investment_volume_uses_safe_wei_sum():
    class FakeCursor:
        def __init__(self):
            self.last_query = ""

        def execute(self, query, _params):
            self.last_query = query

        def fetchone(self):
            return {"n": 2, "spent_wei": 5_000_000_000_000_000_000}

    cursor = FakeCursor()
    count, wei = fetch_owner_investment_volume(cursor, "0xOwner")
    assert count == 2
    assert wei == 5_000_000_000_000_000_000
    assert "DECIMAL(36,0)" in cursor.last_query
    assert "DECIMAL(36,18)" not in cursor.last_query
    assert "INVESTMENT_COMPLETED" in cursor.last_query
