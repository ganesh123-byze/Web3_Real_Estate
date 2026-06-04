"""Tenant copilot: pay rent by property #id, not ambiguous name lists."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import backend.ai.tools as tools
from backend.ai.investor_guards import has_investor_portfolio_intent
from backend.ai.tenant_guards import (
    extract_pay_rent_property_hint_from_utterance,
    has_explicit_pay_rent_intent,
    pay_rent_utterance_names_property,
)
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
    base = {
        "rent_enabled": True,
        "monthly_rent_wei": "1000000000000000000",
        "token_address": "0x00000000000000000000000000000000000000aa",
    }
    return [
        {**base, "id": 4, "name": "Eiffel Crown Residences", "location": "Paris"},
        {**base, "id": 7, "name": "Siddiq Villa", "location": "Texas"},
    ]


def test_extract_pay_rent_hint_from_hash_id():
    assert extract_pay_rent_property_hint_from_utterance("pay the rent #4") == "#4"
    assert extract_pay_rent_property_hint_from_utterance("property #7") == "#7"


def test_has_explicit_pay_rent_intent():
    assert has_explicit_pay_rent_intent("pay the rent #4") is True
    assert has_explicit_pay_rent_intent("when is my rent due") is False


def test_pay_rent_quick_action_does_not_name_property():
    utterance = "I want to pay this month's rent."
    assert extract_pay_rent_property_hint_from_utterance(utterance) == ""
    assert pay_rent_utterance_names_property(utterance) is False


def test_try_server_pay_rent_quick_action_asks_for_property(monkeypatch):
    token = tools.set_current_thread_id("test:tenant-pay-rent-ask")
    msg_token = tools.set_current_messages(
        [{"type": "human", "content": "I want to pay this month's rent."}]
    )
    try:
        tools._clear_workflow_session("PAY_RENT")
        with patch.object(tools, "canonical_role", return_value="tenant"):
            result = asyncio.run(tools.try_server_tenant_pay_rent_turn(_tenant(), None))
        assert result is not None
        assert result.ok
        assert result.data.get("next_field") == "property_name"
        assert "which property" in (result.data.get("speak_to_user") or "").lower()
        assert not result.data.get("submitted")
    finally:
        tools._clear_workflow_session("PAY_RENT")
        tools.reset_current_thread_id(token)
        tools.reset_current_messages(msg_token)


def test_resolve_rentable_property_by_hash_id(monkeypatch):
    monkeypatch.setattr(tools, "_validate_property_rentable", lambda _p: None)
    prop, err = tools._resolve_rentable_property_from_items(
        _rentable_items(), "pay the rent #4"
    )
    assert err is None
    assert prop is not None
    assert int(prop["id"]) == 4


def test_resolve_rentable_property_hash_only(monkeypatch):
    monkeypatch.setattr(tools, "_validate_property_rentable", lambda _p: None)
    prop, err = tools._resolve_rentable_property_from_items(_rentable_items(), "#7")
    assert err is None
    assert int(prop["id"]) == 7


def test_try_server_pay_rent_turn_submits_for_hash_id(monkeypatch):
    token = tools.set_current_thread_id("test:tenant-pay-rent-4")
    msg_token = tools.set_current_messages(
        [{"type": "human", "content": "pay the rent #4"}]
    )
    try:
        tools._clear_workflow_session("PAY_RENT")
        monkeypatch.setattr(tools, "_validate_property_rentable", lambda _p: None)
        def _fake_resolve(_db, name, tenant_wallet=None):
            return tools._resolve_rentable_property_from_items(_rentable_items(), name)

        monkeypatch.setattr(tools, "_resolve_property_for_rent", _fake_resolve)

        async def _fake_execute(pid, _user, _db):
            return tools.ToolResult(
                ok=True,
                data={"speak_to_user": "Confirm in MetaMask.", "submitted": True},
                actions=tools._pay_rent_actions_on_submit(pid),
            )

        monkeypatch.setattr(tools, "_execute_pay_rent_ui", _fake_execute)
        with patch.object(tools, "canonical_role", return_value="tenant"):
            result = asyncio.run(tools.try_server_tenant_pay_rent_turn(_tenant(), None))
        assert result is not None
        assert result.ok
        assert int((result.data or {}).get("property_id") or 0) == 4
        assert any(a.type == "SUBMIT_FORM" for a in (result.actions or []))
    finally:
        tools._clear_workflow_session("PAY_RENT")
        tools.reset_current_thread_id(token)
        tools.reset_current_messages(msg_token)
