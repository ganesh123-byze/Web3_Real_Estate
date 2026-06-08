"""Owner portfolio analytics aggregates — safe wei sums for copilot tools."""
from __future__ import annotations

from typing import Any

from backend.ai.copilot_property_scope import active_property_join
from backend.services.wei_aggregate_sql import sum_varchar_wei_sql


def fetch_owner_investment_volume(
    cursor: Any,
    owner_wallet: str,
) -> tuple[int, int]:
    """
    Return (investment_tx_count, total_investment_wei) for the owner's listings.

    Uses transaction ``amount_spent`` (native ETH sent in wei) for
    INVESTMENT_FUNDED / INVESTMENT_COMPLETED rows.
    """
    wallet = (owner_wallet or "").strip()
    if not wallet:
        return 0, 0

    spent_sum = sum_varchar_wei_sql("t.amount_spent", alias="spent_wei")
    cursor.execute(
        f"""
        SELECT COUNT(*) AS n, {spent_sum}
        FROM transactions t
        {active_property_join("p.id = t.property_id")}
        WHERE LOWER(p.owner_wallet) = LOWER(%s)
          AND UPPER(t.type) IN ('INVESTMENT_FUNDED', 'INVESTMENT_COMPLETED')
        """,
        (wallet,),
    )
    row = cursor.fetchone() or {}
    count = int(row.get("n") or 0)
    spent_wei = int(row.get("spent_wei") or 0)
    return count, spent_wei
