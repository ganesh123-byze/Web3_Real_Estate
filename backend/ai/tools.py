"""Tool registry exposed to the LLM.

Each tool is a small, role-gated function that:
* reads real data via the existing services / DB (single source of truth),
* and/or returns ``AgentAction`` objects the frontend should execute.

The LLM never executes any side effects directly — every workflow ends in the
existing MetaMask + modal pipeline, so we keep the same security model the
dashboards already enforce.
"""
from __future__ import annotations

import asyncio
import contextvars
import logging
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any, Awaitable, Callable

from fastapi import HTTPException

from backend.ai.workflow_parsers import (
    assistant_prompted_for_create_field,
    create_property_field_collection_speak,
    create_property_monthly_rent_collection_prompt,
    create_property_monthly_rent_is_skip,
    create_property_monthly_rent_over_limit,
    create_property_monthly_rent_rejection_message,
    format_create_property_confirmation_summary,
    is_generic_create_property_intent,
    normalize_create_property_accumulated,
    normalize_create_property_field,
    parse_yes_no_confirmation,
)
from backend.ai.copilot_property_scope import (
    ACTIVE_PROPERTY_SQL,
    active_property_join,
    active_property_left_join,
    copilot_property_list_meta,
    count_dashboard_listable_active,
    fetch_active_property,
    filter_dashboard_listable_properties,
    property_unavailable_message,
    transaction_excludes_archived_property,
)
from backend.ai.investor_guards import (
    claim_tool_blocked_message,
    extract_last_human_utterance,
    has_explicit_claim_intent,
    has_explicit_invest_intent,
    invest_tool_blocked_message,
    wants_to_begin_invest_workflow,
)
from backend.ai.schemas import AgentAction, ToolResult
from backend.api._helpers import (
    create_property_record,
    enrich_property_with_supply,
    ensure_rent_property_registered,
    format_transaction_row,
    lock_property,
    require_property_token,
    sync_investors_to_contract,
    sync_rent_amount_to_contract,
    validate_monthly_rent_for_chain,
)
from backend.api.schemas import PropertyCreate
from backend.services.tenant_rent_eligibility import (
    build_tenant_property_rent_fields,
    pay_rent_blocked_message,
    tenant_may_pay_rent,
)
from backend.services.tenant_catalog import (
    fetch_tenant_rental_properties,
    filter_tenant_dashboard_available,
)
from backend.services.auth import AuthUser, canonical_role, normalize_address
from backend.services.investment_funding import (
    InvestmentFundingError,
    check_investor_can_fund_investment,
)
from backend.services.rent_payment_funding import (
    RentPaymentFundingError,
    check_tenant_can_pay_monthly_rent,
)

LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conversation context — exposes the current message history to tools that
# need to recover prior state (e.g. fill_create_property accumulating fields
# across turns even when the LLM forgets to pass them all back).
# ---------------------------------------------------------------------------

_current_messages: contextvars.ContextVar[list[Any]] = contextvars.ContextVar(
    "ai_tool_messages", default=[]
)


def set_current_messages(messages: list[Any] | None) -> contextvars.Token:
    """Bind the current conversation history for the duration of a tool turn."""
    return _current_messages.set(messages or [])


def reset_current_messages(token: contextvars.Token) -> None:
    _current_messages.reset(token)


def _current_history() -> list[Any]:
    return _current_messages.get() or []


_current_thread_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "ai_tool_thread_id", default=None
)

# Per-thread workflow state survives across HTTP/voice turns. The client only
# sends user/assistant text (no ToolMessages), and LangGraph checkpoints may
# not retain tool results when the messages channel is rebuilt each request.
_workflow_sessions: dict[str, dict[str, Any]] = {}


def set_current_thread_id(thread_id: str | None) -> contextvars.Token:
    return _current_thread_id.set(thread_id)


def reset_current_thread_id(token: contextvars.Token) -> None:
    _current_thread_id.reset(token)


def _workflow_session_key(modal: str) -> str | None:
    tid = _current_thread_id.get()
    if not tid:
        return None
    return f"{tid}:{modal}"


def _get_workflow_session(modal: str) -> dict[str, Any]:
    key = _workflow_session_key(modal)
    if not key:
        return {}
    return dict(_workflow_sessions.get(key) or {})


def _set_workflow_session(modal: str, data: dict[str, Any]) -> None:
    key = _workflow_session_key(modal)
    if key:
        _workflow_sessions[key] = data


def _clear_workflow_session(modal: str) -> None:
    key = _workflow_session_key(modal)
    if key:
        _workflow_sessions.pop(key, None)


def reset_workflow_sessions_for_thread(
    thread_id: str | None,
    *,
    modal: str | None = None,
) -> int:
    """Drop in-memory workflow drafts for a copilot thread (e.g. after chat refresh)."""
    if not thread_id:
        return 0
    if modal:
        key = f"{thread_id}:{modal}"
        if key in _workflow_sessions:
            _workflow_sessions.pop(key, None)
            return 1
        return 0
    prefix = f"{thread_id}:"
    keys = [key for key in list(_workflow_sessions) if key.startswith(prefix)]
    for key in keys:
        _workflow_sessions.pop(key, None)
    return len(keys)


