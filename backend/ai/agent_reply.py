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
    if data.get("awaiting_create_confirmation"):
        return True
    if data.get("confirmation_summary"):
        return True
    if data.get("chat_property_limit_reached"):
        return True
    if data.get("insufficient_funds"):
        return True
    if data.get("submit_in_flight"):
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
