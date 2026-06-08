"""Investor guided-invest workflow — prompts, gating, and preflight routing.

Keeps the invest chat/voice flow server-driven: marketplace browse → property pick
(name or #id) → token amount → yes/no confirmation → MetaMask submit.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from backend.ai.investor_guards import (
    assistant_prompted_for_invest_property_selection,
    has_explicit_invest_intent,
    has_investor_portfolio_intent,
    has_marketplace_browse_intent,
    invest_turn_attempts_decimal_token_amount,
    invest_utterance_names_property,
    invest_workflow_active,
    is_invest_property_follow_up_turn,
    parse_invest_order_from_utterance,
    wants_to_begin_invest_workflow,
)
from backend.ai.investor_quick_actions import investor_turn_interrupts_workflow
from backend.ai.investor_wallet_affordability import has_investor_wallet_affordability_intent
from backend.ai.workflow_parsers import parse_yes_no_confirmation
from backend.services.auth import AuthUser

INVEST_PROPERTY_ASK = (
    "Which property would you like to invest in? "
    "You can say the property name or #id."
)
INVEST_TOKEN_ASK = "How many tokens would you like to buy?"

def is_property_disambiguation_error(message: str | None) -> bool:
    """True when property resolution needs the user to pick among named listings."""
    text = (message or "").strip().lower()
    return (
        "which one do you mean" in text
        or "confirm which property you mean" in text
    )


def disambiguation_candidate_ids(candidates: list[dict[str, Any]]) -> list[int]:
    return [int(prop["id"]) for prop in candidates if prop.get("id") is not None]


INVEST_PROPERTY_SELECTION_MARKERS = (
    "which property would you like to invest in",
    "you can say the property name or #id",
    "here are the properties open for investment",
    "say which property you'd like to invest in",
    "i've opened the marketplace",
)


def may_start_invest_workflow(
    utterance: str,
    messages: list[Any] | None,
    session: dict[str, Any] | None,
    *,
    follow_up: bool = False,
    quick_action_id: str | None = None,
) -> bool:
    """Whether this turn may open or resume the guided invest session."""
    if follow_up:
        return True
    if invest_workflow_active(session):
        return True
    if assistant_prompted_for_invest_property_selection(messages) and invest_utterance_names_property(
        utterance, quick_action_id=quick_action_id
    ):
        return True
    if has_explicit_invest_intent(utterance) or wants_to_begin_invest_workflow(utterance):
        return True
    return False


def invest_property_ask_speak(*, filled: dict[str, str] | None = None) -> str:
    """Verbatim prompt when collecting the invest target property."""
    if filled:
        return (
            f"Already collected: {', '.join(f'{k}={v}' for k, v in filled.items())}. "
            f"What is the property name?"
        )
    return INVEST_PROPERTY_ASK


def invest_property_ask_instruction(*, filled: dict[str, str] | None = None) -> str:
    if filled:
        return (
            f"Already collected: {', '.join(f'{k}={v}' for k, v in filled.items())}. "
            "Ask for property_name only — do NOT re-ask fields already in filled. "
            "Do NOT list every marketplace property."
        )
    return (
        "Read speak_to_user verbatim. Ask only for the property name or #id — "
        "do NOT ask for token count yet and do NOT read the full marketplace catalog."
    )


async def run_invest_property_preflight(
    user: AuthUser,
    db: Any,
    *,
    utterance: str,
    quick_action_id: str | None,
    history: list[Any] | None,
    session: dict[str, Any] | None,
    abort_invest_workflow: Callable[[str], bool],
    ensure_invest_session: Callable[[], Awaitable[Any]],
    fill_invest_property: Callable[..., Awaitable[Any]],
    enrich_invest_result: Callable[..., Any],
) -> Any | None:
    """Server-side invest preflight — returns a ToolResult or None."""
    if not utterance:
        return None

    active = invest_workflow_active(session)
    awaiting_confirm = bool(session and session.get("awaiting_invest_confirmation"))
    follow_up = is_invest_property_follow_up_turn(
        utterance, history, quick_action_id=quick_action_id
    )

    if awaiting_confirm:
        yn = parse_yes_no_confirmation(utterance)
        fill_args: dict[str, Any] = {}
        if yn is True:
            fill_args["confirm_invest"] = True
        elif yn is False:
            fill_args["confirm_invest"] = False
        result = await fill_invest_property(fill_args, user, db)
        return enrich_invest_result(result, db, parsed={})

    if active:
        if abort_invest_workflow(utterance):
            return None
        parsed = parse_invest_order_from_utterance(utterance)
        fill_args = {k: str(v) for k, v in parsed.items() if v not in (None, "")}
        result = await fill_invest_property(fill_args, user, db)
        return enrich_invest_result(result, db, parsed=parsed)

    if abort_invest_workflow(utterance):
        return None
    if has_marketplace_browse_intent(utterance):
        return None
    if has_investor_portfolio_intent(utterance):
        return None
    if has_investor_wallet_affordability_intent(utterance):
        return None
    if investor_turn_interrupts_workflow(utterance, quick_action_id=quick_action_id):
        return None

    if not has_explicit_invest_intent(utterance) and not follow_up:
        return None

    names_property = invest_utterance_names_property(
        utterance, quick_action_id=quick_action_id
    )

    if invest_turn_attempts_decimal_token_amount(utterance):
        if not names_property:
            started = await ensure_invest_session()
            return enrich_invest_result(started, db, parsed={})
        await ensure_invest_session()
        parsed = parse_invest_order_from_utterance(utterance)
        fill_args = {k: str(v) for k, v in parsed.items() if v not in (None, "")}
        result = await fill_invest_property(fill_args, user, db)
        return enrich_invest_result(result, db, parsed=parsed)

    if not names_property and (
        has_explicit_invest_intent(utterance) or wants_to_begin_invest_workflow(utterance)
    ):
        started = await ensure_invest_session()
        return enrich_invest_result(started, db, parsed={})

    parsed = parse_invest_order_from_utterance(utterance)
    fill_args = {k: str(v) for k, v in parsed.items() if v not in (None, "")}

    if not names_property and not follow_up:
        return None

    if names_property or follow_up:
        await ensure_invest_session()

    result = await fill_invest_property(fill_args, user, db)
    return enrich_invest_result(result, db, parsed=parsed)