def _copilot_message_pairs(messages: list[Any]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for msg in messages or []:
        role = _message_role(msg)
        if role not in ("human", "user", "assistant", "ai"):
            continue
        content = _message_content(msg)
        if content:
            pairs.append((role, content))
    return pairs


def copilot_messages_indicate_ui_reset(messages: list[Any]) -> bool:
    """True when the client cleared chat (welcome only, or welcome + one user line)."""
    visible = _copilot_message_pairs(messages)
    if not visible:
        return True
    if len(visible) <= 2 and visible[0][0] in ("assistant", "ai"):
        return True
    return False


def prepare_copilot_turn(
    thread_id: str | None,
    messages: list[Any],
    *,
    explicit_reset: bool = False,
) -> bool:
    """Clear stale workflow caches before an agent turn when the UI started fresh."""
    if explicit_reset or copilot_messages_indicate_ui_reset(messages):
        cleared = reset_workflow_sessions_for_thread(thread_id)
        if cleared:
            LOGGER.info(
                "Cleared %d workflow session(s) for thread %s (explicit_reset=%s)",
                cleared,
                thread_id,
                explicit_reset,
            )
        return True
    return False


def _message_role(msg: Any) -> str:
    if isinstance(msg, dict):
        return (msg.get("type") or msg.get("role") or "").lower()
    role = getattr(msg, "role", None)
    if role is not None:
        return str(role).lower()
    cls = type(msg).__name__.lower()
    if "human" in cls:
        return "human"
    if "ai" in cls or "assistant" in cls:
        return "assistant"
    if "tool" in cls:
        return "tool"
    return ""


def _message_content(msg: Any) -> str:
    if isinstance(msg, dict):
        content = msg.get("content")
    else:
        content = getattr(msg, "content", None)
    return (content or "").strip() if isinstance(content, str) else ""


def _create_property_session_preserves_filled(session: dict[str, Any] | None) -> bool:
    """True when server-side CREATE_PROPERTY draft must survive history recovery."""
    if not session:
        return False
    if session.get("chat_property_limit_reached"):
        return False
    filled = session.get("filled")
    if not filled:
        return False
    if session.get("in_progress"):
        return True
    return bool(
        session.get("awaiting_create_confirmation")
        or session.get("submitting")
        or session.get("submit_failed")
    )


def _latest_human_yes_no_reply() -> bool | None:
    for msg in reversed(_current_history() or []):
        if _message_role(msg) not in ("human", "user"):
            continue
        text = _message_content(msg)
        if not text:
            continue
        return parse_yes_no_confirmation(text)
    return None


def _merge_last_user_utterance(
    accumulated: dict[str, str],
    modal: str,
    fields: tuple[str, ...],
    required: tuple[str, ...],
) -> dict[str, str]:
    """If the LLM omitted the field the user just answered, use the last human line."""
    session = _get_workflow_session(modal)
    if modal == _CREATE_PROPERTY_MODAL and _latest_human_yes_no_reply() is not None:
        return accumulated
    next_field = session.get("next_field")
    missing = [f for f in required if f not in accumulated or not accumulated.get(f)]
    if not next_field and missing:
        next_field = missing[0]
    if not next_field or next_field not in fields or accumulated.get(next_field):
        return accumulated

    hist = _current_history() or []
    last_human_idx: int | None = None
    last_ai_idx: int | None = None
    for i, msg in enumerate(hist):
        role = _message_role(msg)
        if role in ("human", "user"):
            last_human_idx = i
        elif role in ("ai", "assistant"):
            last_ai_idx = i
    # Only use a user line that came after the latest assistant message (the
    # field question). Otherwise we'd treat "create a property" as the name.
    if last_human_idx is None:
        return accumulated
    if last_ai_idx is not None and last_human_idx <= last_ai_idx:
        return accumulated

    text = _message_content(hist[last_human_idx])
    if not text:
        return accumulated

    if modal == _CREATE_PROPERTY_MODAL:
        last_ai_text = (
            _message_content(hist[last_ai_idx]) if last_ai_idx is not None else ""
        )
        if not assistant_prompted_for_create_field(last_ai_text, next_field):
            return accumulated
        if next_field == "name" and is_generic_create_property_intent(text):
            return accumulated

    value = text
    if modal == _CREATE_PROPERTY_MODAL:
        value = normalize_create_property_field(next_field, text)
        if not value:
            return accumulated
    accumulated[next_field] = value
    return accumulated


def _backfill_create_property_filled_from_history(
    accumulated: dict[str, str],
) -> dict[str, str]:
    """Recover answers from chat when the LLM skipped fill_create_property tool calls."""
    out = dict(accumulated)
    field_order = list(_CREATE_PROPERTY_FIELDS)
    hist = _current_history() or []
    pending_field: str | None = None

    for msg in hist:
        role = _message_role(msg)
        text = _message_content(msg)
        if not text:
            continue
        lowered = text.lower()
        if role in ("ai", "assistant"):
            if "reply yes to create and deploy" in lowered or (
                "here are the property details" in lowered
                and ("reply yes" in lowered or "to edit," in lowered)
            ):
                pending_field = None
                continue
            for field in field_order:
                if assistant_prompted_for_create_field(text, field):
                    pending_field = field
                    break
            continue
        if role not in ("human", "user") or not pending_field:
            continue
        if out.get(pending_field) not in (None, ""):
            pending_field = None
            continue
        if parse_yes_no_confirmation(text) is not None:
            pending_field = None
            continue
        if pending_field == "name" and is_generic_create_property_intent(text):
            continue
        if pending_field == "monthly_rent_eth" and create_property_monthly_rent_is_skip(text):
            out[pending_field] = "0"
            pending_field = None
            continue
        value = normalize_create_property_field(pending_field, text)
        if value:
            out[pending_field] = value
        pending_field = None

    return normalize_create_property_accumulated(out)


def _persist_create_property_filled(filled: dict[str, str], **extra: Any) -> None:
    session = _get_workflow_session(_CREATE_PROPERTY_MODAL) or {}
    _set_workflow_session(
        _CREATE_PROPERTY_MODAL,
        {
            **session,
            "in_progress": True,
            "filled": filled,
            **extra,
        },
    )


# ---------------------------------------------------------------------------
# Tool metadata + dispatch
# ---------------------------------------------------------------------------

ToolHandler = Callable[[dict, AuthUser, Any], Awaitable[ToolResult]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict
    roles: frozenset[str]
    handler: ToolHandler


_REGISTRY: dict[str, ToolSpec] = {}


# Friendly nudge when the LLM tries to fire a workflow that belongs to a
# different dashboard. We surface the canonical destination so the agent can
# turn it into a one-sentence explanation instead of saying "I can't do that".
_DASHBOARD_FOR_ROLE = {
    "property_owner": "the property owner dashboard",
    "investor": "the investor dashboard",
    "tenant": "the tenant dashboard",
}


def register(spec: ToolSpec) -> None:
    _REGISTRY[spec.name] = spec


def tools_for_role(role: str) -> list[ToolSpec]:
    """Return only the tools available to ``role``.

    Universal tools (``roles == ALL_ROLES``) are visible to every persona; the
    rest are gated so each agent persona only sees its own surface area.
    """
    r = canonical_role(role)
    return [t for t in _REGISTRY.values() if (not t.roles) or r in t.roles]


def openai_tool_schemas(role: str) -> list[dict]:
    """Return the OpenAI ``tools=[...]`` list filtered by role."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools_for_role(role)
    ]


async def dispatch(name: str, arguments: dict, user: AuthUser, db: Any) -> ToolResult:
    spec = _REGISTRY.get(name)
    if not spec:
        return ToolResult(ok=False, error=f"Unknown tool: {name}")
    role = canonical_role(user.role)
    if spec.roles and role not in spec.roles:
        allowed = sorted(spec.roles)
        # Map the destination dashboards so the agent can explain politely.
        dashboards = sorted({_DASHBOARD_FOR_ROLE.get(r, r) for r in allowed})
        return ToolResult(
            ok=False,
            error=(
                f"This action belongs to {', '.join(dashboards)}. The user is "
                f"signed in as {role.replace('_', ' ')}. Explain that the "
                f"action can only be performed from {dashboards[0]} (politely, "
                "without using the word 'tool')."
            ),
            data={
                "wrong_role": True,
                "required_roles": allowed,
                "current_role": role,
                "destination_dashboards": dashboards,
            },
        )
    try:
        return await spec.handler(arguments or {}, user, db)
    except Exception as exc:  # noqa: BLE001 - tools must never crash the agent loop
        return ToolResult(ok=False, error=str(exc)[:300])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_ROLES = frozenset({"property_owner", "investor", "tenant"})


def _eth(amount_wei: str | int | None, digits: int = 4) -> str:
    if amount_wei in (None, "", "0"):
        return "0"
    try:
        wei = int(str(amount_wei))
    except (TypeError, ValueError):
        return "0"
    return f"{Decimal(wei) / Decimal(10**18):.{digits}f}"


def _serialize_property(row: dict) -> dict:
    return {
        "id": int(row["id"]),
        "name": row.get("name"),
        "location": row.get("location"),
        "token_symbol": row.get("token_symbol"),
        "total_value": str(row.get("total_value") or "0"),
        "token_supply": str(row.get("token_supply") or "0"),
        "tokens_sold": str(row.get("tokens_sold") or "0"),
        "tokens_available": str(row.get("tokens_available") or "0"),
        "sold_percentage": str(row.get("sold_percentage") or "0"),
        "monthly_rent_eth": row.get("monthly_rent_eth"),
        "monthly_rent_wei": str(row.get("monthly_rent_wei") or "0"),
        "rent_enabled": str(row.get("monthly_rent_wei") or "0") not in ("", "0"),
        "owner_wallet": row.get("owner_wallet"),
        "token_address": row.get("token_address"),
    }


def _serialize_tenant_property(row: dict) -> dict:
    """Tenant dashboard row — investors funded, rent cycle, pay eligibility."""
    base = _serialize_property(row)
    base["current_cycle_paid"] = bool(row.get("current_cycle_paid"))
    base["can_pay_rent"] = bool(row.get("can_pay_rent", not base["current_cycle_paid"]))
    base["tenant_paid_current_cycle"] = bool(row.get("tenant_paid_current_cycle"))
    base["rent_claimed_by_other_tenant"] = bool(row.get("rent_claimed_by_other_tenant"))
    base["rent_cycle_label"] = row.get("rent_cycle_label")
    base["active_rental"] = bool(row.get("active_rental"))
    base["has_investors"] = bool(row.get("has_investors"))
    return base


def _tenant_property_items(cursor, tenant_wallet: str | None) -> list[dict]:
    return [
        _serialize_tenant_property(row)
        for row in fetch_tenant_rental_properties(cursor, tenant_wallet=tenant_wallet)
    ]


def _list_properties(cursor) -> list[dict]:
    cursor.execute(
        f"SELECT * FROM properties WHERE {ACTIVE_PROPERTY_SQL} ORDER BY id DESC"
    )
    rows = filter_dashboard_listable_properties(cursor, cursor.fetchall() or [])
    return [_serialize_property(r) for r in rows]


def _normalize_match_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _property_match_score(query: str, prop: dict) -> float:
    q = _normalize_match_text(query)
    if not q:
        return 0
    candidates = [
        prop.get("name"),
        prop.get("location"),
        prop.get("token_symbol"),
        f"{prop.get('name') or ''} {prop.get('location') or ''}",
    ]
    best = 0.0
    for candidate in candidates:
        c = _normalize_match_text(candidate)
        if not c:
            continue
        if q == c:
            best = max(best, 1.0)
        elif q in c or c in q:
            best = max(best, 0.94)
        else:
            best = max(best, SequenceMatcher(None, q, c).ratio())
    return best


def _filter_properties_by_fuzzy_search(items: list[dict], query: str) -> list[dict]:
    scored = [
        (score, prop)
        for prop in items
        if (score := _property_match_score(query, prop)) >= 0.58
    ]
    scored.sort(key=lambda item: (item[0], int(item[1].get("id") or 0)), reverse=True)
    return [prop for _score, prop in scored]


def _resolve_investable_property_from_items(
    items: list[dict], query: str
) -> tuple[dict | None, str | None]:
    """Resolve a spoken property query to a single investable listing."""
    q = (query or "").strip()
    if not q:
        return None, "Property name is required."

    investable: list[dict] = []
    for prop in items:
        if _validate_property_investable(prop) is None:
            investable.append(prop)

    if not investable:
        return None, "No investable properties are available right now."

    ranked = sorted(
        [(_property_match_score(q, p), p) for p in investable],
        key=lambda item: (item[0], int(item[1].get("id") or 0)),
        reverse=True,
    )
    if not ranked:
        return None, "No investable properties are available right now."

    # Strong threshold prevents weak fuzzy matches from picking unrelated properties.
    strong = [(score, prop) for score, prop in ranked if score >= 0.72]
    if not strong:
        best_score, _best_prop = ranked[0]
        if best_score < 0.58:
            examples = ", ".join((p.get("name") or f"#{p.get('id')}") for _, p in ranked[:3])
            return None, (
                f"No investable property found matching {q!r}. "
                f"Try one of: {examples}."
            )
        # Medium-confidence fallback: ask clarification instead of risky auto-pick.
        options = ", ".join((p.get("name") or f"#{p.get('id')}") for _, p in ranked[:3])
        return None, (
            f"Please confirm which property you want: {options}."
        )

    if len(strong) > 1 and (strong[0][0] - strong[1][0]) < 0.08:
        names = ", ".join((p.get("name") or f"#{p.get('id')}") for _, p in strong[:3])
        return None, f"Several investable properties match {q!r}: {names}. Which one do you mean?"

    return strong[0][1], None


def _validate_property_rentable(prop: dict) -> str | None:
    rent_wei = str(prop.get("monthly_rent_wei") or "0")
    if rent_wei in ("", "0"):
        name = prop.get("name") or "This property"
        return f"{name} does not have monthly rent set yet — ask the owner to enable rent first."
    try:
        require_property_token(prop)
    except HTTPException as exc:
        detail = exc.detail
        return str(detail) if detail else "Property token contract is not deployed."
    return None


def _resolve_rentable_property_from_items(
    items: list[dict], query: str
) -> tuple[dict | None, str | None]:
    """Resolve a spoken property query to a single rent-enabled listing."""
    q = (query or "").strip()
    if not q:
        return None, "Property name is required."

    rentable: list[dict] = []
    for prop in items:
        if prop.get("rent_enabled") and _validate_property_rentable(prop) is None:
            rentable.append(prop)

    if not rentable:
        return None, (
            "No rent-enabled properties are available right now. "
            "Ask the owner to set monthly rent on a property first."
        )

    ranked = sorted(
        [(_property_match_score(q, p), p) for p in rentable],
        key=lambda item: (item[0], int(item[1].get("id") or 0)),
        reverse=True,
    )
    strong = [(score, prop) for score, prop in ranked if score >= 0.72]
    if not strong:
        best_score, _best_prop = ranked[0]
        if best_score < 0.58:
            examples = ", ".join((p.get("name") or f"#{p.get('id')}") for _, p in ranked[:3])
            return None, (
                f"No rent-enabled property found matching {q!r}. "
                f"Try one of: {examples}."
            )
        options = ", ".join((p.get("name") or f"#{p.get('id')}") for _, p in ranked[:3])
        return None, f"Please confirm which property you mean: {options}."

    if len(strong) > 1 and (strong[0][0] - strong[1][0]) < 0.08:
        names = ", ".join((p.get("name") or f"#{p.get('id')}") for _, p in strong[:3])
        return None, f"Several rent-enabled properties match {q!r}: {names}. Which one do you mean?"

    return strong[0][1], None


# ---------------------------------------------------------------------------
# Read tools — all roles
# ---------------------------------------------------------------------------


async def _get_my_profile(_args: dict, user: AuthUser, db: Any) -> ToolResult:
    return ToolResult(
        ok=True,
        data={
            "wallet_address": user.wallet_address,
            "role": canonical_role(user.role),
            "email": user.email,
            "kyc_status": user.kyc_status,
        },
    )


register(ToolSpec(
    name="get_my_profile",
    description="Return the current signed-in user's wallet, role, and KYC status.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    roles=ALL_ROLES,
    handler=_get_my_profile,
))


async def _list_properties_tool(args: dict, _user: AuthUser, db: Any) -> ToolResult:
    cursor = db.cursor(dictionary=True)
    try:
        items = _list_properties(cursor)
    finally:
        cursor.close()
    q = (args.get("search") or "").strip()
    if q:
        items = _filter_properties_by_fuzzy_search(items, q)
    rent_only = bool(args.get("rent_enabled_only"))
    if rent_only:
        items = [p for p in items if p["rent_enabled"]]
    payload = {"properties": items[:25], **copilot_property_list_meta(items)}
    return ToolResult(ok=True, data=payload)


async def _list_tenant_properties_tool(args: dict, user: AuthUser, db: Any) -> ToolResult:
    """Properties on the tenant Rentals dashboard — not the investor marketplace."""
    cursor = db.cursor(dictionary=True)
    try:
        raw_rows = fetch_tenant_rental_properties(
            cursor, tenant_wallet=user.wallet_address
        )
    finally:
        cursor.close()

    if bool(args.get("dashboard_available_only")):
        raw_rows = filter_tenant_dashboard_available(raw_rows)
    elif bool(args.get("rent_enabled_only")):
        raw_rows = [row for row in raw_rows if row.get("rent_enabled")]

    items = [_serialize_tenant_property(row) for row in raw_rows]
    q = (args.get("search") or "").strip()
    if q:
        items = _filter_properties_by_fuzzy_search(items, q)

    return ToolResult(
        ok=True,
        data={
            "count": len(items),
            "properties": items[:25],
            "catalog": "tenant_rentals_dashboard",
            "instruction": (
                "These are tenant-dashboard properties (funded by investors, eligible "
                "for rent). This is NOT the investor token marketplace."
            ),
        },
    )


register(ToolSpec(
    name="list_properties",
    description=(
        "List dashboard-visible properties (same as the Properties / Marketplace UI): "
        "active, token deployed, sale inventory finalized. Archived and in-progress "
        "creates are excluded. Use the returned count and property_names — do not guess. "
        "Tenants must use list_tenant_properties instead."
    ),
    parameters={
        "type": "object",
        "properties": {
            "search": {"type": "string", "description": "Optional fuzzy search on property name, location, or token symbol. Handles casing, spaces, punctuation, and small voice transcription mismatches."},
            "rent_enabled_only": {"type": "boolean", "description": "When true, only return properties where the owner has set monthly rent."},
        },
        "additionalProperties": False,
    },
    roles=frozenset({"property_owner", "investor"}),
    handler=_list_properties_tool,
))


register(ToolSpec(
    name="list_tenant_properties",
    description=(
        "List properties shown on the tenant Rentals dashboard — only listings "
        "that already have investor token holders (funded properties). Includes "
        "monthly rent, whether rent is enabled, and this wallet's current-cycle "
        "payment status. NOT the investor marketplace."
    ),
    parameters={
        "type": "object",
        "properties": {
            "search": {
                "type": "string",
                "description": "Optional fuzzy search on property name, location, or token symbol.",
            },
            "rent_enabled_only": {
                "type": "boolean",
                "description": "When true, only properties with monthly rent configured.",
            },
            "dashboard_available_only": {
                "type": "boolean",
                "description": (
                    "When true, match the tenant dashboard Available section: "
                    "has investors, rent enabled, not paid this cycle, and not "
                    "an active rental row for this wallet."
                ),
            },
        },
        "additionalProperties": False,
    },
    roles=frozenset({"tenant"}),
    handler=_list_tenant_properties_tool,
))


# ---------------------------------------------------------------------------
# Investor tools
# ---------------------------------------------------------------------------


async def _get_my_portfolio(_args: dict, user: AuthUser, db: Any) -> ToolResult:
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            f"""
            SELECT p.id AS property_id, p.name AS property_name, p.location,
                   p.token_symbol, p.token_supply,
                   o.token_amount AS token_amount_base
            FROM token_ownerships o
            {active_property_join("p.id = o.property_id")}
            JOIN users u ON u.id = o.user_id
            WHERE LOWER(u.wallet_address) = LOWER(%s) AND o.token_amount > 0
            ORDER BY p.id DESC
            """,
            (user.wallet_address,),
        )
        rows = cursor.fetchall() or []
    finally:
        cursor.close()
    holdings = []
    for r in rows:
        base = int(r.get("token_amount_base") or 0)
        supply = int(r.get("token_supply") or 0)
        # Tokens are 18-decimal ERC-20 — display in whole tokens.
        whole = base // (10 ** 18) if base else 0
        total_supply_whole = supply // (10 ** 18) if supply else 0
        pct = round((whole / total_supply_whole) * 100, 2) if total_supply_whole else 0
        holdings.append({
            "property_id": r["property_id"],
            "property_name": r["property_name"],
            "location": r["location"],
            "token_symbol": r["token_symbol"],
            "token_amount": whole,
            "total_supply": total_supply_whole,
            "ownership_percentage": pct,
        })
    return ToolResult(ok=True, data={"count": len(holdings), "holdings": holdings})


register(ToolSpec(
    name="get_my_portfolio",
    description="Return the signed-in investor's token holdings across every property they own tokens of.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    roles=frozenset({"investor"}),
    handler=_get_my_portfolio,
))


async def _get_my_claimable_rewards(_args: dict, user: AuthUser, db: Any) -> ToolResult:
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            f"""
            SELECT irp.property_id,
                   SUM(CAST(irp.payout_amount_wei AS DECIMAL(36,0))) AS pending_wei,
                   COUNT(*) AS pending_payouts
            FROM investor_rent_payouts irp
            {active_property_join("p.id = irp.property_id")}
            WHERE LOWER(irp.investor_wallet) = LOWER(%s)
              AND COALESCE(irp.claim_status, 'claimable') = 'claimable'
            GROUP BY irp.property_id
            ORDER BY pending_wei DESC
            """,
            (user.wallet_address,),
        )
        rows = cursor.fetchall() or []
    finally:
        cursor.close()
    items = [
        {
            "property_id": int(r["property_id"]),
            "claimable_eth": _eth(int(r["pending_wei"] or 0)),
            "pending_payouts": int(r["pending_payouts"] or 0),
        }
        for r in rows
    ]
    total_eth = _eth(sum(int(r["pending_wei"] or 0) for r in rows))
    return ToolResult(ok=True, data={"total_claimable_eth": total_eth, "properties": items})


register(ToolSpec(
    name="get_my_claimable_rewards",
    description="Return the signed-in investor's claimable rent rewards, grouped by property.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    roles=frozenset({"investor"}),
    handler=_get_my_claimable_rewards,
))


# ---------------------------------------------------------------------------
# Tenant tools
# ---------------------------------------------------------------------------


async def _get_my_active_rentals(_args: dict, user: AuthUser, db: Any) -> ToolResult:
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            f"""
            SELECT tr.id, tr.property_id, p.name AS property_name, p.location,
                   tr.rental_start_date, tr.status
            FROM tenant_rentals tr
            JOIN tenants t ON t.id = tr.tenant_id
            {active_property_join("p.id = tr.property_id")}
            WHERE LOWER(t.wallet_address) = LOWER(%s) AND tr.status = 'active'
            ORDER BY tr.created_at DESC
            """,
            (user.wallet_address,),
        )
        rows = cursor.fetchall() or []
    finally:
        cursor.close()
    rentals = [
        {
            "id": int(r["id"]),
            "property_id": int(r["property_id"]),
            "property_name": r["property_name"],
            "location": r["location"],
            "rental_start_date": r["rental_start_date"].isoformat() if r.get("rental_start_date") else None,
            "status": r["status"],
        }
        for r in rows
    ]
    return ToolResult(ok=True, data={"count": len(rentals), "rentals": rentals})


register(ToolSpec(
    name="get_my_active_rentals",
    description=(
        "Return rentals the tenant has paid rent on at least once (the "
        "tenant_rentals table). NOTE: this does NOT cover properties the "
        "tenant could pay rent on for the first time — for that use "
        "list_tenant_properties (optionally dashboard_available_only=true)."
    ),
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    roles=frozenset({"tenant"}),
    handler=_get_my_active_rentals,
))


async def _get_my_rent_payments(args: dict, user: AuthUser, db: Any) -> ToolResult:
    limit = int(args.get("limit") or 10)
    limit = max(1, min(limit, 50))
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            f"""
            SELECT rp.id, rp.amount_eth, rp.tx_hash, rp.payment_date,
                   rp.payment_status, p.name AS property_name, rp.property_id
            FROM rent_payments rp
            JOIN tenants t ON t.id = rp.tenant_id
            {active_property_join("p.id = rp.property_id")}
            WHERE LOWER(t.wallet_address) = LOWER(%s)
            ORDER BY rp.payment_date DESC
            LIMIT %s
            """,
            (user.wallet_address, limit),
        )
        rows = cursor.fetchall() or []
    finally:
        cursor.close()
    payments = [
        {
            "id": int(r["id"]),
            "property_id": int(r["property_id"]),
            "property_name": r["property_name"],
            "amount_eth": str(r["amount_eth"] or "0"),
            "tx_hash": r["tx_hash"],
            "payment_date": r["payment_date"].isoformat() if r.get("payment_date") else None,
            "payment_status": r["payment_status"],
        }
        for r in rows
    ]
    return ToolResult(ok=True, data={"count": len(payments), "payments": payments})


register(ToolSpec(
    name="get_my_rent_payments",
    description="Return the signed-in tenant's most recent rent payments (default 10, max 50).",
    parameters={
        "type": "object",
        "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}},
        "additionalProperties": False,
    },
    roles=frozenset({"tenant"}),
    handler=_get_my_rent_payments,
))


# ---------------------------------------------------------------------------
# Property-owner tools
# ---------------------------------------------------------------------------


async def _get_my_owned_properties(_args: dict, user: AuthUser, db: Any) -> ToolResult:
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            f"SELECT * FROM properties WHERE LOWER(owner_wallet) = LOWER(%s) "
            f"AND {ACTIVE_PROPERTY_SQL} ORDER BY id DESC",
            (user.wallet_address,),
        )
        rows = filter_dashboard_listable_properties(cursor, cursor.fetchall() or [])
        items = [_serialize_property(r) for r in rows]
    finally:
        cursor.close()
    payload = {"properties": items, **copilot_property_list_meta(items)}
    return ToolResult(ok=True, data=payload)


register(ToolSpec(
    name="get_my_owned_properties",
    description=(
        "Return dashboard-visible properties owned by the signed-in property owner "
        "(same rules as the admin Properties page). Use count and property_names from "
        "the result — do not invent other listings."
    ),
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    roles=frozenset({"property_owner"}),
    handler=_get_my_owned_properties,
))


async def _get_rent_analytics(_args: dict, user: AuthUser, db: Any) -> ToolResult:
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            f"""
            SELECT
              COALESCE(SUM(CAST(rp.amount_wei AS DECIMAL(36,0))), 0) AS collected_wei,
              COUNT(*) AS payments_count
            FROM rent_payments rp
            {active_property_join("p.id = rp.property_id")}
            WHERE LOWER(p.owner_wallet) = LOWER(%s)
            """,
            (user.wallet_address,),
        )
        agg = cursor.fetchone() or {}
        cursor.execute(
            f"SELECT COUNT(*) AS active FROM tenant_rentals tr "
            f"{active_property_join('p.id = tr.property_id')} "
            f"WHERE LOWER(p.owner_wallet) = LOWER(%s) AND tr.status = 'active'",
            (user.wallet_address,),
        )
        active = cursor.fetchone() or {}
    finally:
        cursor.close()
    return ToolResult(
        ok=True,
        data={
            "total_rent_collected_eth": _eth(int(agg.get("collected_wei") or 0)),
            "payments_count": int(agg.get("payments_count") or 0),
            "active_rentals": int(active.get("active") or 0),
        },
    )


register(ToolSpec(
    name="get_rent_analytics",
    description="Aggregate rent metrics across the signed-in property owner's portfolio.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    roles=frozenset({"property_owner"}),
    handler=_get_rent_analytics,
))


async def _get_my_investors(_args: dict, user: AuthUser, db: Any) -> ToolResult:
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            f"""
            SELECT u.wallet_address, u.email,
                   p.id AS property_id, p.name AS property_name, p.token_symbol,
                   p.token_supply, o.token_amount AS token_amount_base
            FROM token_ownerships o
            JOIN users u ON u.id = o.user_id
            {active_property_join("p.id = o.property_id")}
            WHERE LOWER(p.owner_wallet) = LOWER(%s) AND o.token_amount > 0
            ORDER BY p.id DESC, o.token_amount DESC
            """,
            (user.wallet_address,),
        )
        rows = cursor.fetchall() or []
    finally:
        cursor.close()

    by_property: dict[int, dict] = {}
    for r in rows:
        pid = int(r["property_id"])
        base = int(r.get("token_amount_base") or 0)
        supply = int(r.get("token_supply") or 0)
        whole = base // (10 ** 18) if base else 0
        total_whole = supply // (10 ** 18) if supply else 0
        pct = round((whole / total_whole) * 100, 2) if total_whole else 0
        bucket = by_property.setdefault(pid, {
            "property_id": pid,
            "property_name": r["property_name"],
            "token_symbol": r["token_symbol"],
            "investors": [],
        })
        bucket["investors"].append({
            "wallet_address": r["wallet_address"],
            "email": r.get("email"),
            "token_amount": whole,
            "ownership_percentage": pct,
        })

    properties = list(by_property.values())
    total_investors = sum(len(p["investors"]) for p in properties)
    return ToolResult(
        ok=True,
        data={
            "total_investors": total_investors,
            "properties": properties,
        },
    )


register(ToolSpec(
    name="get_my_investors",
    description=(
        "List investors holding tokens of any property owned by the signed-in "
        "property owner, grouped by property."
    ),
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    roles=frozenset({"property_owner"}),
    handler=_get_my_investors,
))


def _build_owner_analytics_overview(cursor, user: AuthUser) -> dict:
    """Aggregate analytics-page metrics for the property-owner copilot."""
    wallet = normalize_address(user.wallet_address or "")

    cursor.execute(
        f"SELECT * FROM properties WHERE {ACTIVE_PROPERTY_SQL} ORDER BY id DESC"
    )
    listable_rows = filter_dashboard_listable_properties(cursor, cursor.fetchall() or [])
    properties = [_serialize_property(r) for r in listable_rows]
    listable_ids = {int(p["id"]) for p in properties if p.get("id") is not None}
    owned = [p for p in properties if wallet and normalize_address(p.get("owner_wallet") or "") == wallet]
    listed_with_sales = [p for p in properties if float(p.get("sold_percentage") or 0) > 0]

    cursor.execute(
        f"""
        SELECT COALESCE(SUM(CAST(rp.amount_wei AS DECIMAL(36,0))), 0) AS collected,
               COUNT(*) AS payments_count
        FROM rent_payments rp
        {active_property_join("p.id = rp.property_id")}
        """
    )
    rent_pay = cursor.fetchone() or {}
    cursor.execute(
        f"""
        SELECT COALESCE(SUM(CAST(rd.total_distributed AS DECIMAL(36,0))), 0) AS distributed,
               COUNT(*) AS distributions_count
        FROM rent_distributions rd
        {active_property_join("p.id = rd.property_id")}
        """
    )
    rent_dist = cursor.fetchone() or {}
    cursor.execute(
        f"""
        SELECT COUNT(*) AS active FROM tenant_rentals tr
        {active_property_join("p.id = tr.property_id")}
        WHERE tr.status = 'active'
        """
    )
    active_rentals = int((cursor.fetchone() or {}).get("active") or 0)

    cursor.execute(
        "SELECT rp.id, rp.property_id, p.name AS property_name, rp.amount_eth, "
        "rp.payment_date, rp.payment_status, t.wallet_address AS tenant_wallet "
        f"FROM rent_payments rp "
        f"JOIN tenants t ON t.id = rp.tenant_id "
        f"{active_property_join('p.id = rp.property_id')} "
        f"ORDER BY rp.payment_date DESC LIMIT 10"
    )
    recent_payments = [
        {
            "property_name": r.get("property_name"),
            "amount_eth": str(r.get("amount_eth") or "0"),
            "tenant_wallet": r.get("tenant_wallet"),
            "payment_date": r["payment_date"].isoformat() if r.get("payment_date") else None,
            "payment_status": r.get("payment_status"),
        }
        for r in (cursor.fetchall() or [])
    ]

    cursor.execute(
        "SELECT rd.property_id, p.name AS property_name, rd.total_distributed, "
        "rd.investor_count, rd.distributed_at "
        f"FROM rent_distributions rd "
        f"{active_property_join('p.id = rd.property_id')} "
        f"ORDER BY rd.distributed_at DESC LIMIT 8"
    )
    recent_distributions = [
        {
            "property_name": r.get("property_name"),
            "total_distributed_eth": _eth(int(r.get("total_distributed") or 0)),
            "investor_count": int(r.get("investor_count") or 0),
            "distributed_at": r["distributed_at"].isoformat() if r.get("distributed_at") else None,
        }
        for r in (cursor.fetchall() or [])
    ]

    cursor.execute(
        "SELECT COUNT(DISTINCT o.user_id) AS n FROM token_ownerships o WHERE o.token_amount > 0"
    )
    platform_investors = int((cursor.fetchone() or {}).get("n") or 0)
    cursor.execute(
        f"""
        SELECT p.id, p.name, COUNT(DISTINCT o.user_id) AS investor_count
        FROM properties p
        LEFT JOIN token_ownerships o ON o.property_id = p.id AND o.token_amount > 0
        WHERE {ACTIVE_PROPERTY_SQL}
        GROUP BY p.id, p.name
        HAVING COUNT(DISTINCT o.user_id) > 0
        ORDER BY investor_count DESC, p.id DESC
        LIMIT 8
        """
    )
    investors_by_property = [
        {
            "property_id": int(r["id"]),
            "property_name": r.get("name"),
            "investor_count": int(r.get("investor_count") or 0),
        }
        for r in (cursor.fetchall() or [])
        if int(r["id"]) in listable_ids
    ]

    cursor.execute(
        "SELECT t.id, t.tx_hash, t.type, t.amount, t.timestamp, t.property_id, "
        "p.name AS property_name, t.amount_spent "
        f"FROM transactions t "
        f"{active_property_left_join('p.id = t.property_id')} "
        f"WHERE 1=1 {transaction_excludes_archived_property()} "
        f"ORDER BY t.timestamp DESC, t.id DESC LIMIT 12"
    )
    recent_transactions = [_format_transaction(r) for r in (cursor.fetchall() or [])]

    cursor.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(CAST(amount_spent AS DECIMAL(36,18))), 0) AS spent "
        "FROM transactions WHERE UPPER(type) IN ('INVESTMENT_FUNDED', 'INVESTMENT_COMPLETED')"
    )
    inv_agg = cursor.fetchone() or {}

    my_investors_data: dict = {}
    if wallet:
        cursor.execute(
            f"""
            SELECT COUNT(DISTINCT o.user_id) AS n
            FROM token_ownerships o
            {active_property_join("p.id = o.property_id")}
            WHERE LOWER(p.owner_wallet) = %s AND o.token_amount > 0
            """,
            (wallet,),
        )
        my_investors_data["investors_on_my_properties"] = int((cursor.fetchone() or {}).get("n") or 0)

    property_perf = sorted(
        [
            {
                "id": p["id"],
                "name": p.get("name"),
                "sold_percentage": p.get("sold_percentage"),
                "tokens_sold": p.get("tokens_sold"),
                "token_supply": p.get("token_supply"),
                "monthly_rent_eth": p.get("monthly_rent_eth"),
            }
            for p in properties
        ],
        key=lambda x: float(x.get("sold_percentage") or 0),
        reverse=True,
    )[:8]

    return {
        "summary": {
            "dashboard_visible_properties": len(properties),
            "total_properties": len(properties),
            "properties_you_own": len(owned),
            "properties_with_token_sales": len(listed_with_sales),
            "property_names": [p.get("name") for p in properties if p.get("name")],
            "platform_investors": platform_investors,
            "active_rentals": active_rentals,
            "total_rent_collected_eth": _eth(int(rent_pay.get("collected") or 0)),
            "rent_payments_count": int(rent_pay.get("payments_count") or 0),
            "total_rent_distributed_eth": _eth(int(rent_dist.get("distributed") or 0)),
            "rent_distributions_count": int(rent_dist.get("distributions_count") or 0),
            "total_investments_recorded": int(inv_agg.get("n") or 0),
            "total_investment_volume_eth": str(inv_agg.get("spent") or "0"),
        },
        "my_portfolio": my_investors_data,
        "property_performance": property_perf,
        "investors_by_property": investors_by_property,
        "recent_rent_payments": recent_payments,
        "recent_rent_distributions": recent_distributions,
        "recent_transactions": recent_transactions,
        "properties": properties[:20],
    }


async def _get_owner_analytics_overview(_args: dict, user: AuthUser, db: Any) -> ToolResult:
    cursor = db.cursor(dictionary=True)
    try:
        data = _build_owner_analytics_overview(cursor, user)
    finally:
        cursor.close()
    return ToolResult(
        ok=True,
        data=data,
        actions=[],
    )


register(ToolSpec(
    name="get_owner_analytics_overview",
    description=(
        "Analytics snapshot aligned with the admin dashboard: summary.dashboard_visible_properties "
        "and summary.property_names match the Properties page. Includes rent collected/distributed, "
        "active rentals, investors by property, recent payments and transactions. Use for "
        "'analytics', 'view analytics', or dashboard overview. Report counts from summary only."
    ),
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    roles=frozenset({"property_owner"}),
    handler=_get_owner_analytics_overview,
))


async def _view_analytics(_args: dict, user: AuthUser, db: Any) -> ToolResult:
    """Alias for analytics requests — same data as get_owner_analytics_overview."""
    return await _get_owner_analytics_overview(_args, user, db)


register(ToolSpec(
    name="view_analytics",
    description=(
        "Return the full analytics overview (properties, rent payments, investors, "
        "transactions) directly in chat. Do NOT navigate pages. Use when the user says "
        "'analytics', 'view analytics', 'show analytics', or taps the View Analytics quick action."
    ),
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    roles=frozenset({"property_owner"}),
    handler=_view_analytics,
))


# ---------------------------------------------------------------------------
# Extended read tools — full read access to every dashboard page
# ---------------------------------------------------------------------------


async def _get_wallet_balance(_args: dict, user: AuthUser, _db: Any) -> ToolResult:
    """Return native ETH balance + property-token balances for the signed-in user."""
    from backend.services.blockchain import (
        from_base_units,
        get_contract,
        get_erc20_balance,
        get_native_balance,
        get_web3,
    )
    from backend.config.settings import TOKEN_DECIMALS

    web3 = get_web3()
    wallet = user.wallet_address
    if not wallet or not web3.is_address(wallet):
        return ToolResult(ok=False, error="No wallet connected.")
    checksum = web3.to_checksum_address(wallet)
    native_wei = int(get_native_balance(checksum))
    native_eth = str(web3.from_wei(native_wei, "ether"))

    tokens: list[dict] = []
    db = _db
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            f"SELECT id, name, token_address, token_symbol "
            f"FROM properties WHERE token_address IS NOT NULL AND {ACTIVE_PROPERTY_SQL}"
        )
        for row in cursor.fetchall() or []:
            addr = row.get("token_address")
            if not addr:
                continue
            try:
                contract = get_contract("SecurityToken", addr)
                base = int(get_erc20_balance(contract, checksum))
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("token balance failed property=%s err=%s", row.get("id"), exc)
                continue
            if base <= 0:
                continue
            tokens.append({
                "property_id": int(row["id"]),
                "property_name": row.get("name"),
                "symbol": row.get("token_symbol"),
                "balance": str(from_base_units(base, TOKEN_DECIMALS)),
            })
    finally:
        cursor.close()
    return ToolResult(
        ok=True,
        data={
            "wallet_address": checksum,
            "eth_balance": native_eth,
            "eth_balance_wei": str(native_wei),
            "property_tokens": tokens,
        },
    )


register(ToolSpec(
    name="get_wallet_balance",
    description=(
        "Return the signed-in user's wallet balances: native ETH and every "
        "property token they hold. Use for questions about wallet balance, "
        "ETH balance, or 'how much ETH do I have'."
    ),
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    roles=ALL_ROLES,
    handler=_get_wallet_balance,
))


def _format_transaction(row: dict) -> dict:
    formatted = format_transaction_row(dict(row))
    ts = formatted.get("timestamp")
    if hasattr(ts, "isoformat"):
        formatted["timestamp"] = ts.isoformat()
    return {
        "id": int(formatted.get("id") or 0),
        "tx_hash": formatted.get("tx_hash"),
        "type": formatted.get("type"),
        "action_label": formatted.get("action_label"),
        "description": formatted.get("description"),
        "display_amount": str(formatted.get("display_amount") or "0"),
        "amount_unit": formatted.get("amount_unit"),
        "property_id": formatted.get("property_id"),
        "property_name": formatted.get("property_name"),
        "wallet_address": formatted.get("wallet_address"),
        "timestamp": formatted.get("timestamp"),
        "amount_spent": formatted.get("amount_spent"),
        "gas_fee": formatted.get("gas_fee"),
    }


async def _get_my_transactions(args: dict, user: AuthUser, db: Any) -> ToolResult:
    limit = max(1, min(int(args.get("limit") or 10), 50))
    tx_type = (args.get("type") or "").strip() or None
    cursor = db.cursor(dictionary=True)
    try:
        conditions = ["LOWER(COALESCE(t.wallet_address, i.investor_wallet)) = LOWER(%s)"]
        params: list = [user.wallet_address]
        if tx_type:
            conditions.append("t.type = %s")
            params.append(tx_type)
        query = (
            "SELECT t.id, t.tx_hash, t.type, t.amount, t.timestamp, t.property_id, "
            "t.block_number, COALESCE(t.wallet_address, i.investor_wallet) AS wallet_address, "
            "t.gas_fee, t.amount_spent, t.remaining_balance, p.name AS property_name "
            f"FROM transactions t "
            f"{active_property_left_join('p.id = t.property_id')} "
            "LEFT JOIN investments i ON LOWER(i.deposit_tx_hash) = LOWER(t.tx_hash) "
            "WHERE " + " AND ".join(conditions) + f" {transaction_excludes_archived_property()} "
            "ORDER BY t.timestamp DESC, t.id DESC LIMIT %s"
        )
        params.append(limit)
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall() or []
    finally:
        cursor.close()
    txs = [_format_transaction(r) for r in rows]
    return ToolResult(ok=True, data={"count": len(txs), "transactions": txs})


register(ToolSpec(
    name="get_my_transactions",
    description=(
        "Recent on-chain transactions involving the signed-in user (invest, "
        "rent paid, claims, transfers). Use for questions like 'show my last "
        "transaction', 'my last 2 transactions', 'recent activity'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "description": "Default 10."},
            "type": {"type": "string", "description": "Optional filter: ISSUE_TOKENS, INVESTMENT_FUNDED, RENT_PAID, REWARDS_CLAIMED, RENT_DISTRIBUTED, TRANSFER, MINT_NFT."},
        },
        "additionalProperties": False,
    },
    roles=ALL_ROLES,
    handler=_get_my_transactions,
))


async def _get_all_transactions(args: dict, _user: AuthUser, db: Any) -> ToolResult:
    limit = max(1, min(int(args.get("limit") or 20), 100))
    tx_type = (args.get("type") or "").strip() or None
    property_id = args.get("property_id")
    cursor = db.cursor(dictionary=True)
    try:
        conditions: list[str] = []
        params: list = []
        if tx_type:
            conditions.append("t.type = %s")
            params.append(tx_type)
        if property_id is not None:
            conditions.append("t.property_id = %s")
            params.append(int(property_id))
        query = (
            "SELECT t.id, t.tx_hash, t.type, t.amount, t.timestamp, t.property_id, "
            "t.block_number, COALESCE(t.wallet_address, i.investor_wallet) AS wallet_address, "
            "t.gas_fee, t.amount_spent, t.remaining_balance, p.name AS property_name "
            f"FROM transactions t "
            f"{active_property_left_join('p.id = t.property_id')} "
            "LEFT JOIN investments i ON LOWER(i.deposit_tx_hash) = LOWER(t.tx_hash) "
        )
        archive_filter = transaction_excludes_archived_property()
        if conditions:
            query += "WHERE " + " AND ".join(conditions) + f" {archive_filter} "
        else:
            query += f"WHERE 1=1 {archive_filter} "
        query += "ORDER BY t.timestamp DESC, t.id DESC LIMIT %s"
        params.append(limit)
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall() or []
    finally:
        cursor.close()
    txs = [_format_transaction(r) for r in rows]
    return ToolResult(ok=True, data={"count": len(txs), "transactions": txs})


register(ToolSpec(
    name="get_all_transactions",
    description=(
        "Platform-wide on-chain transactions across every property. Use for "
        "property-owner analytics like 'last transactions on the platform', "
        "'all transactions for Azure View', or 'recent rent payments'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Default 20."},
            "type": {"type": "string", "description": "Optional transaction type filter."},
            "property_id": {"type": "integer", "description": "Optional property id filter."},
        },
        "additionalProperties": False,
    },
    roles=ALL_ROLES,
    handler=_get_all_transactions,
))


async def _get_property_details(args: dict, _user: AuthUser, db: Any) -> ToolResult:
    pid = args.get("property_id")
    if pid is None:
        return ToolResult(ok=False, error="property_id is required.")
    cursor = db.cursor(dictionary=True)
    try:
        prop = fetch_active_property(cursor, int(pid))
        if not prop:
            return ToolResult(ok=False, error=property_unavailable_message(int(pid)))
        enriched = prop
        cursor.execute(
            "SELECT COUNT(DISTINCT user_id) AS investor_count "
            "FROM token_ownerships WHERE property_id = %s AND token_amount > 0",
            (int(pid),),
        )
        investor_count = int((cursor.fetchone() or {}).get("investor_count") or 0)
        cursor.execute(
            "SELECT COUNT(*) AS active FROM tenant_rentals WHERE property_id = %s AND status = 'active'",
            (int(pid),),
        )
        active = int((cursor.fetchone() or {}).get("active") or 0)
    finally:
        cursor.close()
    base = _serialize_property(enriched)
    base["investor_count"] = investor_count
    base["active_rentals"] = active
    return ToolResult(ok=True, data=base)


register(ToolSpec(
    name="get_property_details",
    description=(
        "Return detailed info on a single property — sale progress, monthly "
        "rent, investor count, active rentals. Resolve the id from "
        "list_tenant_properties (tenant) or list_properties / get_my_owned_properties first."
    ),
    parameters={
        "type": "object",
        "properties": {
            "property_id": {"type": "integer", "description": "Property id."},
        },
        "required": ["property_id"],
        "additionalProperties": False,
    },
    roles=ALL_ROLES,
    handler=_get_property_details,
))


async def _get_my_rent_distributions(_args: dict, user: AuthUser, db: Any) -> ToolResult:
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT rd.id, rd.property_id, p.name AS property_name, "
            "rd.total_distributed, rd.investor_count, rd.distributed_at, rd.tx_hash "
            f"FROM rent_distributions rd "
            f"{active_property_join('p.id = rd.property_id')} "
            f"WHERE LOWER(p.owner_wallet) = LOWER(%s) "
            "ORDER BY rd.distributed_at DESC LIMIT 50",
            (user.wallet_address,),
        )
        rows = cursor.fetchall() or []
    finally:
        cursor.close()
    items = [
        {
            "property_id": int(r["property_id"]),
            "property_name": r.get("property_name"),
            "total_distributed_eth": _eth(int(r.get("total_distributed") or 0)),
            "investor_count": int(r.get("investor_count") or 0),
            "distributed_at": r["distributed_at"].isoformat() if r.get("distributed_at") else None,
            "tx_hash": r.get("tx_hash"),
        }
        for r in rows
    ]
    return ToolResult(ok=True, data={"count": len(items), "distributions": items})


register(ToolSpec(
    name="get_my_rent_distributions",
    description=(
        "Rent distributions sent out across properties owned by the signed-in "
        "property owner. Each row is one distribution event with total ETH and "
        "investor count."
    ),
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    roles=frozenset({"property_owner"}),
    handler=_get_my_rent_distributions,
))


async def _get_my_active_tenants(_args: dict, user: AuthUser, db: Any) -> ToolResult:
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT tr.id, tr.property_id, p.name AS property_name, p.location, "
            "t.wallet_address AS tenant_wallet, tr.rental_start_date, tr.status "
            f"FROM tenant_rentals tr "
            f"JOIN tenants t ON t.id = tr.tenant_id "
            f"{active_property_join('p.id = tr.property_id')} "
            f"WHERE LOWER(p.owner_wallet) = LOWER(%s) AND tr.status = 'active' "
            "ORDER BY tr.created_at DESC",
            (user.wallet_address,),
        )
        rows = cursor.fetchall() or []
    finally:
        cursor.close()
    items = [
        {
            "property_id": int(r["property_id"]),
            "property_name": r.get("property_name"),
            "location": r.get("location"),
            "tenant_wallet": r.get("tenant_wallet"),
            "rental_start_date": r["rental_start_date"].isoformat() if r.get("rental_start_date") else None,
        }
        for r in rows
    ]
    return ToolResult(ok=True, data={"count": len(items), "rentals": items})


register(ToolSpec(
    name="get_my_active_tenants",
    description=(
        "Active tenant rentals across properties owned by the signed-in "
        "property owner. Use when the owner asks about their tenants."
    ),
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    roles=frozenset({"property_owner"}),
    handler=_get_my_active_tenants,
))


async def _get_my_rent_collections(args: dict, user: AuthUser, db: Any) -> ToolResult:
    """Rent payments received across the owner's properties."""
    limit = max(1, min(int(args.get("limit") or 20), 100))
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT rp.id, rp.property_id, p.name AS property_name, rp.amount_eth, "
            "rp.amount_wei, rp.tx_hash, rp.payment_date, rp.payment_status, "
            "t.wallet_address AS tenant_wallet "
            f"FROM rent_payments rp "
            f"JOIN tenants t ON t.id = rp.tenant_id "
            f"{active_property_join('p.id = rp.property_id')} "
            f"WHERE LOWER(p.owner_wallet) = LOWER(%s) "
            f"ORDER BY rp.payment_date DESC LIMIT %s",
            (user.wallet_address, limit),
        )
        rows = cursor.fetchall() or []
    finally:
        cursor.close()
    items = [
        {
            "property_id": int(r["property_id"]),
            "property_name": r.get("property_name"),
            "tenant_wallet": r.get("tenant_wallet"),
            "amount_eth": str(r.get("amount_eth") or "0"),
            "tx_hash": r.get("tx_hash"),
            "payment_date": r["payment_date"].isoformat() if r.get("payment_date") else None,
            "payment_status": r.get("payment_status"),
        }
        for r in rows
    ]
    return ToolResult(ok=True, data={"count": len(items), "payments": items})


register(ToolSpec(
    name="get_my_rent_collections",
    description=(
        "Rent payments collected by the signed-in property owner, across all "
        "their properties. Use for 'show recent rent received' or 'last rent "
        "payment'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Default 20."},
        },
        "additionalProperties": False,
    },
    roles=frozenset({"property_owner"}),
    handler=_get_my_rent_collections,
))


