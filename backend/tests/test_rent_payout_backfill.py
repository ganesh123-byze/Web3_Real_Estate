"""Rent confirm must index investor yield rows when InvestorPaid events are missing."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from backend.api._helpers import backfill_investor_payout_rows_for_distribution


@patch("backend.api._helpers.calculate_rent_distribution")
@patch("backend.api._helpers.get_web3")
def test_backfill_inserts_rows_when_distribution_has_no_payouts(mock_web3, mock_calc):
    mock_web3.return_value.to_checksum_address.side_effect = lambda a: a
    mock_calc.return_value = [
        {
            "investor": "0xInvestorA",
            "payout_wei": 300_000_000_000_000_000,
            "ownership_pct": 60.0,
        },
        {
            "investor": "0xInvestorB",
            "payout_wei": 200_000_000_000_000_000,
            "ownership_pct": 40.0,
        },
    ]

    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        {"row_count": 0},
        None,
        None,
    ]
    cursor.rowcount = 1

    ts = datetime(2026, 6, 1, 12, 0, 0)
    written = backfill_investor_payout_rows_for_distribution(
        cursor,
        mock_web3.return_value,
        property_id=4,
        distribution_id=99,
        rent_amount_wei=500_000_000_000_000_000,
        distribution_tx_hash="0xrent",
        distributed_at=ts,
    )

    assert written == 2
    assert cursor.execute.call_count >= 3
    mock_calc.assert_called_once_with(4, 500_000_000_000_000_000)


@patch("backend.api._helpers.calculate_rent_distribution")
@patch("backend.api._helpers.get_web3")
def test_backfill_skips_when_payout_rows_already_exist(mock_web3, mock_calc):
    mock_web3.return_value.to_checksum_address.side_effect = lambda a: a
    cursor = MagicMock()
    cursor.fetchone.return_value = {"row_count": 2}

    written = backfill_investor_payout_rows_for_distribution(
        cursor,
        mock_web3.return_value,
        property_id=4,
        distribution_id=99,
        rent_amount_wei=500_000_000_000_000_000,
        distribution_tx_hash="0xrent",
        distributed_at=datetime(2026, 6, 1, 12, 0, 0),
    )

    assert written == 0
    mock_calc.assert_not_called()
