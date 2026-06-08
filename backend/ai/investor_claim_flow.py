"""Investor guided yield-claim workflow — prompts, gating, and preflight routing."""
from __future__ import annotations

import re
from typing import Any, Awaitable, Callable

from backend.ai.investor_guards import (
    claim_workflow_active,
    has_explicit_claim_intent,
    wants_to_begin_claim_workflow,
)
from backend.ai.investor_quick_actions import investor_turn_interrupts_workflow
from backend.ai.workflow_parsers import parse_yes_no_confirmation
from backend.services.auth import AuthUser

CLAIM_PROPERTY_ASK = (
    "Which property would you like to claim yield from? "
    "You can say the property name or #id."
)

CLAIM_PROPERTY_SELECTION_MARKERS = (
    "which property would you like to claim yield from",
    "you can say the property name or #id",
    "claimable yield by property",
    "say which property to claim",
)

_CLAIM_PROPERTY_TAIL = re.compile(
    r"(?i)^(?:please\s+)?claim\s+(?:my\s+|the\s+)?"
    r"(?:rewards|yield|rental\s+yield|earnings?)\s+"
    r"(?:from|on|for)\s+(.+)$"
)

_PROPERTY_ID_IN_UTTERANCE = re.compile(r"(?i)(?:property\s*)?#(\d+)\b")


def claim_property_ask_speak(*, filled: dict[str, str] | None = None) -> str:
    if filled:
        return (
            f"Already collected: {', '.join(f'{k}={v}' for k, v in filled.items())}. "
            "What is the property name?"
        )
    return CLAIM_PROPERTY_ASK


def claim_property_ask_instruction(*, filled: dict[str, str] | None = None) -> str:
    if filled:
        return (
            f"Already collected: {', '.join(f'{k}={v}' for k, v in filled.items())}. "
            "Ask for property_name only — do NOT re-ask fields already in filled."
        )
    return (
        "Read speak_to_user verbatim. Ask only for the property name or #id — "
        "do NOT open MetaMask yet."
    )


def parse_claim_property_from_utterance(text: str) -> str | None:
    """Extract a property hint from 'claim my yield on Sunset Villas' style text."""
    utterance = (text or "").strip()
    if not utterance:
        return None
    tail = _CLAIM_PROPERTY_TAIL.match(utterance)
    if tail:
        hint = tail.group(1).strip()
        return hint or None
    embedded = _PROPERTY_ID_IN_UTTERANCE.search(utterance)
    if embedded and has_explicit_claim_intent(utterance):
        return f"#{embedded.group(1)}"
    return None


def claim_utterance_names_property(
    text: str,
    *,
    quick_action_id: str | None = None,
) -> bool:
    if quick_action_id:
        return False
    utterance = (text or "").strip()
    if not utterance:
        return False
    if parse_claim_property_from_utterance(utterance):
        return True
    if _PROPERTY_ID_IN_UTTERANCE.search(utterance):
        return True
    if re.fullmatch(r"#?\d+", utterance):
        return True
    if has_explicit_claim_intent(utterance):
        return False
    return len(utterance.split()) >= 2 and not utterance.endswith("?")


def assistant_prompted_for_claim_property_selection(messages: list[Any] | None) -> bool:
    from backend.ai.investor_guards import extract_latest_assistant_utterance

    text = extract_latest_assistant_utterance(messages).lower()
    if not text:
        return False
    return any(marker in text for marker in CLAIM_PROPERTY_SELECTION_MARKERS)


def is_claim_property_follow_up_turn(
    utterance: str,
    messages: list[Any] | None,
    *,
    quick_action_id: str | None = None,
) -> bool:
    if not (utterance or "").strip():
        return False
    if not assistant_prompted_for_claim_property_selection(messages):
        return False
    return claim_utterance_names_property(utterance, quick_action_id=quick_action_id)


def investor_turn_interrupts_claim_workflow(
    utterance: str,
    *,
    quick_action_id: str | None = None,
) -> bool:
    if has_explicit_claim_intent(utterance):
        return False
    return investor_turn_interrupts_workflow(utterance, quick_action_id=quick_action_id)


async def run_claim_yield_preflight(
    user: AuthUser,
    db: Any,
    *,
    utterance: str,
    quick_action_id: str | None,
    history: list[Any] | None,
    session: dict[str, Any] | None,
    abort_claim_workflow: Callable[[str], bool],
    ensure_claim_session: Callable[[], Awaitable[Any]],
    fill_claim_yield: Callable[..., Awaitable[Any]],
    enrich_claim_result: Callable[..., Any],
    list_claimable_properties: Callable[[AuthUser, Any], list[dict[str, Any]]],
) -> Any | None:
    """Server-side claim preflight — returns a ToolResult or None."""
    if not utterance:
        return None

    active = claim_workflow_active(session)
    awaiting_confirm = bool(session and session.get("awaiting_claim_confirmation"))
    follow_up = is_claim_property_follow_up_turn(
        utterance, history, quick_action_id=quick_action_id
    )

    if awaiting_confirm:
        yn = parse_yes_no_confirmation(utterance)
        fill_args: dict[str, Any] = {}
        if yn is True:
            fill_args["confirm_claim"] = True
        elif yn is False:
            fill_args["confirm_claim"] = False
        result = await fill_claim_yield(fill_args, user, db)
        return enrich_claim_result(result, db)

    if active:
        if abort_claim_workflow(utterance):
            return None
        hint = parse_claim_property_from_utterance(utterance)
        fill_args: dict[str, str] = {}
        if hint:
            fill_args["property_name"] = hint
        elif follow_up or claim_utterance_names_property(utterance, quick_action_id=quick_action_id):
            fill_args["property_name"] = utterance.strip()
        result = await fill_claim_yield(fill_args, user, db)
        return enrich_claim_result(result, db)

    if abort_claim_workflow(utterance):
        return None
    if investor_turn_interrupts_claim_workflow(utterance, quick_action_id=quick_action_id):
        return None

    if not has_explicit_claim_intent(utterance) and not follow_up:
        return None

    claimable = list_claimable_properties(user, db)
    if not claimable:
        return None

    hint = parse_claim_property_from_utterance(utterance)
    names_property = bool(hint) or claim_utterance_names_property(
        utterance, quick_action_id=quick_action_id
    )

    if len(claimable) == 1 and not names_property:
        row = claimable[0]
        await ensure_claim_session()
        result = await fill_claim_yield(
            {"property_name": str(row.get("property_name") or f"#{row.get('property_id')}")},
            user,
            db,
        )
        return enrich_claim_result(result, db)

    if not names_property and (
        has_explicit_claim_intent(utterance) or wants_to_begin_claim_workflow(utterance)
    ):
        started = await ensure_claim_session()
        return enrich_claim_result(started, db)

    if names_property or follow_up:
        await ensure_claim_session()
        fill_args: dict[str, str] = {}
        if hint:
            fill_args["property_name"] = hint
        elif follow_up or names_property:
            fill_args["property_name"] = utterance.strip()
        result = await fill_claim_yield(fill_args, user, db)
        return enrich_claim_result(result, db)

    return None