async def _get_my_yield_summary(_args: dict, user: AuthUser, db: Any) -> ToolResult:
    cursor = db.cursor(dictionary=True)
    try:
        wallet = user.wallet_address
        cursor.execute(
            f"""
            SELECT COALESCE(SUM(CAST(irp.payout_amount_wei AS DECIMAL(36,0))), 0) AS earned,
                   COUNT(*) AS payouts,
                   COUNT(DISTINCT irp.property_id) AS props
            FROM investor_rent_payouts irp
            {active_property_join("p.id = irp.property_id")}
            WHERE LOWER(irp.investor_wallet) = LOWER(%s)
            """,
            (wallet,),
        )
        totals = cursor.fetchone() or {}
        cursor.execute(
            f"""
            SELECT COALESCE(SUM(CAST(irp.payout_amount_wei AS DECIMAL(36,0))), 0) AS claimable
            FROM investor_rent_payouts irp
            {active_property_join("p.id = irp.property_id")}
            WHERE LOWER(irp.investor_wallet) = LOWER(%s)
              AND COALESCE(irp.claim_status, 'claimable') = 'claimable'
            """,
            (wallet,),
        )
        claimable = int((cursor.fetchone() or {}).get("claimable") or 0)
        cursor.execute(
            f"""
            SELECT COALESCE(SUM(CAST(irp.payout_amount_wei AS DECIMAL(36,0))), 0) AS claimed
            FROM investor_rent_payouts irp
            {active_property_join("p.id = irp.property_id")}
            WHERE LOWER(irp.investor_wallet) = LOWER(%s)
              AND irp.claim_status = 'claimed'
            """,
            (wallet,),
        )
        claimed = int((cursor.fetchone() or {}).get("claimed") or 0)
    finally:
        cursor.close()
    return ToolResult(
        ok=True,
        data={
            "total_earned_eth": _eth(int(totals.get("earned") or 0)),
            "total_claimable_eth": _eth(claimable),
            "total_claimed_eth": _eth(claimed),
            "total_payouts": int(totals.get("payouts") or 0),
            "properties_earning": int(totals.get("props") or 0),
        },
    )


