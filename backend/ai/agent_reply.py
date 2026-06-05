"""When tool output must be shown verbatim in chat (not LLM-paraphrased)."""
from __future__ import annotations

from typing import Any


def tool_data_requires_verbatim_reply(data: dict[str, Any] | None) -> bool:
    """True when speak_to_user is authoritative and must not be rewritten by the LLM."""
    if not data:
        return False
    speak = (data.get("speak_to_user") or "").strip()
    if not speak:
        return False
    if data.get("speak_verbatim") is True:
        return True
    if data.get("invalid_field"):
        return True
    if data.get("rent_over_limit"):
        return True
    if data.get("field_accepted"):
        return True
    if data.get("next_field") == "token_symbol" and (data.get("speak_to_user") or "").strip():
        return True
    if data.get("awaiting_create_confirmation"):
        return True
    if data.get("awaiting_invest_confirmation"):
        return True
    if data.get("awaiting_delete_confirmation"):
        return True
    if data.get("confirmation_summary"):
        return True
    if data.get("marketplace_catalog"):
        return True
    if data.get("invest_property_target"):
        return True
    if data.get("investor_portfolio_overview"):
        return True
    if data.get("owner_analytics_overview"):
        return True
    if data.get("owner_investors_overview"):
        return True
    if data.get("owner_rent_overview"):
        return True
    if data.get("insufficient_funds"):
        return True
    if data.get("submit_in_flight"):
        return True
    if data.get("success_message") and data.get("speak_verbatim"):
        return True
    instruction = str(data.get("instruction") or "").lower()
    return "verbatim" in instruction and "speak_to_user" in instruction


def pick_verbatim_speak_to_user(
    tool_results: list[tuple[str, dict[str, Any] | None]],
) -> str | None:
    """Last authoritative speak_to_user across tools executed this turn."""
    chosen: str | None = None
    for _name, data in tool_results:
        if not tool_data_requires_verbatim_reply(data):
            continue
        speak = str((data or {}).get("speak_to_user") or "").strip()
        if speak:
            chosen = speak
    return chosen


def extract_final_reply_from_state(state: dict[str, Any] | None) -> str:
    """Best reply text from a completed agent graph state."""
    if not state:
        return ""
    verbatim = str(state.get("verbatim_reply") or "").strip()
    if verbatim:
        return verbatim
    messages = state.get("messages") or []
    for item in reversed(messages):
        if isinstance(item, dict):
            role = (item.get("type") or item.get("role") or "").lower()
            if role not in ("ai", "assistant"):
                continue
            content = str(item.get("content") or "").strip()
            if content and not item.get("tool_calls"):
                return content
            continue
        content = getattr(item, "content", None)
        if not isinstance(content, str) or not content.strip():
            continue
        tool_calls = getattr(item, "tool_calls", None) or []
        if not tool_calls:
            return content.strip()
    last = messages[-1] if messages else None
    if isinstance(last, dict):
        return str(last.get("content") or "").strip()
    content = getattr(last, "content", None)
    return content.strip() if isinstance(content, str) else ""
