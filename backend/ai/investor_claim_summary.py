"""Investor guided claim summary — confirmation card before MetaMask."""
from __future__ import annotations

from typing import Any

from backend.ai.chat_stat_format import format_chat_stat_eth_amount

CLAIM_YIELD_SUMMARY_HEADING = "Yield claim summary"

CLAIM_CONFIRMATION_FOOTER = (
    "Reply Yes to claim this yield in MetaMask, or No to cancel."
)


def format_claim_confirmation_summary(claim_row: dict[str, Any]) -> str:
    """Formatted yes/no summary for a single claimable property."""
    name = str(claim_row.get("property_name") or f"Property {claim_row.get('property_id')}")
    pid = claim_row.get("property_id")
    amount = format_chat_stat_eth_amount(claim_row.get("claimable_amount_eth") or "0")
    pending = int(claim_row.get("pending_payouts") or 0)
    pending_label = "accrual" if pending == 1 else "accruals"
    lines = [
        CLAIM_YIELD_SUMMARY_HEADING,
        f"Property: {name} (#{pid})",
        f"Claimable yield: {amount} ETH",
        f"Pending {pending_label}: {pending}",
        CLAIM_CONFIRMATION_FOOTER,
    ]
    return "\n".join(lines)