register(ToolSpec(
    name="get_my_yield_summary",
    description=(
        "Cumulative yield summary for the signed-in investor: total earned, "
        "claimable, and already-claimed rent (in ETH)."
    ),
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    roles=frozenset({"investor"}),
    handler=_get_my_yield_summary,
))


async def _get_my_claim_history(_args: dict, user: AuthUser, db: Any) -> ToolResult:
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT irp.property_id, p.name AS property_name, irp.claim_tx_hash, "
            "COALESCE(SUM(CAST(irp.payout_amount_wei AS DECIMAL(36,0))), 0) AS claimed_wei, "
            "COUNT(*) AS payout_count, MAX(irp.claimed_at) AS claimed_at "
            f"FROM investor_rent_payouts irp "
            f"{active_property_join('p.id = irp.property_id')} "
            f"WHERE LOWER(irp.investor_wallet) = LOWER(%s) "
            f"AND irp.claim_status = 'claimed' AND irp.claim_tx_hash IS NOT NULL "
            "GROUP BY irp.property_id, p.name, irp.claim_tx_hash "
            "ORDER BY MAX(irp.claimed_at) DESC LIMIT 50",
            (user.wallet_address,),
        )
        rows = cursor.fetchall() or []
    finally:
        cursor.close()
    items = [
        {
            "property_id": int(r["property_id"]),
            "property_name": r.get("property_name"),
            "claimed_amount_eth": _eth(int(r.get("claimed_wei") or 0)),
            "payout_count": int(r.get("payout_count") or 0),
            "claim_tx_hash": r.get("claim_tx_hash"),
            "claimed_at": r["claimed_at"].isoformat() if r.get("claimed_at") else None,
        }
        for r in rows
    ]
    return ToolResult(ok=True, data={"count": len(items), "claims": items})


register(ToolSpec(
    name="get_my_claim_history",
    description="Past reward claims by the signed-in investor, grouped by claim transaction.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    roles=frozenset({"investor"}),
    handler=_get_my_claim_history,
))


async def _get_my_rental_earnings(_args: dict, user: AuthUser, db: Any) -> ToolResult:
    """Per-property breakdown of rent earnings for the signed-in user."""
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT irp.property_id, p.name AS property_name, "
            "SUM(CAST(irp.payout_amount_wei AS DECIMAL(36,0))) AS earned_wei, "
            "COUNT(*) AS payment_count, "
            "MAX(irp.ownership_percentage) AS current_ownership_pct, "
            "MAX(irp.distributed_at) AS last_distributed_at "
            f"FROM investor_rent_payouts irp "
            f"{active_property_join('p.id = irp.property_id')} "
            f"WHERE LOWER(irp.investor_wallet) = LOWER(%s) "
            f"GROUP BY irp.property_id, p.name "
            "ORDER BY earned_wei DESC",
            (user.wallet_address,),
        )
        rows = cursor.fetchall() or []
    finally:
        cursor.close()
    items = [
        {
            "property_id": int(r["property_id"]),
            "property_name": r.get("property_name"),
            "earned_eth": _eth(int(r.get("earned_wei") or 0)),
            "payment_count": int(r.get("payment_count") or 0),
            "current_ownership_pct": float(r.get("current_ownership_pct") or 0),
            "last_distributed_at": r["last_distributed_at"].isoformat() if r.get("last_distributed_at") else None,
        }
        for r in rows
    ]
    return ToolResult(ok=True, data={"count": len(items), "earnings": items})


register(ToolSpec(
    name="get_my_rental_earnings",
    description=(
        "Per-property rent earnings breakdown for the signed-in investor — "
        "total earned, payment count, current ownership percentage."
    ),
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    roles=frozenset({"investor"}),
    handler=_get_my_rental_earnings,
))


async def _get_platform_stats(_args: dict, _user: AuthUser, db: Any) -> ToolResult:
    cursor = db.cursor(dictionary=True)
    try:
        properties_active = count_dashboard_listable_active(cursor)
        cursor.execute("SELECT COUNT(DISTINCT user_id) AS n FROM token_ownerships WHERE token_amount > 0")
        investors_active = int((cursor.fetchone() or {}).get("n") or 0)
        cursor.execute(
            f"""
            SELECT COUNT(*) AS n FROM tenant_rentals tr
            {active_property_join("p.id = tr.property_id")}
            WHERE tr.status = 'active'
            """
        )
        active_rentals = int((cursor.fetchone() or {}).get("n") or 0)
        cursor.execute(
            f"""
            SELECT COALESCE(SUM(CAST(rp.amount_wei AS DECIMAL(36,0))), 0) AS wei, COUNT(*) AS n
            FROM rent_payments rp
            {active_property_join("p.id = rp.property_id")}
            """
        )
        rent_agg = cursor.fetchone() or {}
        cursor.execute(
            f"""
            SELECT COALESCE(SUM(CAST(rd.total_distributed AS DECIMAL(36,0))), 0) AS wei
            FROM rent_distributions rd
            {active_property_join("p.id = rd.property_id")}
            """
        )
        dist_agg = cursor.fetchone() or {}
        cursor.execute("SELECT COUNT(*) AS n FROM transactions")
        tx_count = int((cursor.fetchone() or {}).get("n") or 0)
    finally:
        cursor.close()
    return ToolResult(
        ok=True,
        data={
            "active_properties": properties_active,
            "active_investors": investors_active,
            "active_rentals": active_rentals,
            "total_rent_collected_eth": _eth(int(rent_agg.get("wei") or 0)),
            "rent_payments_count": int(rent_agg.get("n") or 0),
            "total_rent_distributed_eth": _eth(int(dist_agg.get("wei") or 0)),
            "total_transactions": tx_count,
        },
    )


register(ToolSpec(
    name="get_platform_stats",
    description=(
        "System-wide totals. active_properties counts dashboard-visible listings "
        "only (same as UI). Also returns active investors, rentals, rent totals, "
        "and transaction count."
    ),
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    roles=ALL_ROLES,
    handler=_get_platform_stats,
))


# ---------------------------------------------------------------------------
# Workflow tools — return UI actions the frontend executes
# ---------------------------------------------------------------------------


_CREATE_PROPERTY_FIELDS = (
    "name",
    "location",
    "total_value",
    "token_supply",
    "token_symbol",
    "monthly_rent_eth",
)
_CREATE_PROPERTY_MODAL = "CREATE_PROPERTY"
_CREATE_PROPERTY_REFRESH_FOR_NEW_CHAT_MESSAGE = (
    "Please refresh the page to start a new chat before creating another property."
)


def _create_property_chat_limit_reached(session: dict[str, Any] | None) -> bool:
    """True after one successful create-property submission in this copilot thread."""
    return bool((session or {}).get("chat_property_limit_reached"))


def _block_create_property_when_chat_limit_reached() -> ToolResult | None:
    """One property per chat session — block further create attempts without processing input."""
    session = _get_workflow_session(_CREATE_PROPERTY_MODAL) or {}
    if not _create_property_chat_limit_reached(session):
        return None
    last_name = str(session.get("last_created_name") or "").strip()
    if last_name:
        speak = (
            f"Property '{last_name}' was created successfully in this chat. "
            f"{_CREATE_PROPERTY_REFRESH_FOR_NEW_CHAT_MESSAGE}"
        )
    else:
        speak = (
            "A property was already created successfully in this chat. "
            f"{_CREATE_PROPERTY_REFRESH_FOR_NEW_CHAT_MESSAGE}"
        )
    return ToolResult(
        ok=True,
        data={
            "blocked": True,
            "chat_property_limit_reached": True,
            "submitted": True,
            "filled": {},
            "missing": [],
            "speak_to_user": speak,
            "instruction": (
                "Tell the user exactly what speak_to_user says. Do NOT call "
                "start_create_property or fill_create_property. Do NOT ask for "
                "property fields or accept their latest input for a new listing."
            ),
        },
        actions=[],
    )


def _assistant_announced_property_created(text: str) -> bool:
    """Detect copilot success lines like \"Property 'X' created successfully.\" """
    lowered = (text or "").lower()
    return "created successfully" in lowered and "property" in lowered


def _assistant_announced_property_create_failure(text: str) -> bool:
    """Detect frontend/tooling failure lines after a create-property submit."""
    lowered = (text or "").lower()
    if not lowered or _assistant_announced_property_created(text):
        return False
    if "reply yes to create and deploy" in lowered:
        return False
    if "here are the property details" in lowered:
        return False
    if lowered.startswith("submitting ") and "from this chat" in lowered:
        return False
    markers = (
        "failed to create",
        "property creation failed",
        "missing property details",
        "session expired",
        "exceeds the on-chain limit",
        "cannot exceed",
        "total property value cannot",
        "monthly rent exceeds",
        "monthly rent cannot exceed",
        "setup failed",
        "http 401",
        "http 409",
        "http 500",
        "issue with the property creation",
        "did not complete",
        "property was saved but setup failed",
    )
    return any(marker in lowered for marker in markers)


def _latest_assistant_create_property_outcome() -> tuple[str | None, str]:
    """Return ('success'|'failure'|None, message text for the latest outcome)."""
    for msg in reversed(_current_history() or []):
        if _message_role(msg) not in ("ai", "assistant"):
            continue
        text = _message_content(msg)
        if _assistant_announced_property_created(text):
            return "success", text
        if _assistant_announced_property_create_failure(text):
            return "failure", text
    return None, ""


def _reconcile_create_property_session_after_outcome(
    pre_session: dict[str, Any] | None,
) -> dict[str, Any]:
    """Restore confirmation draft after a failed deploy so the admin can retry Yes."""
    session = dict(pre_session or {})
    outcome, failure_text = _latest_assistant_create_property_outcome()
    if outcome == "success":
        _sync_create_property_limit_from_success_announcement()
        return _get_workflow_session(_CREATE_PROPERTY_MODAL) or {}
    if outcome != "failure":
        return session

    filled = _backfill_create_property_filled_from_history(
        normalize_create_property_accumulated(dict(session.get("filled") or {}))
    )
    if not _create_property_required_fields_present(filled):
        return session

    restored = {
        "in_progress": True,
        "filled": filled,
        "next_field": None,
        "submitted": False,
        "submitting": False,
        "awaiting_create_confirmation": True,
        "submit_failed": True,
        "last_submit_error": failure_text[:500],
    }
    _set_workflow_session(_CREATE_PROPERTY_MODAL, restored)
    return restored


def _sync_create_property_limit_from_success_announcement() -> None:
    """Lock one-property-per-chat after the UI reports a successful create."""
    session = _get_workflow_session(_CREATE_PROPERTY_MODAL) or {}
    if session.get("chat_property_limit_reached"):
        return
    for msg in reversed(_current_history() or []):
        if _message_role(msg) not in ("ai", "assistant"):
            continue
        text = _message_content(msg)
        if _assistant_announced_property_created(text):
            name = ""
            m = re.search(r"property\s+'([^']+)'", text, re.IGNORECASE)
            if m:
                name = m.group(1).strip()
            _mark_create_property_completed(name)
        return


def _mark_create_property_completed(property_name: str = "") -> None:
    """Mark this chat thread as having used its one allowed create-property submission."""
    _set_workflow_session(
        _CREATE_PROPERTY_MODAL,
        {
            "in_progress": False,
            "submitted": True,
            "chat_property_limit_reached": True,
            "filled": {},
            "next_field": None,
            "last_created_name": (property_name or "").strip(),
        },
    )


def _create_property_session_needs_ui_bootstrap(session: dict[str, Any]) -> bool:
    """True when the Create dialog must be navigated/opened before fill/submit."""
    if _create_property_chat_limit_reached(session):
        return False
    return not bool(session.get("in_progress"))


def _human_requested_new_create_property_listing() -> bool:
    """Detect a fresh 'create/add/list a property' intent in the latest user line."""
    for msg in reversed(_current_history() or []):
        if _message_role(msg) not in ("human", "user"):
            continue
        text = _message_content(msg)
        if not text:
            continue
        if is_generic_create_property_intent(text):
            return True
        lowered = text.lower()
        return "create" in lowered and "property" in lowered
    return False


async def _start_create_property(_args: dict, _user: AuthUser, _db: Any) -> ToolResult:
    _sync_create_property_limit_from_success_announcement()
    blocked = _block_create_property_when_chat_limit_reached()
    if blocked is not None:
        return blocked

    pre_session = _reconcile_create_property_session_after_outcome(
        _get_workflow_session(_CREATE_PROPERTY_MODAL)
    )
    if pre_session.get("submit_failed") and pre_session.get("filled"):
        filled = _backfill_create_property_filled_from_history(
            normalize_create_property_accumulated(dict(pre_session.get("filled") or {}))
        )
        if _create_property_required_fields_present(filled):
            return _create_property_confirmation_prompt(
                filled,
                actions=[],
                data={"filled": filled},
                bootstrap_for_turn=True,
                needs_ui_bootstrap=True,
                had_active_session=False,
                pre_session=pre_session,
            )

    modal = _CREATE_PROPERTY_MODAL
    required = _CREATE_PROPERTY_FIELDS[:5]
    # Explicit start always opens a new draft (abandoned partial forms, chat refresh, etc.).
    _clear_workflow_session(modal)
    filled: dict[str, str] = {}
    missing = [f for f in required if f not in filled or not filled.get(f)]
    next_field = missing[0] if missing else None
    _set_workflow_session(
        modal,
        {
            "in_progress": True,
            "filled": filled,
            "next_field": next_field or "name",
            "submitted": False,
        },
    )
    focus_field = next_field or "name"
    return ToolResult(
        ok=True,
        data={
            "message": "Starting chat-only property creation.",
            "filled": filled,
            "missing": missing,
            "next_field": next_field or "name",
            "instruction": (
                f"Form already has: {', '.join(f'{k}={v}' for k, v in filled.items())}. "
                f"Ask about {next_field or 'name'} only — do NOT re-ask for fields in filled."
                if filled
                else "Ask: What's the name of the property?"
            ),
        },
        actions=[
            AgentAction(type="NAVIGATE", route="/property_owner/properties"),
            AgentAction(type="OPEN_MODAL", modal="CREATE_PROPERTY"),
            AgentAction(type="FOCUS_FIELD", modal="CREATE_PROPERTY", field=focus_field),
        ],
    )


register(ToolSpec(
    name="start_create_property",
    description=(
        "MANDATORY first step the moment the user asks to create / add a new "
        "property. Starts the chat-only collection flow; the frontend keeps "
        "focus in the copilot textbox and does not show the Create Property "
        "dialog behind the chat. After calling this tool, your spoken "
        "reply MUST end with the very next question to ask: \"What's the name "
        "of the property?\" Only one property may be created per chat session; "
        "after a successful create, this tool returns speak_to_user telling the "
        "user to refresh for a new chat."
    ),
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    roles=frozenset({"property_owner"}),
    handler=_start_create_property,
))


