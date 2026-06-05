"""Tenant rent confirm must credit each holder's pro-rata share for yield/claim."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from backend.api._helpers import finalize_investor_rent_yield_after_payment


@patch("backend.api._helpers.accrue_investor_rewards")
@patch("backend.api._helpers.rent_contract_supports_accrue", return_value=True)
@patch("backend.api._helpers.backfill_investor_payout_rows_for_distribution", return_value=1)
@patch("backend.api._helpers.get_rent_distribution_breakdown")
@patch("backend.api._helpers.sync_investors_to_contract", return_value=["0xNew"])
@patch("backend.api._helpers.get_web3")
def test_finalize_accrues_investor_missing_from_pay_rent_events(
    mock_web3,
    _sync,
    mock_breakdown,
    _backfill,
    _supports,
    mock_accrue,
):
    mock_web3.return_value.to_checksum_address.side_effect = lambda a: a
    rent_wei = 1_000_000_000_000_000_000
    mock_breakdown.return_value = [
        {"investor": "0xPaid", "payout_wei": rent_wei // 2, "ownership_pct": 50.0},
        {"investor": "0xMissed", "payout_wei": rent_wei // 2, "ownership_pct": 50.0},
    ]
    paid_events = [
        {"args": {"investor": "0xPaid", "amount": rent_wei // 2, "ownershipBps": 5000}},
    ]

    rows = finalize_investor_rent_yield_after_payment(
        MagicMock(),
        mock_web3.return_value,
        property_id=3,
        distribution_id=11,
        rent_amount_wei=rent_wei,
        distribution_tx_hash="0xrent",
        distributed_at=datetime(2026, 6, 1),
        investor_paid_events=paid_events,
    )

    assert rows == 1
    mock_accrue.assert_called_once_with(3, "0xMissed", rent_wei // 2)
