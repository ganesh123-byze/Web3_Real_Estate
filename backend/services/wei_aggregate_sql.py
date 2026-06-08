"""Safe SQL helpers for summing on-chain wei values stored as VARCHAR."""

from __future__ import annotations


def sum_varchar_wei_sql(column: str, *, alias: str = "total_wei") -> str:
    """
    Sum wei columns without DECIMAL(36,18) overflow.

    Wei integers are stored as VARCHAR and can exceed 10^18 (1 ETH in wei).
    DECIMAL(36,18) only allows 18 integer digits, so always aggregate wei as
    DECIMAL(36,0) and convert to ETH in application code.
    """
    col = column.strip()
    return f"COALESCE(SUM(CAST({col} AS DECIMAL(36,0))), 0) AS {alias}"