def _recover_form_state(modal: str, tool_name: str, fields: tuple[str, ...]) -> dict[str, str]:
    """Scan the conversation history for prior calls of ``tool_name`` and
    return the accumulated field values for the *current* fill workflow.

    This makes the create / edit workflows resilient: even if the LLM forgets
    to pass previously collected fields on a later turn, the server still
    knows what's been filled. The data lives in earlier ToolMessages.

    CRITICAL: we treat both submission and workflow-restart events as
    boundaries that reset the accumulator. Without this, after a
    successful create-property #1 the recovery would dredge up #1's
    fields when the user starts create-property #2 — the LLM would see
    ``missing: []``, immediately call fill with ``submit=true``, and
    re-submit #1's stale values instead of asking for #2's fresh ones.
    Property #2 then fails to be created because the form contained
    duplicate / wrong data.

    Boundaries:
      • A prior fill-tool ToolMessage with ``data.submitted`` or
        ``data.submitting`` true (the user already finished a property).
      • A prior ``start_<bare>`` ToolMessage (the LLM explicitly
        re-opened the dialog — i.e. the user wants to start over, even
        if the previous attempt wasn't submitted).
    """
    import json as _json

    # The matching "start" tool that opens this dialog (e.g.
    # fill_create_property → start_create_property).
    start_tool = tool_name.replace("fill_", "start_", 1)

    accumulated: dict[str, str] = {}
    session = _get_workflow_session(modal)
    session_filled = dict(session.get("filled") or {})
    if modal == _CREATE_PROPERTY_MODAL and _create_property_chat_limit_reached(session):
        session_filled = {}
    if isinstance(session_filled, dict):
        for k, v in session_filled.items():
            if k in fields and v not in (None, ""):
                accumulated[k] = str(v)

    for msg in _current_history() or []:
        role = _message_role(msg)
        name = getattr(msg, "name", None) or (msg.get("name") if isinstance(msg, dict) else None)
        content = getattr(msg, "content", None)
        if content is None and isinstance(msg, dict):
            content = msg.get("content")

        if modal == _CREATE_PROPERTY_MODAL and role in ("ai", "assistant"):
            if _assistant_announced_property_created(_message_content(msg)):
                accumulated = {}
                continue

        # start_* is handled via the session store (client history has no tools).
        if name == start_tool:
            continue

        if name != tool_name or not content:
            continue
        try:
            parsed = _json.loads(content) if isinstance(content, str) else content
        except (TypeError, ValueError):
            continue
        data = parsed.get("data") if isinstance(parsed, dict) else None
        if not isinstance(data, dict):
            continue
        # Submission boundary — anything filled BEFORE this point belongs
        # to a previous property/edit/etc. and must NOT leak into the new
        # conversation that follows. Reset and keep walking forward in
        # case there are further (partial) fills after this submission.
        if data.get("submitted") or data.get("submitting"):
            accumulated = {}
            continue
        prior_filled = data.get("filled") or data.get("filled_fields") or {}
        if isinstance(prior_filled, dict):
            for k, v in prior_filled.items():
                if k in fields and v not in (None, ""):
                    accumulated[k] = str(v)
    if modal == _CREATE_PROPERTY_MODAL and _create_property_session_preserves_filled(session):
        for k, v in session_filled.items():
            if k in fields and v not in (None, ""):
                accumulated[k] = str(v)
    return accumulated


def _build_fill_workflow(
    args: dict,
    modal: str,
    tool_name: str,
    fields: tuple[str, ...],
    required: tuple[str, ...],
) -> ToolResult:
    """Shared implementation for any ``fill_<modal>`` workflow tool.

    Behaviour:
    - Merges values from prior turns (recovered from message history) with the
      new ``args`` so the LLM never has to remember the entire form.
    - Emits a ``FILL_FIELD`` action for every value (including recovered ones)
      so the UI stays in sync if the frontend lost local state (e.g. after a
      voice mode reload).
    - When ``submit=true`` and all required fields are present, emits
      ``SUBMIT_FORM``; otherwise reports missing fields so the LLM can ask
      one focused question.
    """
    actions: list[AgentAction] = []
    accumulated = _recover_form_state(modal, tool_name, fields)
    for field in fields:
        value = args.get(field)
        if value is None or value == "":
            continue
        raw = str(value)
        if modal == _CREATE_PROPERTY_MODAL:
            if field == "name" and is_generic_create_property_intent(raw):
                continue
            raw = normalize_create_property_field(field, raw)
            if not raw:
                continue
        accumulated[field] = raw

    accumulated = _merge_last_user_utterance(accumulated, modal, fields, required)

    if modal == "CREATE_PROPERTY":
        accumulated = normalize_create_property_accumulated(accumulated)

    for field in fields:
        value = accumulated.get(field)
        if value in (None, ""):
            continue
        actions.append(AgentAction(
            type="FILL_FIELD",
            modal=modal,
            field=field,
            value=str(value),
        ))

    missing = [f for f in required if f not in accumulated or accumulated.get(f) in (None, "")]

    submit = bool(args.get("submit"))
    next_field = missing[0] if missing else None
    instruction: str | None = None
    if accumulated and next_field:
        instruction = (
            "Already collected: "
            + ", ".join(f"{k}={v!r}" for k, v in accumulated.items())
            + f". Ask the user for {next_field} next. "
            "Do NOT re-ask for any field already in filled."
        )
    elif not missing:
        instruction = (
            "All required fields are collected. The server will show a confirmation "
            "summary before submitting — read speak_to_user to the user."
        )

    if submit and not missing:
        # CREATE_PROPERTY submit runs through fill_create_property so chat limits
        # apply before SUBMIT_FORM is emitted.
        if modal != _CREATE_PROPERTY_MODAL:
            actions.append(AgentAction(type="SUBMIT_FORM", modal=modal))
            _set_workflow_session(
                modal,
                {"in_progress": False, "filled": accumulated, "next_field": None, "submitted": True},
            )
            return ToolResult(
                ok=True,
                data={
                    "filled": accumulated,
                    "missing": [],
                    "submitted": True,
                    "next_field": None,
                    "instruction": instruction,
                },
                actions=actions,
            )

    if submit and missing:
        # The LLM asked to submit but we don't have everything — keep filling
        # what we have, surface what's missing, and tell the LLM what to ask
        # next so it doesn't re-ask for a field already filled.
        return ToolResult(
            ok=False,
            error=(
                "Cannot submit yet. Still missing: "
                + ", ".join(missing)
                + f". Ask the user for {next_field} next — do NOT re-ask for fields already filled."
            ),
            data={
                "filled": accumulated,
                "missing": missing,
                "submitted": False,
                "next_field": next_field,
                "instruction": instruction,
            },
            actions=actions,
        )

    session_payload: dict[str, Any] = {
        "in_progress": True,
        "filled": accumulated,
        "next_field": next_field,
        "submitted": False,
    }
    _set_workflow_session(modal, session_payload)
    return ToolResult(
        ok=True,
        data={
            "filled": accumulated,
            "missing": missing,
            "submitted": False,
            "next_field": next_field,
            "instruction": instruction,
        },
        actions=actions,
    )


def _property_create_payload_from_accumulated(accumulated: dict) -> PropertyCreate:
    monthly_raw = (accumulated.get("monthly_rent_eth") or "").strip().lower()
    monthly_rent: Decimal | None = None
    if monthly_raw and monthly_raw not in {"0", "skip", "none", "no", "n/a"}:
        monthly_rent = Decimal(str(accumulated["monthly_rent_eth"]))

    return PropertyCreate(
        name=str(accumulated["name"]).strip(),
        location=str(accumulated["location"]).strip(),
        total_value=Decimal(str(accumulated["total_value"])),
        token_supply=Decimal(str(accumulated["token_supply"])),
        token_symbol=str(accumulated["token_symbol"]).strip(),
        monthly_rent_eth=monthly_rent,
        images=[],
    )


def create_property_pending_name() -> str:
    """Property name from the in-flight create workflow session (for status messages)."""
    session = _get_workflow_session(_CREATE_PROPERTY_MODAL) or {}
    return str((session.get("filled") or {}).get("name") or "").strip()


def _parse_confirm_create_arg(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "1"):
            return True
        if lowered in ("false", "no", "0"):
            return False
    return bool(value)


def create_property_deploy_pending(tool_input: dict | None = None) -> bool:
    """True when fill_create_property is about to run server-side create + deploy."""
    args = dict(tool_input or {})
    explicit = _parse_confirm_create_arg(args.get("confirm_create"))
    if explicit is True:
        return True
    if explicit is False:
        return False

    pre_session = _reconcile_create_property_session_after_outcome(
        _get_workflow_session(_CREATE_PROPERTY_MODAL) or {}
    )
    if pre_session.get("submitting") and not pre_session.get("submit_failed"):
        return False

    filled = _backfill_create_property_filled_from_history(
        normalize_create_property_accumulated(dict(pre_session.get("filled") or {}))
    )
    awaiting = bool(
        pre_session.get("awaiting_create_confirmation")
        or pre_session.get("submit_failed")
    )
    complete = _create_property_required_fields_present(filled)
    if not awaiting and not complete:
        return False
    confirm = _create_property_confirmation_reply(args)
    return confirm is True and complete


def create_property_server_submit_eligible(user: AuthUser) -> tuple[bool, str]:
    """True when the latest user turn is Yes and the server should submit now."""
    if canonical_role(user.role) != "property_owner":
        return False, ""
    if _latest_human_yes_no_reply() is not True:
        return False, ""

    pre_session = _reconcile_create_property_session_after_outcome(
        _get_workflow_session(_CREATE_PROPERTY_MODAL) or {}
    )
    if pre_session.get("chat_property_limit_reached"):
        return False, ""
    if pre_session.get("submitting") and not pre_session.get("submit_failed"):
        return False, ""

    filled = _backfill_create_property_filled_from_history(
        normalize_create_property_accumulated(dict(pre_session.get("filled") or {}))
    )
    awaiting = bool(
        pre_session.get("awaiting_create_confirmation")
        or pre_session.get("submit_failed")
    )
    if not awaiting and not _create_property_required_fields_present(filled):
        return False, ""
    if not _create_property_required_fields_present(filled):
        return False, ""

    return True, str(filled.get("name") or "").strip()


def _create_property_success_message(
    name: str,
    *,
    rent_sync_warning: str | None = None,
) -> str:
    from backend.ai.create_property_messages import create_property_success_message

    return create_property_success_message(name, rent_sync_warning=rent_sync_warning)


def _create_property_args_change_fields(
    args: dict,
    session_filled: dict[str, Any] | None = None,
) -> bool:
    """True when fill_create_property carries a real field edit (not redundant re-send)."""
    for field in _CREATE_PROPERTY_FIELDS:
        if field not in args or args.get(field) in (None, ""):
            continue
        incoming = normalize_create_property_field(field, str(args[field]))
        if not incoming:
            continue
        if session_filled:
            existing = normalize_create_property_field(
                field, str(session_filled.get(field) or "")
            )
            if existing and incoming.lower() == existing.lower():
                continue
        return True
    return False


def _create_property_confirmation_reply(args: dict) -> bool | None:
    confirm = args.get("confirm_create")
    if confirm is not None:
        return bool(confirm)
    return _latest_human_yes_no_reply()


def _create_property_pre_submit_block(accumulated: dict[str, str]) -> ToolResult | None:
    """Block SUBMIT_FORM when values cannot succeed on-chain; keep confirmation open."""
    monthly_raw = (accumulated.get("monthly_rent_eth") or "").strip().lower()
    if not monthly_raw or monthly_raw in {"0", "skip", "none", "no", "n/a"}:
        return None
    from backend.services.blockchain import to_wei

    try:
        rent_wei = to_wei(Decimal(str(accumulated["monthly_rent_eth"])))
    except (TypeError, ValueError, ArithmeticError):
        return None
    if rent_wei <= 0:
        return None
    try:
        validate_monthly_rent_for_chain(rent_wei)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        summary = format_create_property_confirmation_summary(accumulated)
        _set_workflow_session(
            _CREATE_PROPERTY_MODAL,
            {
                "in_progress": True,
                "filled": accumulated,
                "next_field": None,
                "submitted": False,
                "awaiting_create_confirmation": True,
            },
        )
        return ToolResult(
            ok=True,
            data={
                "filled": accumulated,
                "missing": [],
                "submitted": False,
                "awaiting_create_confirmation": True,
                "submit_blocked": True,
                "on_chain_limit": "monthly_rent",
                "confirmation_summary": summary,
                "speak_to_user": (
                    f"{detail} Update the monthly rent, say No to cancel, or confirm "
                    "again after lowering rent to 100 ETH or less."
                ),
                "instruction": _create_property_confirmation_instruction(),
            },
            actions=[],
        )
    return None


def _create_property_required_fields_present(filled: dict[str, str]) -> bool:
    required = _CREATE_PROPERTY_FIELDS[:5]
    return all(filled.get(field) not in (None, "") for field in required)


def _create_property_needs_monthly_rent_collection(filled: dict[str, str]) -> bool:
    """True when required fields are done but optional rent has not been collected."""
    if not _create_property_required_fields_present(filled):
        return False
    return "monthly_rent_eth" not in filled


def _create_property_prompt_for_monthly_rent(
    accumulated: dict[str, str],
    *,
    data: dict[str, Any],
    actions: list[AgentAction],
) -> ToolResult:
    prompt = create_property_monthly_rent_collection_prompt()
    _set_workflow_session(
        _CREATE_PROPERTY_MODAL,
        {
            "in_progress": True,
            "filled": accumulated,
            "next_field": "monthly_rent_eth",
            "submitted": False,
            "awaiting_create_confirmation": False,
        },
    )
    out_data = {
        **data,
        "filled": accumulated,
        "missing": [],
        "next_field": "monthly_rent_eth",
        "submitted": False,
        "awaiting_create_confirmation": False,
        "speak_to_user": prompt,
        "instruction": (
            "Read speak_to_user verbatim, then wait for the user's monthly rent answer. "
            "Monthly rent must be less than 100 ETH (say 0 or skip for no rent)."
        ),
    }
    return ToolResult(ok=True, data=out_data, actions=actions)


def _gate_create_property_monthly_rent_value(
    accumulated: dict[str, str],
    *,
    data: dict[str, Any],
    actions: list[AgentAction],
) -> ToolResult | None:
    raw = accumulated.get("monthly_rent_eth")
    if raw in (None, ""):
        return None
    if create_property_monthly_rent_is_skip(str(raw)):
        accumulated["monthly_rent_eth"] = "0"
        return None
    if not create_property_monthly_rent_over_limit(str(raw)):
        return None
    accumulated.pop("monthly_rent_eth", None)
    prompt = create_property_monthly_rent_rejection_message(str(raw))
    _set_workflow_session(
        _CREATE_PROPERTY_MODAL,
        {
            "in_progress": True,
            "filled": accumulated,
            "next_field": "monthly_rent_eth",
            "submitted": False,
            "awaiting_create_confirmation": False,
        },
    )
    return ToolResult(
        ok=True,
        data={
            **data,
            "filled": accumulated,
            "missing": [],
            "next_field": "monthly_rent_eth",
            "rent_over_limit": True,
            "speak_to_user": prompt,
            "instruction": (
                "The rent value exceeds the 100 ETH limit. Read speak_to_user and "
                "wait for a lower amount, 0, or skip."
            ),
        },
        actions=[a for a in actions if a.field != "monthly_rent_eth"],
    )


def _create_property_confirmation_instruction() -> str:
    return (
        "Read the confirmation summary to the user verbatim (it lists Edit and Delete). "
        "Wait for Yes (create), Edit (field change), or Delete/No (clear draft). "
        "On Yes call fill_create_property with confirm_create=true only — do not "
        "re-send all fields. On Delete or No use confirm_create=false. On Edit pass "
        "only the updated field(s). After a failed create, call fill_create_property "
        "with confirm_create=true to retry — never restart from the property name "
        "unless the user asked to."
    )


def _create_property_failure_retry_prefix(session: dict[str, Any]) -> str:
    err = str(session.get("last_submit_error") or "").strip()
    if err:
        return f"The previous create attempt did not succeed: {err}\n\n"
    return "The previous create attempt did not succeed.\n\n"


def _create_property_confirmation_prompt(
    accumulated: dict[str, str],
    *,
    actions: list[AgentAction],
    data: dict[str, Any],
    bootstrap_for_turn: bool,
    needs_ui_bootstrap: bool,
    had_active_session: bool,
    pre_session: dict[str, Any] | None = None,
) -> ToolResult:
    summary = format_create_property_confirmation_summary(accumulated)
    session = dict(pre_session or {})
    prefix = _create_property_failure_retry_prefix(session) if session.get("submit_failed") else ""
    speak = f"{prefix}{summary}"
    _set_workflow_session(
        _CREATE_PROPERTY_MODAL,
        {
            "in_progress": True,
            "filled": accumulated,
            "next_field": None,
            "submitted": False,
            "submitting": False,
            "awaiting_create_confirmation": True,
            "submit_failed": bool(session.get("submit_failed")),
            "last_submit_error": session.get("last_submit_error"),
        },
    )
    out_data = {
        **data,
        "filled": accumulated,
        "missing": [],
        "next_field": None,
        "submitted": False,
        "awaiting_create_confirmation": True,
        "confirmation_summary": summary,
        "speak_to_user": speak,
        "speak_verbatim": True,
        "instruction": _create_property_confirmation_instruction(),
    }
    final_actions = list(actions)
    if needs_ui_bootstrap or bootstrap_for_turn or not had_active_session:
        final_actions = [
            AgentAction(type="NAVIGATE", route="/property_owner/properties"),
            AgentAction(type="OPEN_MODAL", modal=_CREATE_PROPERTY_MODAL),
            *final_actions,
        ]
    return ToolResult(ok=True, data=out_data, actions=final_actions)


def _create_property_cancel_after_decline() -> ToolResult:
    _set_workflow_session(
        _CREATE_PROPERTY_MODAL,
        {
            "in_progress": True,
            "filled": {},
            "next_field": "name",
            "submitted": False,
            "awaiting_create_confirmation": False,
        },
    )
    required = _CREATE_PROPERTY_FIELDS[:5]
    return ToolResult(
        ok=True,
        data={
            "cancelled": True,
            "property_create_cancelled": True,
            "filled": {},
            "missing": list(required),
            "next_field": "name",
            "awaiting_create_confirmation": False,
            "speak_to_user": (
                "I've cleared the property details. "
                "What's the name of the property if you'd like to start again?"
            ),
            "instruction": (
                "The user declined the confirmation. Ask for the property name to "
                "restart collection. Do not submit until they confirm a new summary."
            ),
        },
        actions=[],
    )


def _create_property_submit_in_flight_block(pre_session: dict[str, Any]) -> ToolResult | None:
    if pre_session.get("submitting") and not pre_session.get("submit_failed"):
        return ToolResult(
            ok=True,
            data={
                "submit_in_flight": True,
                "speak_to_user": (
                    "Property creation is still in progress — please wait for the "
                    "success or error message before trying again."
                ),
                "instruction": "Do not call more tools until the create finishes.",
            },
            actions=[],
        )
    return None


def _create_property_submit_failure_result(
    accumulated: dict[str, str],
    data: dict[str, Any],
    *,
    detail: str,
    property_name: str,
) -> ToolResult:
    _set_workflow_session(
        _CREATE_PROPERTY_MODAL,
        {
            "in_progress": True,
            "filled": accumulated,
            "next_field": None,
            "submitted": False,
            "submitting": False,
            "awaiting_create_confirmation": True,
            "submit_failed": True,
            "last_submit_error": detail,
            "last_submit_name": property_name,
        },
    )
    return ToolResult(
        ok=True,
        data={
            **data,
            "filled": accumulated,
            "missing": [],
            "submitted": False,
            "submit_failed": True,
            "last_submit_error": detail,
            "speak_to_user": (
                f"Failed to create the property: {detail} "
                "You can say Yes to try again, or edit a field such as monthly rent."
            ),
            "instruction": (
                "Tell the user the failure in plain language. Do not claim success. "
                "They may retry with confirm_create=true."
            ),
        },
        actions=[],
    )


