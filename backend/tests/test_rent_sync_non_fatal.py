"""Non-fatal rent sync during property finalize (copilot + POST /properties)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.api._helpers import rent_sync_error_is_non_fatal
from backend.api.routers.properties import _finalize_step_sync_rent


def test_rent_sync_error_is_non_fatal_detects_rent_cap():
    exc = HTTPException(
        status_code=409,
        detail="Monthly rent exceeds the on-chain limit of 100 ETH.",
    )
    assert rent_sync_error_is_non_fatal(exc) is not None


def test_rent_sync_error_is_non_fatal_detects_deployer_mismatch():
    exc = HTTPException(
        status_code=409,
        detail={"code": "DEPLOYER_CONTRACT_MISMATCH", "message": "Deployer is not owner."},
    )
    assert "Deployer" in (rent_sync_error_is_non_fatal(exc) or "")


def test_finalize_step_sync_rent_returns_warning_instead_of_raising():
    db = MagicMock()
    cursor = MagicMock()
    db.cursor.return_value = cursor
    cursor.fetchone.return_value = {
        "id": 5,
        "monthly_rent_wei": "78000000000000000000",
        "token_address": "0x" + "a" * 40,
    }

    with patch("backend.api.routers.properties.lock_property", return_value=cursor.fetchone.return_value):
        with patch(
            "backend.api.routers.properties.sync_rent_chain_for_new_property",
            side_effect=HTTPException(
                status_code=500,
                detail="Property was saved but setup failed while syncing rent chain: rent amount too high",
            ),
        ):
            warning = _finalize_step_sync_rent(db, 5)

    assert warning is not None
    assert "rent" in warning.lower()
    db.rollback.assert_called()
