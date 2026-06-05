"""Tenant guided pay-rent: property name → confirmation → MetaMask."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import backend.ai.tools as tools
from backend.services.auth import AuthUser


def _tenant() -> AuthUser:
    return AuthUser(
        id=20,
        wallet_address="0x0000000000000000000000000000000000000020",
        role="tenant",
        email=None,
        kyc_status="verified",
        active=True,
    )


def _rentable_items() -> list[dict]:
    return [
        {
            "id": 4,
            "name": "Eiffel Crown Residences",
            "location": "Paris",
            "rent_enabled": True,
            "monthly_rent_eth": "1",
            "token_address": "0xabc",
        }
    ]


def test_pay_rent_asks_property_then_waits_for_confirmation(monkeypatch):
    token = tools.set_current_thread_id("test:pay-rent:confirm-flow")
    try:
        tools._clear_workflow_session("PAY_RENT")
        monkeypatch.setattr(tools, "_validate_property_rentable", lambda _p: None)
        monkeypatch.setattr(
            tools,
            "_resolve_property_for_rent",
            lambda _db, name, tenant_wallet=None: (
                tools._resolve_rentable_property_from_items(_rentable_items(), name)
            ),
        )

        started = asyncio.run(tools._start_pay_rent_property({}, _tenant(), None))
        assert started.ok
        assert started.data.get("next_field") == "property_name"
        assert "which property" in str(started.data.get("speak_to_user") or "").lower()

        filled = asyncio.run(
            tools._fill_pay_rent_property(
                {"property_name": "Eiffel Crown Residences"},
                _tenant(),
                None,
            )
        )
        assert filled.ok
        assert filled.data.get("awaiting_pay_rent_confirmation") is True
        assert filled.data.get("submitted") is False
        assert "Reply Yes" in str(filled.data.get("speak_to_user") or "")
        assert "Eiffel Crown" in str(filled.data.get("speak_to_user") or "")
    finally:
        tools._clear_workflow_session("PAY_RENT")
        tools.reset_current_thread_id(token)


def test_pay_rent_cancels_on_confirmation_no():
    token = tools.set_current_thread_id("test:pay-rent:cancel")
    try:
        tools._clear_workflow_session("PAY_RENT")
        tools._set_workflow_session(
            "PAY_RENT",
            {
                "in_progress": True,
                "awaiting_pay_rent_confirmation": True,
                "filled": {
                    "property_name": "Eiffel Crown Residences",
                    "property_id": "4",
                },
                "property_id": 4,
            },
        )
        result = asyncio.run(
            tools._fill_pay_rent_property({"confirm_pay_rent": False}, _tenant(), None)
        )
        assert result.ok
        assert "cancelled" in str(result.data.get("speak_to_user") or "").lower()
        assert tools._get_workflow_session("PAY_RENT") == {}
    finally:
        tools._clear_workflow_session("PAY_RENT")
        tools.reset_current_thread_id(token)