def _create_property_submit_result(
    accumulated: dict[str, str],
    data: dict[str, Any],
    user: AuthUser,
    db: Any,
    *,
    bootstrap_for_turn: bool,
    needs_ui_bootstrap: bool,
    had_active_session: bool,
) -> ToolResult:
    """Create the listing on the server (DB + on-chain deploy), same as POST /properties/stream."""
    del bootstrap_for_turn, needs_ui_bootstrap, had_active_session

    in_flight = _create_property_submit_in_flight_block(
        _get_workflow_session(_CREATE_PROPERTY_MODAL) or {}
    )
    if in_flight is not None:
        return in_flight

    blocked = _create_property_pre_submit_block(accumulated)
    if blocked is not None:
        return blocked

    property_name = str(accumulated.get("name") or "property")
    _set_workflow_session(
        _CREATE_PROPERTY_MODAL,
        {
            "in_progress": True,
            "filled": accumulated,
            "next_field": None,
            "submitted": False,
            "submitting": True,
            "awaiting_create_confirmation": False,
            "submit_failed": False,
            "last_submit_error": None,
            "last_submit_name": property_name,
        },
    )

    try:
        payload = _property_create_payload_from_accumulated(accumulated)
        LOGGER.info(
            "[create_property:copilot] server_create start name=%r total_value=%s "
            "token_supply=%s monthly_rent_eth=%s",
            property_name,
            accumulated.get("total_value"),
            accumulated.get("token_supply"),
            accumulated.get("monthly_rent_eth"),
        )
        row = create_property_record(db, user, payload)
        pid = int(row["id"])
        rent_sync_warning = str(row.pop("_rent_sync_warning", "") or "").strip() or None
        success = _create_property_success_message(
            property_name,
            rent_sync_warning=rent_sync_warning,
        )
        _mark_create_property_completed(property_name)
        _set_workflow_session(
            _CREATE_PROPERTY_MODAL,
            {
                "in_progress": False,
                "filled": accumulated,
                "next_field": None,
                "submitted": True,
                "submitting": False,
                "awaiting_create_confirmation": False,
                "submit_failed": False,
                "last_submit_error": None,
                "last_submit_name": property_name,
                "property_id": pid,
            },
        )
        LOGGER.info(
            "[create_property:copilot] server_create done property_id=%s token=%s",
            pid,
            row.get("token_address"),
        )
        return ToolResult(
            ok=True,
            data={
                **data,
                "filled": accumulated,
                "missing": [],
                "submitted": True,
                "submitting": False,
                "property_id": pid,
                "token_address": row.get("token_address"),
                "success_message": success,
                "speak_to_user": success,
                "speak_verbatim": True,
                "instruction": (
                    "Read speak_to_user verbatim — the property was created and deployed."
                ),
            },
            actions=[
                AgentAction(type="NAVIGATE", route="/property_owner/properties"),
            ],
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        LOGGER.error(
            "[create_property:copilot] server_create failed name=%r http_detail=%s",
            property_name,
            detail,
        )
        return _create_property_submit_failure_result(
            accumulated, data, detail=str(detail), property_name=property_name
        )
    except ValueError as exc:
        LOGGER.error(
            "[create_property:copilot] server_create failed name=%r validation=%s",
            property_name,
            exc,
        )
        return _create_property_submit_failure_result(
            accumulated, data, detail=str(exc), property_name=property_name
        )
    except Exception as exc:
        LOGGER.exception(
            "[create_property:copilot] server_create failed name=%r",
            property_name,
        )
        return _create_property_submit_failure_result(
            accumulated,
            data,
            detail=str(exc)[:300],
            property_name=property_name,
        )


def _handle_create_property_confirmation_turn(
    args: dict,
    pre_session: dict[str, Any],
    user: AuthUser,
    db: Any,
    *,
    bootstrap_for_turn: bool,
    needs_ui_bootstrap: bool,
    had_active_session: bool,
) -> ToolResult | None:
    """Dedicated yes/no turn — submit or cancel from session draft without re-collecting fields."""
    filled = _backfill_create_property_filled_from_history(
        normalize_create_property_accumulated(dict(pre_session.get("filled") or {}))
    )
    if filled != (pre_session.get("filled") or {}):
        _persist_create_property_filled(
            filled,
            next_field=pre_session.get("next_field"),
            awaiting_create_confirmation=bool(
                pre_session.get("awaiting_create_confirmation")
                or pre_session.get("submit_failed")
            ),
            submit_failed=bool(pre_session.get("submit_failed")),
            last_submit_error=pre_session.get("last_submit_error"),
        )
    awaiting = bool(
        pre_session.get("awaiting_create_confirmation")
        or pre_session.get("submit_failed")
    )
    complete = _create_property_required_fields_present(filled)
    if not awaiting and not complete:
        return None

    confirm = _create_property_confirmation_reply(args)
    if confirm is True and complete:
        in_flight = _create_property_submit_in_flight_block(pre_session)
        if in_flight is not None:
            return in_flight
        return _create_property_submit_result(
            filled,
            {"filled": filled},
            user,
            db,
            bootstrap_for_turn=bootstrap_for_turn,
            needs_ui_bootstrap=needs_ui_bootstrap,
            had_active_session=had_active_session,
        )
    if confirm is False and (awaiting or complete):
        return _create_property_cancel_after_decline()
    if awaiting and _create_property_args_change_fields(args, filled):
        return None
    return None


def _create_property_ui_submit_actions(
    accumulated: dict[str, str], *, bootstrap_ui: bool
) -> list[AgentAction]:
    """Fill every collected field on-screen, then click Create.

    ``bootstrap_ui=True`` is for flows where start_create_property was skipped:
    we navigate/open once before filling. During an active flow we avoid extra
    route/modal bootstrap because it can interrupt an already-mounted dialog.
    """
    modal = "CREATE_PROPERTY"
    actions: list[AgentAction] = []
    if bootstrap_ui:
        actions.extend(
            [
                AgentAction(type="NAVIGATE", route="/property_owner/properties"),
                AgentAction(type="OPEN_MODAL", modal=modal),
            ]
        )
    for field in _CREATE_PROPERTY_FIELDS:
        value = accumulated.get(field)
        if value in (None, ""):
            continue
        actions.append(
            AgentAction(type="FILL_FIELD", modal=modal, field=field, value=str(value))
        )
    actions.append(
        AgentAction(
            type="SUBMIT_FORM",
            modal=modal,
            form_values={
                field: str(accumulated[field])
                for field in _CREATE_PROPERTY_FIELDS
                if accumulated.get(field) not in (None, "")
            },
        )
    )
    return actions


def _create_property_workflow_active(
    session: dict[str, Any], filled: dict[str, str]
) -> bool:
    if session.get("in_progress") or session.get("awaiting_create_confirmation"):
        return True
    if filled:
        return True
    for msg in reversed(_current_history() or []):
        if _message_role(msg) not in ("ai", "assistant"):
            continue
        text = _message_content(msg).lower()
        if "here are the property details i have" in text:
            return True
        if "what's the name of the property" in text:
            return True
        if "monthly rent" in text and "100 eth" in text:
            return True
    return False


async def try_server_create_property_confirmation(
    user: AuthUser, db: Any
) -> ToolResult | None:
    """Emit the canonical confirmation summary without waiting for the LLM to paraphrase it.

    When every field is collected (including monthly rent) but the model replies in
    free text instead of calling fill_create_property, this keeps Edit/Delete in chat.
    """
    if canonical_role(user.role) != "property_owner":
        return None
    if _latest_human_yes_no_reply() is not None:
        return None

    pre_session = _reconcile_create_property_session_after_outcome(
        _get_workflow_session(_CREATE_PROPERTY_MODAL) or {}
    )
    if pre_session.get("chat_property_limit_reached"):
        return None
    if pre_session.get("submitting") and not pre_session.get("submit_failed"):
        return None
    if pre_session.get("awaiting_create_confirmation"):
        return None

    filled = _backfill_create_property_filled_from_history(
        normalize_create_property_accumulated(dict(pre_session.get("filled") or {}))
    )
    if not _create_property_workflow_active(pre_session, filled):
        return None
    if not _create_property_required_fields_present(filled):
        return None

    probe = _merge_last_user_utterance(
        dict(filled),
        _CREATE_PROPERTY_MODAL,
        _CREATE_PROPERTY_FIELDS,
        _CREATE_PROPERTY_FIELDS[:5],
    )
    probe = normalize_create_property_accumulated(probe)
    if _create_property_needs_monthly_rent_collection(probe):
        return None

    result = await _fill_create_property({}, user, db)
    data = result.data or {}
    if not data.get("awaiting_create_confirmation"):
        return None
    speak = str(data.get("speak_to_user") or "").strip()
    if not speak:
        return None
    return result


async def try_server_create_property_submit(
    user: AuthUser, db: Any
) -> ToolResult | None:
    """Submit after the user said Yes without waiting for the LLM tool round-trip."""
    eligible, _ = create_property_server_submit_eligible(user)
    if not eligible:
        return None
    return await _fill_create_property({}, user, db)


async def _fill_create_property(args: dict, user: AuthUser, db: Any) -> ToolResult:
    """Drive the Create Property workflow and create the listing on submit.

    While collecting fields we emit FILL_FIELD / OPEN_MODAL actions for the UI.
    When the user confirms Yes (``confirm_create=true``), the server runs the same
    pipeline as ``POST /properties/stream`` (DB insert, token deploy, inventory, rent)
    and returns ``success_message`` — no browser form submit required.
    """
    force_ui_bootstrap = bool(args.pop("_force_create_property_bootstrap", False))
    LOGGER.info("[fill_create_property] args=%s", args)

    _sync_create_property_limit_from_success_announcement()

    pre_session = _reconcile_create_property_session_after_outcome(
        _get_workflow_session(_CREATE_PROPERTY_MODAL)
    )

    blocked = _block_create_property_when_chat_limit_reached()
    if blocked is not None:
        return blocked

    # Abandoned draft + user asks to create again (often after copilot refresh) without
    # passing new field values yet — drop the stale server session.
    if (
        _human_requested_new_create_property_listing()
        and not _create_property_args_change_fields(args, pre_session.get("filled"))
        and pre_session.get("in_progress")
        and not pre_session.get("submitted")
        and not pre_session.get("awaiting_create_confirmation")
        and not pre_session.get("submit_failed")
        and not _create_property_chat_limit_reached(pre_session)
    ):
        _clear_workflow_session(_CREATE_PROPERTY_MODAL)
        pre_session = {}

    needs_ui_bootstrap = force_ui_bootstrap or _create_property_session_needs_ui_bootstrap(
        pre_session
    )

    # Defensive reset: if a stale in-progress session exists but the user starts
    # naming a different property, treat this as a new create workflow. This
    # covers same-chat "create another property" turns even when the model
    # skips start_create_property.
    incoming_name_raw = args.get("name")
    incoming_name = (
        normalize_create_property_field("name", str(incoming_name_raw))
        if incoming_name_raw not in (None, "")
        else ""
    )
    session_name = str((pre_session.get("filled") or {}).get("name") or "").strip()
    if (
        incoming_name
        and session_name
        and incoming_name.lower() != session_name.lower()
        and pre_session.get("in_progress")
        and not _create_property_chat_limit_reached(pre_session)
    ):
        _clear_workflow_session(_CREATE_PROPERTY_MODAL)
        pre_session = {}
        needs_ui_bootstrap = True
    had_active_session = bool(
        (pre_session.get("in_progress") or pre_session.get("awaiting_create_confirmation"))
        and not _create_property_chat_limit_reached(pre_session)
    )
    bootstrap_for_turn = needs_ui_bootstrap

    confirmation_turn = _handle_create_property_confirmation_turn(
        args,
        pre_session,
        user,
        db,
        bootstrap_for_turn=bootstrap_for_turn,
        needs_ui_bootstrap=needs_ui_bootstrap,
        had_active_session=had_active_session,
    )
    if confirmation_turn is not None:
        return confirmation_turn

    result = _build_fill_workflow(
        args,
        modal="CREATE_PROPERTY",
        tool_name="fill_create_property",
        fields=_CREATE_PROPERTY_FIELDS,
        required=_CREATE_PROPERTY_FIELDS[:5],
    )

    data = dict(result.data or {})
    actions = list(result.actions)
    accumulated = normalize_create_property_accumulated(dict(data.get("filled") or {}))
    accumulated = _backfill_create_property_filled_from_history(accumulated)
    required = _CREATE_PROPERTY_FIELDS[:5]
    missing = [f for f in required if not accumulated.get(f)]
    data["filled"] = accumulated
    data["missing"] = missing
    if missing:
        data["next_field"] = missing[0]
    elif _create_property_needs_monthly_rent_collection(accumulated):
        data["next_field"] = "monthly_rent_eth"
        missing = []
        data["missing"] = missing
    else:
        data["next_field"] = None
    _persist_create_property_filled(
        accumulated,
        next_field=data.get("next_field"),
        submitted=False,
        awaiting_create_confirmation=False,
    )

    rent_gated = _gate_create_property_monthly_rent_value(
        accumulated, data=data, actions=actions
    )
    if rent_gated is not None:
        return rent_gated

    if _create_property_needs_monthly_rent_collection(accumulated) and not args.get(
        "monthly_rent_eth"
    ):
        return _create_property_prompt_for_monthly_rent(
            accumulated, data=data, actions=actions
        )

    confirm = _create_property_confirmation_reply(args)
    if confirm is False and (
        pre_session.get("awaiting_create_confirmation")
        or _create_property_required_fields_present(accumulated)
    ):
        return _create_property_cancel_after_decline()
    if not missing and confirm is True and _create_property_required_fields_present(accumulated):
        return _create_property_submit_result(
            accumulated,
            data,
            user,
            db,
            bootstrap_for_turn=bootstrap_for_turn,
            needs_ui_bootstrap=needs_ui_bootstrap,
            had_active_session=had_active_session,
        )

    if not missing:
        return _create_property_confirmation_prompt(
            accumulated,
            actions=actions,
            data=data,
            bootstrap_for_turn=bootstrap_for_turn,
            needs_ui_bootstrap=needs_ui_bootstrap,
            had_active_session=had_active_session,
            pre_session=pre_session,
        )

    LOGGER.info(
        "[fill_create_property] filled=%s missing=%s next=%s actions=%d",
        data.get("filled"),
        data.get("missing"),
        data.get("next_field"),
        len(actions),
    )
    # If the model skipped start_create_property, bootstrap the UI once so subsequent
    # FILL_FIELD actions have a mounted form target. During an active workflow we avoid
    # OPEN_MODAL because the dialog listener resets form state on open.
    if needs_ui_bootstrap or not had_active_session:
        actions = [
            AgentAction(type="NAVIGATE", route="/property_owner/properties"),
            AgentAction(type="OPEN_MODAL", modal=_CREATE_PROPERTY_MODAL),
            *actions,
        ]
    field_speak = create_property_field_collection_speak(
        str(data.get("next_field") or ""),
        accumulated,
    )
    if field_speak:
        data["speak_to_user"] = field_speak
        data["speak_verbatim"] = True
        data["instruction"] = "Read speak_to_user verbatim — do not rephrase the ticker question."
    return ToolResult(ok=result.ok, data=data, error=result.error, actions=actions)


register(ToolSpec(
    name="fill_create_property",
    description=(
        "Drive the chat-only Create Property workflow. Call this every time the "
        "user answers a field — pass only the NEW value(s); the server merges "
        "them with everything already filled. The result includes `filled` "
        "(every value collected so far), `missing` (required fields still "
        "empty), and `next_field` (the single field to ask about next). "
        "NEVER ask about a field that already appears in `filled`. When "
        "`missing` is empty the server shows a confirmation summary — the user "
        "must reply Yes before the listing is created (pass confirm_create=true "
        "after Yes — the server deploys on-chain). Pass spoken numbers as-is "
        "(e.g. 'one lakh tokens', 'USD symbol') — the server normalizes them. "
        "Do not call more tools after a successful submit. Only one property "
        "may be created per chat session; after success, further calls return "
        "speak_to_user telling the user to refresh for a new chat."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Property display name, e.g. 'Oceanview Apartments'."},
            "location": {"type": "string", "description": "City / location string."},
            "total_value": {"type": "string", "description": "Total property value in ETH, e.g. '10' or '12.5'."},
            "token_supply": {"type": "string", "description": "Total number of ownership tokens to mint, e.g. '10000'."},
            "token_symbol": {"type": "string", "description": "Short ticker for the token, e.g. 'OCEAN'."},
            "monthly_rent_eth": {
                "type": "string",
                "description": (
                    "Optional monthly rent in ETH — must be less than 100 ETH "
                    "(on-chain limit). Use 0 or skip if no rent yet."
                ),
            },
            "submit": {
                "type": "boolean",
                "description": (
                    "Legacy flag — submission is gated by confirm_create after the "
                    "user approves the confirmation summary."
                ),
            },
            "confirm_create": {
                "type": "boolean",
                "description": (
                    "Only when awaiting_create_confirmation is true in the tool result: "
                    "true = user said Yes, submit the listing; false = user said No, "
                    "clear details and restart collection."
                ),
            },
        },
        "additionalProperties": False,
    },
    roles=frozenset({"property_owner"}),
    handler=_fill_create_property,
))


_ACTIVITY_QUERIES = (
    "SELECT 1 FROM token_ownerships WHERE property_id = %s AND token_amount > 0 LIMIT 1",
    "SELECT 1 FROM investments WHERE property_id = %s LIMIT 1",
    "SELECT 1 FROM transactions WHERE property_id = %s LIMIT 1",
    "SELECT 1 FROM rent_payments WHERE property_id = %s LIMIT 1",
    "SELECT 1 FROM rent_distributions WHERE property_id = %s LIMIT 1",
    "SELECT 1 FROM investor_rent_payouts WHERE property_id = %s LIMIT 1",
)


def _property_has_activity(cursor, prop: dict) -> bool:
    if prop.get("token_address") or prop.get("nft_token_id"):
        return True
    pid = int(prop["id"])
    for q in _ACTIVITY_QUERIES:
        cursor.execute(q, (pid,))
        if cursor.fetchone():
            return True
    return False


async def _delete_property(args: dict, user: AuthUser, db: Any) -> ToolResult:
    pid = args.get("property_id")
    if not pid:
        return ToolResult(ok=False, error="property_id is required.")
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return ToolResult(ok=False, error="property_id must be an integer.")

    cursor = db.cursor(dictionary=True)
    try:
        prop = lock_property(cursor, pid)
        if not prop:
            return ToolResult(ok=False, error=f"Property {pid} not found.")
        owner = normalize_address(prop.get("owner_wallet") or "")
        if not owner or owner != normalize_address(user.wallet_address):
            return ToolResult(ok=False, error="You can only delete properties you own.")

        name = prop.get("name") or f"Property {pid}"
        if _property_has_activity(cursor, prop):
            cursor.execute("UPDATE properties SET is_active = FALSE WHERE id = %s", (pid,))
            mode = "archived"
        else:
            cursor.execute("DELETE FROM properties WHERE id = %s", (pid,))
            mode = "deleted"
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return ToolResult(ok=False, error=str(exc)[:300])
    finally:
        cursor.close()

    return ToolResult(
        ok=True,
        data={"property_id": pid, "name": name, "mode": mode},
        actions=[AgentAction(type="NAVIGATE", route="/property_owner/properties")],
    )


