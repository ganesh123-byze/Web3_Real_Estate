"""Late investor (buys after rent paid) should receive proportional backfilled yield."""
from decimal import Decimal
from unittest.mock import MagicMock, patch

from backend.api._helpers import backfill_missed_rent_accruals, build_rent_distribution_preview_from_db


def test_build_rent_distribution_splits_50_50_between_two_holders():
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {"wallet_address": "0xInvestorX", "token_amount": Decimal("500")},
        {"wallet_address": "0xInvestorY", "token_amount": Decimal("500")},
    ]
    rent_wei = 500_000_000_000_000_000  # 0.5 ETH
    rows = build_rent_distribution_preview_from_db(cursor, 1, rent_wei)
    assert len(rows) == 2
    payouts = {r["investor"]: r["payout_wei"] for r in rows}
    assert payouts["0xInvestorX"] == rent_wei // 2
    assert payouts["0xInvestorY"] == rent_wei // 2


@patch("backend.api._helpers.accrue_investor_rewards")
@patch("backend.api._helpers.rent_contract_supports_accrue", return_value=True)
@patch("backend.api._helpers.get_rent_property_info")
@patch("backend.api._helpers.get_web3")
def test_backfill_credits_investor_with_no_prior_payout_row(
    mock_web3,
    mock_rent_info,
    _supports_accrue,
    mock_accrue,
):
    mock_web3.return_value.to_checksum_address.side_effect = lambda a: a
    mock_rent_info.return_value = {"active": True}

    cursor = MagicMock()
    # One past distribution: 0.5 ETH rent
    cursor.fetchall.side_effect = [
        [
            {
                "distribution_id": 10,
                "total_rent_collected": "500000000000000000",
                "distribution_tx_hash": "0xrent",
                "distributed_at": "2026-01-01",
            }
        ],
        # token holders for build_rent_distribution_preview_from_db
        [
            {"wallet_address": "0xInvestorX", "token_amount": Decimal("500")},
            {"wallet_address": "0xInvestorY", "token_amount": Decimal("500")},
        ],
    ]
    # X already paid; Y missing
    cursor.fetchone.return_value = None

    credited = backfill_missed_rent_accruals(cursor, 1, ["0xInvestorY"])
    assert len(credited) == 1
    assert credited[0]["investor_wallet"] == "0xInvestorY"
    assert int(credited[0]["amount_wei"]) == 250_000_000_000_000_000
    mock_accrue.assert_called_once()
    args = mock_accrue.call_args[0]
    assert args[0] == 1
    assert args[1] == "0xInvestorY"
    assert args[2] == 250_000_000_000_000_000


@patch("backend.api._helpers.rent_contract_supports_accrue", return_value=True)
@patch("backend.api._helpers.get_rent_property_info")
@patch("backend.api._helpers.get_web3")
def test_backfill_skips_investor_already_fully_paid(mock_web3, mock_rent_info, _supports):
    mock_web3.return_value.to_checksum_address.side_effect = lambda a: a
    mock_rent_info.return_value = {"active": True}

    cursor = MagicMock()
    cursor.fetchall.side_effect = [
        [
            {
                "distribution_id": 10,
                "total_rent_collected": "500000000000000000",
                "distribution_tx_hash": "0xrent",
                "distributed_at": "2026-01-01",
            }
        ],
        [
            {"wallet_address": "0xInvestorX", "token_amount": Decimal("500")},
            {"wallet_address": "0xInvestorY", "token_amount": Decimal("500")},
        ],
    ]
    cursor.fetchone.return_value = {"payout_amount_wei": "250000000000000000"}

    with patch("backend.api._helpers.accrue_investor_rewards") as mock_accrue:
        credited = backfill_missed_rent_accruals(cursor, 1, ["0xInvestorY"])
    assert credited == []
    mock_accrue.assert_not_called()