register(ToolSpec(
    name="delete_property",
    description=(
        "Delete or archive a property the signed-in property owner owns. If the "
        "property has any on-chain or rental activity it is archived "
        "(is_active=false); otherwise it is hard-deleted. The action navigates "
        "to /property_owner/properties so the list refreshes. Resolve the "
        "property by name via get_my_owned_properties first if you don't "
        "already have its id."
    ),
    parameters={
        "type": "object",
        "properties": {
            "property_id": {"type": "integer", "description": "ID of the property to remove."},
        },
        "required": ["property_id"],
        "additionalProperties": False,
    },
    roles=frozenset({"property_owner"}),
    handler=_delete_property,
))


# ---------------------------------------------------------------------------
# Edit property workflow — uses the existing EDIT_PROPERTY dialog wired into
# the property cards.
# ---------------------------------------------------------------------------

_EDIT_PROPERTY_FIELDS = (
    "name",
    "location",
    "total_value",
    "token_supply",
    "token_symbol",
    "monthly_rent_eth",
)


async def _start_edit_property(args: dict, user: AuthUser, db: Any) -> ToolResult:
    pid = args.get("property_id")
    if pid is None:
        return ToolResult(ok=False, error="property_id is required.")
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return ToolResult(ok=False, error="property_id must be an integer.")
    cursor = db.cursor(dictionary=True)
    try:
        prop = fetch_active_property(cursor, pid)
        if not prop:
            return ToolResult(ok=False, error=property_unavailable_message(pid))
        owner = normalize_address(prop.get("owner_wallet") or "")
        if not owner or owner != normalize_address(user.wallet_address):
            return ToolResult(ok=False, error="You can only edit properties you own.")
    finally:
        cursor.close()
    return ToolResult(
        ok=True,
        data={
            "property_id": pid,
            "property_name": prop.get("name"),
            "message": f"Opening edit form for {prop.get('name')}.",
        },
        actions=[
            AgentAction(type="NAVIGATE", route="/property_owner/properties"),
            AgentAction(type="OPEN_MODAL", modal="EDIT_PROPERTY", property_id=pid),
        ],
    )


register(ToolSpec(
    name="start_edit_property",
    description=(
        "Open the Edit Property dialog for a property the signed-in owner "
        "owns. Resolve the id via get_my_owned_properties or list_properties "
        "first if you only have a name. After this, call fill_edit_property "
        "for each value the user wants to change."
    ),
    parameters={
        "type": "object",
        "properties": {
            "property_id": {"type": "integer", "description": "ID of the property to edit."},
        },
        "required": ["property_id"],
        "additionalProperties": False,
    },
    roles=frozenset({"property_owner"}),
    handler=_start_edit_property,
))


async def _fill_edit_property(args: dict, _user: AuthUser, _db: Any) -> ToolResult:
    LOGGER.info("[fill_edit_property] Called with args: %s", args)
    # At minimum we need ONE changed field to submit; required=() means we
    # accept submission as soon as the user is done answering.
    return _build_fill_workflow(
        args,
        modal="EDIT_PROPERTY",
        tool_name="fill_edit_property",
        fields=_EDIT_PROPERTY_FIELDS,
        required=(),
    )


register(ToolSpec(
    name="fill_edit_property",
    description=(
        "Fill one or more fields on the open Edit Property dialog. Only pass "
        "the fields the user wants to change — the rest keep their current "
        "values. Pass `submit=true` on the final call to save. The server "
        "merges values across turns so you only ever need to send what is "
        "new."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Updated property name."},
            "location": {"type": "string", "description": "Updated location."},
            "total_value": {"type": "string", "description": "Updated total value in ETH (locked if SecurityToken already deployed)."},
            "token_supply": {"type": "string", "description": "Updated token supply (locked if SecurityToken already deployed)."},
            "token_symbol": {"type": "string", "description": "Updated token symbol (locked if SecurityToken already deployed)."},
            "monthly_rent_eth": {"type": "string", "description": "Updated monthly rent in ETH."},
            "submit": {"type": "boolean", "description": "Set true on the final call to save the edits."},
        },
        "additionalProperties": False,
    },
    roles=frozenset({"property_owner"}),
    handler=_fill_edit_property,
))


async def _start_set_rent(args: dict, user: AuthUser, db: Any) -> ToolResult:
    """Navigate to the rent management page and surface the property the
    user wants to set rent on. Setting rent on-chain requires a MetaMask
    confirmation, which the user does via the Set Rent dialog on
    /property_owner/rent."""
    pid = args.get("property_id")
    if pid is None:
        return ToolResult(ok=False, error="property_id is required.")
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return ToolResult(ok=False, error="property_id must be an integer.")
    cursor = db.cursor(dictionary=True)
    try:
        prop = fetch_active_property(cursor, pid)
        if not prop:
            return ToolResult(ok=False, error=property_unavailable_message(pid))
        owner = normalize_address(prop.get("owner_wallet") or "")
        if not owner or owner != normalize_address(user.wallet_address):
            return ToolResult(ok=False, error="You can only set rent on properties you own.")
        if not prop.get("token_address"):
            return ToolResult(
                ok=False,
                error=(
                    f"{prop.get('name')} doesn't have its SecurityToken deployed yet — "
                    "rent can only be set after deployment."
                ),
            )
    finally:
        cursor.close()
    return ToolResult(
        ok=True,
        data={
            "property_id": pid,
            "property_name": prop.get("name"),
            "message": f"Opening the rent page for {prop.get('name')}.",
        },
        actions=[AgentAction(type="NAVIGATE", route="/property_owner/rent")],
    )


register(ToolSpec(
    name="start_set_rent",
    description=(
        "Open the rent management page so the owner can set or update the "
        "monthly rent on a property they own. Setting rent on-chain requires "
        "a MetaMask signature, so we only navigate the user to the right "
        "page rather than auto-submitting. Resolve property_id via "
        "get_my_owned_properties or list_properties first."
    ),
    parameters={
        "type": "object",
        "properties": {
            "property_id": {"type": "integer", "description": "ID of the property to set rent on."},
        },
        "required": ["property_id"],
        "additionalProperties": False,
    },
    roles=frozenset({"property_owner"}),
    handler=_start_set_rent,
))


_INVEST_MODAL = "INVEST_PROPERTY"
_INVEST_FIELDS = ("property_name", "token_amount")
_INVEST_REQUIRED = ("property_name", "token_amount")


def invest_workflow_session() -> dict:
    """Current guided-invest session for this thread (used by agent guards)."""
    return _get_workflow_session(_INVEST_MODAL)


def _validate_property_investable(prop: dict) -> str | None:
    if not prop.get("token_address"):
        name = prop.get("name") or "This property"
        return f"{name} is not open for investment yet — no token contract is deployed."
    try:
        available = int(str(prop.get("tokens_available") or "0"))
    except (TypeError, ValueError):
        available = 0
    if available <= 0:
        name = prop.get("name") or "This property"
        return f"{name} has no tokens available for sale right now."
    return None


def _resolve_property_by_name(db: Any, name: str) -> tuple[dict | None, str | None]:
    """Fuzzy-match a spoken property name to a single investable listing."""
    query = (name or "").strip()
    cursor = db.cursor(dictionary=True)
    try:
        items = _list_properties(cursor)
    finally:
        cursor.close()
    return _resolve_investable_property_from_items(items, query)


def _invest_actions_on_submit(property_id: int, token_amount: str) -> list[AgentAction]:
    """Navigate, open dialog, fill amount, and click Invest (MetaMask confirm is manual)."""
    pid = int(property_id)
    amount = str(int(token_amount))
    return [
        AgentAction(type="NAVIGATE", route="/investor/marketplace"),
        AgentAction(type="OPEN_MODAL", modal=_INVEST_MODAL, property_id=pid),
        AgentAction(
            type="FILL_FIELD",
            modal=_INVEST_MODAL,
            field="token_amount",
            value=amount,
            property_id=pid,
        ),
        AgentAction(type="SUBMIT_FORM", modal=_INVEST_MODAL, property_id=pid),
    ]


def _load_invest_property_row(db: Any, property_id: int) -> dict | None:
    """Fresh property row with supply and sale price for invest funding checks."""
    cursor = db.cursor(dictionary=True)
    try:
        row = lock_property(cursor, property_id)
        if not row:
            return None
        return enrich_property_with_supply(cursor, row)
    finally:
        cursor.close()


def _gate_invest_funding(
    user: AuthUser,
    property_item: dict,
    token_amount: int,
    accumulated: dict[str, str],
) -> ToolResult | None:
    """Block MetaMask when wallet ETH is below the order total."""
    try:
        funding = check_investor_can_fund_investment(
            user.wallet_address or "",
            property_item,
            token_amount,
        )
    except InvestmentFundingError as exc:
        return ToolResult(
            ok=False,
            error=str(exc),
            data={
                "filled": accumulated,
                "missing": [],
                "submitted": False,
                "next_field": "token_amount",
            },
        )

    if funding.ok:
        return None

    _set_workflow_session(
        _INVEST_MODAL,
        {
            "in_progress": True,
            "filled": accumulated,
            "next_field": "token_amount",
            "submitted": False,
            "completing_submit": False,
            "property_id": int(property_item.get("id") or 0) or None,
        },
    )
    return ToolResult(
        ok=True,
        data={
            "filled": accumulated,
            "missing": [],
            "submitted": False,
            "insufficient_funds": True,
            "required_eth": funding.required_eth,
            "wallet_eth": funding.balance_eth,
            "shortfall_eth": funding.shortfall_eth,
            "speak_to_user": funding.speak_to_user,
            "instruction": funding.instruction,
        },
        actions=[],
    )


async def _start_invest_property(_args: dict, _user: AuthUser, _db: Any) -> ToolResult:
    """Begin guided invest: ask property name first, then token amount."""
    user_text = extract_last_human_utterance(_current_history())
    if not (has_explicit_invest_intent(user_text) or wants_to_begin_invest_workflow(user_text)):
        return ToolResult(
            ok=False,
            error=invest_tool_blocked_message(),
            data={"blocked_wallet_ui": True, "modal": _INVEST_MODAL},
        )

    modal = _INVEST_MODAL
    session = _get_workflow_session(modal)
    if session.get("submitted") or not session.get("filled"):
        _clear_workflow_session(modal)
        session = {}
    filled = dict(session.get("filled") or {})
    missing = [f for f in _INVEST_REQUIRED if f not in filled or not filled.get(f)]
    next_field = missing[0] if missing else "property_name"
    _set_workflow_session(
        modal,
        {
            "in_progress": True,
            "filled": filled,
            "next_field": next_field,
            "submitted": False,
            "completing_submit": False,
        },
    )
    instruction = (
        f"Already collected: {', '.join(f'{k}={v}' for k, v in filled.items())}. "
        f"Ask for {next_field} only — do NOT re-ask fields already in filled."
        if filled
        else "Ask: Which property would you like to invest in? (property name)"
    )
    return ToolResult(
        ok=True,
        data={
            "message": "Starting guided investment.",
            "filled": filled,
            "missing": missing,
            "next_field": next_field,
            "instruction": instruction,
        },
        actions=[AgentAction(type="NAVIGATE", route="/investor/marketplace")],
    )


register(ToolSpec(
    name="start_invest_property",
    description=(
        "MANDATORY first step when the user wants to invest / buy tokens but has not "
        "finished the guided form. Opens the marketplace and asks which property they "
        "want (property name first, then token amount via fill_invest_property). Call "
        "this when they say 'I want to invest' even if they did not name a property yet."
    ),
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    roles=frozenset({"investor"}),
    handler=_start_invest_property,
))


async def _fill_invest_property(args: dict, _user: AuthUser, db: Any) -> ToolResult:
    """Collect property name + token amount, then auto-fill and submit the invest form."""
    modal = _INVEST_MODAL
    tool_name = "fill_invest_property"
    accumulated = _recover_form_state(modal, tool_name, _INVEST_FIELDS)

    for field in _INVEST_FIELDS:
        value = args.get(field)
        if value is None or value == "":
            continue
        accumulated[field] = str(value).strip()

    accumulated = _merge_last_user_utterance(
        accumulated, modal, _INVEST_FIELDS, _INVEST_REQUIRED
    )

    property_id: int | None = None
    resolved_name: str | None = None
    resolved_prop: dict | None = None
    if accumulated.get("property_name"):
        prop, err = _resolve_property_by_name(db, accumulated["property_name"])
        if err:
            missing = [f for f in _INVEST_REQUIRED if f not in accumulated or not accumulated.get(f)]
            return ToolResult(
                ok=False,
                error=err,
                data={
                    "filled": accumulated,
                    "missing": missing,
                    "next_field": "property_name",
                    "submitted": False,
                },
            )
        resolved_prop = prop
        property_id = int(prop["id"])
        resolved_name = str(prop.get("name") or accumulated["property_name"])
        accumulated["property_id"] = str(property_id)
        accumulated["property_name"] = resolved_name

    missing = [f for f in _INVEST_REQUIRED if f not in accumulated or not accumulated.get(f)]
    submit = bool(args.get("submit"))
    next_field = missing[0] if missing else None

    # Reliability guard: if all required invest fields are already present,
    # auto-submit in this same turn so the workflow does not stall waiting for
    # the model to make an extra submit=true tool call.
    if not submit and not missing and property_id is not None:
        return await _fill_invest_property({**args, "submit": True}, _user, db)

    instruction: str | None = None
    if accumulated and next_field:
        instruction = (
            "Already collected: "
            + ", ".join(f"{k}={v!r}" for k, v in accumulated.items())
            + f". Ask the user for {next_field} next. "
            "Do NOT re-ask for any field already in filled."
        )
    elif not missing:
        instruction = (
            "All required fields are collected. Call this tool again with submit=true "
            "to fill the invest form and open MetaMask for the user to confirm."
        )

    if submit and not missing and property_id is not None:
        try:
            token_amount = int(accumulated["token_amount"])
        except (TypeError, ValueError):
            return ToolResult(
                ok=False,
                error="token_amount must be a whole number of tokens.",
                data={"filled": accumulated, "missing": ["token_amount"], "next_field": "token_amount"},
            )
        if token_amount < 1:
            return ToolResult(
                ok=False,
                error="token_amount must be at least 1.",
                data={"filled": accumulated, "missing": ["token_amount"], "next_field": "token_amount"},
            )

        property_row = resolved_prop
        if db is not None:
            property_row = _load_invest_property_row(db, property_id) or property_row
        if not property_row:
            return ToolResult(
                ok=False,
                error="Property not found for investment.",
                data={"filled": accumulated, "missing": [], "submitted": False},
            )
        investable_err = _validate_property_investable(property_row)
        if investable_err:
            return ToolResult(
                ok=False,
                error=investable_err,
                data={
                    "filled": accumulated,
                    "missing": [],
                    "submitted": False,
                    "next_field": "property_name",
                },
            )

        funding_block = _gate_invest_funding(
            _user, property_row, token_amount, accumulated
        )
        if funding_block is not None:
            return funding_block

        _set_workflow_session(
            modal,
            {
                "in_progress": False,
                "filled": accumulated,
                "next_field": None,
                "submitted": True,
                "completing_submit": True,
                "property_id": property_id,
            },
        )
        speak = (
            f"I've filled your investment in {resolved_name} for {token_amount} tokens. "
            "Confirm the payment in MetaMask when it opens."
        )
        actions = _invest_actions_on_submit(property_id, str(token_amount))
        return ToolResult(
            ok=True,
            data={
                "filled": accumulated,
                "missing": [],
                "submitted": True,
                "property_id": property_id,
                "property_name": resolved_name,
                "token_amount": token_amount,
                "success_message": speak,
                "speak_to_user": speak,
                "instruction": "Tell the user to confirm the transaction in MetaMask.",
            },
            actions=actions,
        )

    if submit and missing:
        return ToolResult(
            ok=False,
            error=(
                "Cannot submit yet. Still missing: "
                + ", ".join(missing)
                + f". Ask the user for {next_field} next."
            ),
            data={
                "filled": accumulated,
                "missing": missing,
                "submitted": False,
                "next_field": next_field,
                "instruction": instruction,
            },
        )

    _set_workflow_session(
        modal,
        {
            "in_progress": True,
            "filled": accumulated,
            "next_field": next_field,
            "submitted": False,
            "completing_submit": False,
            "property_id": property_id,
        },
    )
    return ToolResult(
        ok=True,
        data={
            "filled": accumulated,
            "missing": missing,
            "submitted": False,
            "next_field": next_field,
            "property_id": property_id,
            "property_name": resolved_name,
            "instruction": instruction,
        },
        actions=[],
    )


register(ToolSpec(
    name="fill_invest_property",
    description=(
        "Drive the guided invest workflow. Call after start_invest_property whenever "
        "the user answers a field — pass only NEW values; the server merges prior turns. "
        "Field order: property_name first, then token_amount. Result includes filled, "
        "missing, and next_field. When missing is empty, call again with submit=true "
        "to auto-fill the form and open MetaMask (user taps Confirm in the wallet)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "property_name": {
                "type": "string",
                "description": "Spoken property name, e.g. 'Sunset Villas' or 'ocean view'.",
            },
            "token_amount": {
                "type": "string",
                "description": "Whole number of tokens to buy, e.g. '10'.",
            },
            "submit": {
                "type": "boolean",
                "description": (
                    "Set true on the FINAL call once property_name and token_amount are "
                    "filled — auto-fills the invest dialog and triggers MetaMask."
                ),
            },
        },
        "additionalProperties": False,
    },
    roles=frozenset({"investor"}),
    handler=_fill_invest_property,
))


async def _start_invest(args: dict, _user: AuthUser, db: Any) -> ToolResult:
    """Legacy one-shot entry — prefer start_invest_property + fill_invest_property."""
    user_text = extract_last_human_utterance(_current_history())
    if not has_explicit_invest_intent(user_text):
        return ToolResult(
            ok=False,
            error=invest_tool_blocked_message(),
            data={"blocked_wallet_ui": True, "modal": _INVEST_MODAL},
        )
    pid = args.get("property_id")
    token_amount = args.get("token_amount")
    if not pid:
        return await _start_invest_property({}, _user, db)

    cursor = db.cursor(dictionary=True)
    try:
        row = fetch_active_property(cursor, int(pid))
        if not row:
            return ToolResult(ok=False, error=property_unavailable_message(int(pid)))
        prop = _serialize_property(enrich_property_with_supply(cursor, row))
        err = _validate_property_investable(prop)
    finally:
        cursor.close()
    if err:
        return ToolResult(ok=False, error=err)

    if token_amount is None:
        return await _fill_invest_property(
            {"property_name": str(prop.get("name") or "")},
            _user,
            db,
        )
    return await _fill_invest_property(
        {
            "property_name": str(prop.get("name") or ""),
            "token_amount": str(int(token_amount)),
            "submit": True,
        },
        _user,
        db,
    )


register(ToolSpec(
    name="start_invest",
    description=(
        "Prefer start_invest_property + fill_invest_property for the guided flow. "
        "One-shot shortcut only when you already have property_id and token_amount."
    ),
    parameters={
        "type": "object",
        "properties": {
            "property_id": {"type": "integer", "description": "ID of the property to invest in."},
            "token_amount": {"type": "integer", "minimum": 1, "description": "Number of whole tokens to purchase."},
        },
        "additionalProperties": False,
    },
    roles=frozenset({"investor"}),
    handler=_start_invest,
))


_PAY_RENT_MODAL = "PAY_RENT"
_PAY_RENT_FIELDS = ("property_name",)
_PAY_RENT_REQUIRED = ("property_name",)


def pay_rent_workflow_session() -> dict:
    """Current guided pay-rent session for this thread."""
    return _get_workflow_session(_PAY_RENT_MODAL)


def _ensure_rent_chain_ready_for_payment(cursor, property_item: dict, property_id: int) -> int:
    """Register property, sync rent amount, and sync investors before tenant pays."""
    ensure_rent_property_registered(cursor, property_item, property_id)
    sync_rent_amount_to_contract(cursor, property_item, property_id)
    synced = sync_investors_to_contract(cursor, property_id)
    return len(synced)


def _resolve_property_for_rent(
    db: Any, name: str, *, tenant_wallet: str | None = None
) -> tuple[dict | None, str | None]:
    """Fuzzy-match a spoken property name to a tenant-dashboard rent listing."""
    query = (name or "").strip()
    cursor = db.cursor(dictionary=True)
    try:
        items = _tenant_property_items(cursor, tenant_wallet)
    finally:
        cursor.close()
    return _resolve_rentable_property_from_items(items, query)


def _pay_rent_actions_on_submit(property_id: int) -> list[AgentAction]:
    pid = int(property_id)
    return [
        AgentAction(type="NAVIGATE", route="/tenant/rentals"),
        AgentAction(type="OPEN_MODAL", modal=_PAY_RENT_MODAL, property_id=pid),
        AgentAction(type="SUBMIT_FORM", modal=_PAY_RENT_MODAL, property_id=pid),
    ]


def _rent_period_already_paid_result(prop: dict, period: dict) -> ToolResult:
    next_due = period.get("next_due_at")
    next_due_iso = next_due.isoformat() if next_due else None
    next_due_label = next_due.strftime("%B %d, %Y") if next_due else "next cycle"
    pid = int(prop["id"])
    return ToolResult(
        ok=False,
        error=(
            f"Rent for {prop['name']} is already paid for this cycle — "
            f"next due {next_due_label}."
        ),
        data={
            "already_paid": True,
            "property_id": pid,
            "property_name": prop["name"],
            "next_due_at": next_due_iso,
            "next_due_label": next_due_label,
            "rent_cycle_label": period.get("rent_cycle_label"),
        },
    )


def _http_detail_message(detail: Any) -> str:
    if isinstance(detail, dict):
        return str(detail.get("message") or detail)
    return str(detail)


async def _execute_pay_rent_ui(property_id: int, user: AuthUser, db: Any) -> ToolResult:
    """Validate rent status, sync on-chain rent state, then open MetaMask via the UI."""
    pid = int(property_id)
    cursor = db.cursor(dictionary=True)
    try:
        prop = fetch_active_property(cursor, pid)
        if not prop:
            return ToolResult(ok=False, error=property_unavailable_message(pid))

        prop = enrich_property_with_supply(cursor, prop)
        serialized = _serialize_property(prop)
        rent_err = _validate_property_rentable(serialized)
        if rent_err:
            return ToolResult(ok=False, error=rent_err)

        rent_fields = build_tenant_property_rent_fields(
            cursor,
            pid,
            tenant_wallet=user.wallet_address if user else None,
        )
        if not tenant_may_pay_rent(rent_fields):
            return ToolResult(
                ok=False,
                error=pay_rent_blocked_message(
                    rent_fields, property_name=str(serialized.get("name") or "this property")
                ),
                data={
                    "already_paid": bool(rent_fields.get("current_cycle_paid")),
                    "claimed_by_other": bool(rent_fields.get("rent_claimed_by_other_tenant")),
                    "property_id": pid,
                    "property_name": serialized.get("name"),
                    "next_due_at": rent_fields.get("next_rent_due_at"),
                    "rent_cycle_label": rent_fields.get("rent_cycle_label"),
                },
            )

        from backend.services.blockchain import get_rent_property_info, platform_deployer_mismatch

        mismatch = platform_deployer_mismatch()
        if mismatch:
            return ToolResult(
                ok=False,
                error=(
                    f"{mismatch.get('message')} "
                    "Rent cannot be prepared until platform contracts are redeployed "
                    "with the wallet in DEPLOYER_PRIVATE_KEY."
                ),
                data={"sync_failed": True, "deployer_mismatch": True},
            )

        try:
            synced_count = _ensure_rent_chain_ready_for_payment(cursor, prop, pid)
            if synced_count and hasattr(db, "commit"):
                db.commit()
        except HTTPException as exc:
            detail = exc.detail
            if isinstance(detail, dict) and detail.get("code") == "DEPLOYER_CONTRACT_MISMATCH":
                return ToolResult(
                    ok=False,
                    error=(
                        f"{detail.get('message')} "
                        "Ask the property owner to redeploy platform contracts and run "
                        "Sync Rent Chain on this property."
                    ),
                    data={"sync_failed": True},
                )
            return ToolResult(
                ok=False,
                error=_http_detail_message(detail),
                data={"sync_failed": True},
            )
        except Exception as sync_exc:  # noqa: BLE001
            err = str(sync_exc)
            LOGGER.warning(
                "execute_pay_rent_ui stage=sync_failed property_id=%s error=%s",
                pid,
                sync_exc,
            )
            if "not the owner" in err or "Ownable" in err:
                return ToolResult(
                    ok=False,
                    error=(
                        "Rent contract sync failed: the backend deployer wallet is not the owner "
                        "of RentDistribution. The property owner must redeploy platform contracts "
                        "with the correct DEPLOYER_PRIVATE_KEY, then use Sync Rent Chain."
                    ),
                    data={"sync_failed": True},
                )
            return ToolResult(
                ok=False,
                error=(
                    f"Could not sync rent contract before payment: {sync_exc}. "
                    "Ask the property owner to verify rent setup."
                ),
                data={"sync_failed": True},
            )

        try:
            info = get_rent_property_info(pid)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                ok=False,
                error=f"Failed to read on-chain rent info: {exc}",
                data={"sync_failed": True},
            )

        if not info.get("active"):
            return ToolResult(
                ok=False,
                error=(
                    "Property is not registered on RentDistribution after sync. "
                    "Ask the owner to set rent and run Sync Rent Chain."
                ),
                data={"sync_failed": True},
            )
        rent_wei = int(info.get("monthly_rent_wei") or 0)
        if rent_wei == 0:
            return ToolResult(
                ok=False,
                error="Monthly rent on-chain is zero. The property owner must set rent first.",
                data={"sync_failed": True},
            )

        try:
            funding = check_tenant_can_pay_monthly_rent(
                user.wallet_address or "",
                rent_wei,
                str(serialized.get("name") or ""),
            )
        except RentPaymentFundingError as exc:
            return ToolResult(
                ok=False,
                error=str(exc),
                data={"property_id": pid, "sync_failed": False},
            )
        if not funding.ok:
            return ToolResult(
                ok=True,
                data={
                    "insufficient_funds": True,
                    "property_id": pid,
                    "property_name": serialized["name"],
                    "monthly_rent_eth": serialized.get("monthly_rent_eth"),
                    "required_eth": funding.required_eth,
                    "wallet_eth": funding.balance_eth,
                    "shortfall_eth": funding.shortfall_eth,
                    "speak_to_user": funding.speak_to_user,
                    "instruction": funding.instruction,
                    "submitted": False,
                },
                actions=[],
            )
    finally:
        cursor.close()

    speak = (
        f"Opening rent payment for {serialized['name']}. "
        "Confirm the transaction in MetaMask when it opens."
    )
    return ToolResult(
        ok=True,
        data={
            "message": speak,
            "property_id": pid,
            "property_name": serialized["name"],
            "monthly_rent_eth": serialized.get("monthly_rent_eth"),
            "success_message": speak,
            "speak_to_user": speak,
        },
        actions=_pay_rent_actions_on_submit(pid),
    )


async def _start_pay_rent_property(_args: dict, _user: AuthUser, _db: Any) -> ToolResult:
    """Begin guided pay rent: collect property name, then open MetaMask."""
    modal = _PAY_RENT_MODAL
    session = _get_workflow_session(modal)
    if session.get("submitted") or not session.get("filled"):
        _clear_workflow_session(modal)
        session = {}
    filled = dict(session.get("filled") or {})
    next_field = "property_name"
    _set_workflow_session(
        modal,
        {
            "in_progress": True,
            "filled": filled,
            "next_field": next_field,
            "submitted": False,
            "completing_submit": False,
        },
    )
    instruction = (
        f"Already collected: {', '.join(f'{k}={v}' for k, v in filled.items())}. "
        f"Ask for {next_field} only — do NOT re-ask fields already in filled."
        if filled
        else "Ask: Which property would you like to pay rent for?"
    )
    return ToolResult(
        ok=True,
        data={
            "workflow": "pay_rent",
            "filled": filled,
            "missing": [f for f in _PAY_RENT_REQUIRED if f not in filled or not filled.get(f)],
            "next_field": next_field,
            "instruction": instruction,
        },
        actions=[],
    )


async def _fill_pay_rent_property(args: dict, user: AuthUser, db: Any) -> ToolResult:
    """Collect property name, sync rent chain, then auto-submit the pay-rent form."""
    modal = _PAY_RENT_MODAL
    tool_name = "fill_pay_rent_property"
    accumulated = _recover_form_state(modal, tool_name, _PAY_RENT_FIELDS)

    for field in _PAY_RENT_FIELDS:
        value = args.get(field)
        if value is None or value == "":
            continue
        accumulated[field] = str(value).strip()

    accumulated = _merge_last_user_utterance(
        accumulated, modal, _PAY_RENT_FIELDS, _PAY_RENT_REQUIRED
    )

    property_id: int | None = None
    resolved_name: str | None = None
    if accumulated.get("property_name"):
        prop, err = _resolve_property_for_rent(
            db, accumulated["property_name"], tenant_wallet=user.wallet_address
        )
        if err:
            missing = [
                f for f in _PAY_RENT_REQUIRED if f not in accumulated or not accumulated.get(f)
            ]
            return ToolResult(
                ok=False,
                error=err,
                data={
                    "filled": accumulated,
                    "missing": missing,
                    "next_field": "property_name",
                    "submitted": False,
                },
            )
        property_id = int(prop["id"])
        resolved_name = str(prop.get("name") or accumulated["property_name"])
        accumulated["property_id"] = str(property_id)
        accumulated["property_name"] = resolved_name

    missing = [f for f in _PAY_RENT_REQUIRED if f not in accumulated or not accumulated.get(f)]
    submit = bool(args.get("submit"))
    next_field = missing[0] if missing else None

    if not submit and not missing and property_id is not None:
        return await _fill_pay_rent_property({**args, "submit": True}, user, db)

    instruction: str | None = None
    if accumulated and next_field:
        instruction = (
            "Already collected: "
            + ", ".join(f"{k}={v!r}" for k, v in accumulated.items())
            + f". Ask the user for {next_field} next."
        )
    elif not missing:
        instruction = (
            "Property name collected. Call this tool again with submit=true "
            "to open MetaMask for the user to confirm rent payment."
        )

    if submit and not missing and property_id is not None:
        result = await _execute_pay_rent_ui(property_id, user, db)
        if not result.ok:
            return ToolResult(
                ok=False,
                error=result.error,
                data={
                    **(result.data or {}),
                    "filled": accumulated,
                    "missing": [],
                    "submitted": False,
                    "property_id": property_id,
                    "property_name": resolved_name,
                },
            )
        _set_workflow_session(
            modal,
            {
                "in_progress": False,
                "filled": accumulated,
                "next_field": None,
                "submitted": True,
                "completing_submit": True,
                "property_id": property_id,
            },
        )
        payload = result.data or {}
        speak = str(payload.get("speak_to_user") or payload.get("message") or "")
        return ToolResult(
            ok=True,
            data={
                "filled": accumulated,
                "missing": [],
                "submitted": True,
                "property_id": property_id,
                "property_name": resolved_name,
                "success_message": speak,
                "speak_to_user": speak,
                "instruction": "Tell the user to confirm the transaction in MetaMask.",
            },
            actions=result.actions,
        )

    if submit and missing:
        return ToolResult(
            ok=False,
            error=(
                "Cannot submit yet. Still missing: "
                + ", ".join(missing)
                + f". Ask the user for {next_field} next."
            ),
            data={
                "filled": accumulated,
                "missing": missing,
                "submitted": False,
                "next_field": next_field,
                "instruction": instruction,
            },
        )

    _set_workflow_session(
        modal,
        {
            "in_progress": True,
            "filled": accumulated,
            "next_field": next_field,
            "submitted": False,
            "completing_submit": False,
            "property_id": property_id,
        },
    )
    return ToolResult(
        ok=True,
        data={
            "filled": accumulated,
            "missing": missing,
            "submitted": False,
            "next_field": next_field,
            "property_id": property_id,
            "property_name": resolved_name,
            "instruction": instruction,
        },
        actions=[],
    )


register(ToolSpec(
    name="start_pay_rent_property",
    description=(
        "Begin the guided pay-rent workflow. Ask which property to pay rent on, "
        "then use fill_pay_rent_property for each user answer."
    ),
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    roles=frozenset({"tenant"}),
    handler=_start_pay_rent_property,
))


register(ToolSpec(
    name="fill_pay_rent_property",
    description=(
        "Drive the guided pay-rent workflow after start_pay_rent_property. Pass only "
        "new values each turn; the server merges prior turns. When property_name is "
        "filled, call again with submit=true to sync rent on-chain and open MetaMask."
    ),
    parameters={
        "type": "object",
        "properties": {
            "property_name": {
                "type": "string",
                "description": "Spoken property name, e.g. 'Oceanview Apartments'.",
            },
            "submit": {
                "type": "boolean",
                "description": (
                    "Set true on the FINAL call once property_name is filled — "
                    "syncs rent and triggers MetaMask."
                ),
            },
        },
        "additionalProperties": False,
    },
    roles=frozenset({"tenant"}),
    handler=_fill_pay_rent_property,
))


async def _start_pay_rent(args: dict, user: AuthUser, db: Any) -> ToolResult:
    """One-shot pay rent when property_id (or property_name) is already known."""
    pid = args.get("property_id")
    name = (args.get("property_name") or "").strip()
    if not pid and not name:
        return ToolResult(ok=False, error="property_id or property_name is required.")
    if not pid:
        prop, err = _resolve_property_for_rent(db, name, tenant_wallet=user.wallet_address)
        if err:
            return ToolResult(ok=False, error=err)
        pid = int(prop["id"])
    return await _execute_pay_rent_ui(int(pid), user, db)


register(ToolSpec(
    name="start_pay_rent",
    description=(
        "Open pay rent when you already know property_id or property_name. "
        "Prefer start_pay_rent_property + fill_pay_rent_property for multi-turn chat."
    ),
    parameters={
        "type": "object",
        "properties": {
            "property_id": {
                "type": "integer",
                "description": "ID of the property to pay rent on.",
            },
            "property_name": {
                "type": "string",
                "description": "Spoken property name — resolved against rent-enabled listings.",
            },
        },
        "additionalProperties": False,
    },
    roles=frozenset({"tenant"}),
    handler=_start_pay_rent,
))


async def _start_claim_rewards(args: dict, _user: AuthUser, db: Any) -> ToolResult:
    user_text = extract_last_human_utterance(_current_history())
    if not has_explicit_claim_intent(user_text):
        return ToolResult(
            ok=False,
            error=claim_tool_blocked_message(),
            data={"blocked_wallet_ui": True, "modal": "CLAIM_REWARDS"},
        )
    pid = args.get("property_id")
    if not pid:
        return ToolResult(ok=False, error="property_id is required.")
    cursor = db.cursor(dictionary=True)
    try:
        prop = fetch_active_property(cursor, int(pid))
        if not prop:
            return ToolResult(ok=False, error=property_unavailable_message(int(pid)))
    finally:
        cursor.close()
    return ToolResult(
        ok=True,
        data={
            "message": (
                f"Opened the claim dialog for {prop['name']}. "
                "The user must tap Claim via MetaMask when ready — never auto-submit from chat."
            ),
            "property_id": int(pid),
        },
        actions=[
            AgentAction(type="NAVIGATE", route="/investor"),
            AgentAction(type="OPEN_MODAL", modal="CLAIM_REWARDS", property_id=int(pid)),
        ],
    )


register(ToolSpec(
    name="start_claim_rewards",
    description=(
        "LAST RESORT — only when the user's latest message explicitly orders a claim "
        "(e.g. 'claim my rewards on Sunset Villas'). Never use for 'how much can I "
        "claim', claimable totals, or claim history — use get_my_claimable_rewards or "
        "get_my_claim_history instead. User confirms in the dialog via MetaMask."
    ),
    parameters={
        "type": "object",
        "properties": {
            "property_id": {"type": "integer", "description": "ID of the property to claim rewards from."},
        },
        "required": ["property_id"],
        "additionalProperties": False,
    },
    roles=frozenset({"investor"}),
    handler=_start_claim_rewards,
))


async def _navigate(args: dict, _user: AuthUser, _db: Any) -> ToolResult:
    route = (args.get("route") or "").strip()
    if not route or not route.startswith("/"):
        return ToolResult(ok=False, error="route must start with '/'.")
    return ToolResult(
        ok=True,
        data={"message": f"Navigating to {route}."},
        actions=[AgentAction(type="NAVIGATE", route=route)],
    )


register(ToolSpec(
    name="navigate",
    description=(
        "Navigate the user to a specific in-app page (e.g. /investor/portfolio, "
        "/tenant/payments). Use this only when the user explicitly asks to go "
        "to a page that no other tool covers."
    ),
    parameters={
        "type": "object",
        "properties": {"route": {"type": "string", "description": "Path starting with '/'."}},
        "required": ["route"],
        "additionalProperties": False,
    },
    roles=ALL_ROLES,
    handler=_navigate,
))
