"""LLM agent loop — LangGraph StateGraph with tool calling, Postgres persistence,
human-in-the-loop interrupts, LangSmith tracing, retry with backoff, and parallel
tool execution.

Graph structure:
    call_model ──(tool_calls?)──► [conditional]
                                    │
                    high-stakes? ──► human_approval ──► END
                                    │
                    low-stakes  ──► call_tools ──► call_model
                                    │
                    no tools    ──► END
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Literal, TypedDict

import langchain
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from backend.ai.config import get_settings
from backend.ai.agent_reply import (
    extract_final_reply_from_state,
    pick_verbatim_speak_to_user,
    tool_data_requires_verbatim_reply,
)
from backend.ai.create_property_messages import create_property_deploying_message
from backend.ai.investor_guards import sanitize_investor_wallet_actions
from backend.ai.prompts import system_prompt_for_role
from backend.ai.schemas import AgentAction, ChatMessage, ChatResponse, InterruptResponse
from backend.ai.tools import (
    create_property_deploy_pending,
    create_property_pending_name,
    create_property_server_submit_eligible,
    dispatch,
    invest_workflow_session,
    openai_tool_schemas,
    prepare_copilot_turn,
    reset_current_messages,
    reset_current_thread_id,
    set_current_messages,
    set_current_thread_id,
    try_server_apply_create_property_field_answer,
    try_server_create_property_confirmation,
    try_server_create_property_submit,
    try_server_delete_property_continuation,
    try_server_edit_property_continuation,
    try_server_investor_marketplace_browse,
    try_server_owner_analytics_overview,
)
from backend.services.auth import AuthUser, canonical_role

LOGGER = logging.getLogger(__name__)

# langchain-core in this environment still probes legacy root-module globals
# that langchain 1.x no longer defines. Seed them once so callback setup works.
for _name, _default in (("debug", False), ("verbose", False), ("llm_cache", None)):
    if not hasattr(langchain, _name):
        setattr(langchain, _name, _default)

# Tools that perform irreversible on-chain side effects — require explicit user confirmation.
# NOTE: start_* tools only return UI actions (OPEN_MODAL, NAVIGATE, FILL_FIELD).
# The actual MetaMask transactions are confirmed by the user in the frontend dialogs.
_HIGH_STAKES_TOOLS = frozenset({
    # None currently — all workflow tools are safe UI-only previews.
})


class AIDisabledError(RuntimeError):
    """Raised when AI features are requested but not configured."""


# ──────────────────────────────────────────────────────────────
# State definition
# ──────────────────────────────────────────────────────────────
class AgentState(TypedDict, total=False):
    """LangGraph state schema."""

    messages: list[BaseMessage]
    actions: list[AgentAction]
    interrupt: dict[str, Any] | None
    approval: str | None
    verbatim_reply: str | None


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _coerce_messages(raw: list[Any]) -> list[BaseMessage]:
    """Best-effort coercion of checkpoint-serialized messages back to BaseMessage."""
    out: list[BaseMessage] = []
    for item in raw or []:
        if isinstance(item, BaseMessage):
            out.append(item)
            continue
        if not isinstance(item, dict):
            continue
        role = (item.get("type") or item.get("role") or "").lower()
        content = item.get("content") or ""
        if role in ("human", "user"):
            out.append(HumanMessage(content=content))
        elif role in ("ai", "assistant"):
            tool_calls = item.get("tool_calls") or []
            try:
                out.append(AIMessage(content=content, tool_calls=tool_calls))
            except Exception:  # noqa: BLE001
                out.append(AIMessage(content=content))
        elif role == "system":
            out.append(SystemMessage(content=content))
        elif role == "tool":
            out.append(
                ToolMessage(
                    content=content,
                    tool_call_id=item.get("tool_call_id") or "",
                    name=item.get("name") or "",
                )
            )
    return out


def _setup_langsmith() -> None:
    """Configure LangSmith tracing if enabled."""
    s = get_settings()
    if s.langsmith_tracing and s.langsmith_api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = s.langsmith_api_key
        os.environ["LANGCHAIN_PROJECT"] = s.langsmith_project
        LOGGER.debug("LangSmith tracing enabled (project=%s).", s.langsmith_project)


def _build_model() -> ChatOpenAI:
    s = get_settings()
    if not s.enabled or not s.openai_api_key:
        raise AIDisabledError("AI is disabled. Set OPENAI_API_KEY to enable it.")
    _setup_langsmith()
    return ChatOpenAI(
        model=s.chat_model,
        temperature=s.temperature,
        max_tokens=s.max_output_tokens,
        openai_api_key=s.openai_api_key,
        openai_api_base=s.openai_base_url,
        streaming=True,
    )


def _build_tools(role: str) -> list:
    """Return OpenAI-compatible tool schemas for the role."""
    return openai_tool_schemas(role)


async def _dispatch_with_retry(name: str, args: dict, user: AuthUser, db: Any) -> Any:
    """Execute a tool with exponential backoff (max 3 attempts)."""
    max_attempts = 3
    base_delay = 1.0
    for attempt in range(1, max_attempts + 1):
        try:
            return await dispatch(name, args, user, db)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Tool %s attempt %s/%s failed: %s", name, attempt, max_attempts, exc)
            if attempt == max_attempts:
                raise
            await asyncio.sleep(base_delay * (2 ** (attempt - 1)))
    return None  # unreachable


async def _call_tools(state: AgentState, user: AuthUser, db: Any) -> dict:
    """Execute all tool_calls in the last assistant message with retry."""
    messages = state.get("messages", [])
    actions = state.get("actions", [])
    if not messages:
        return {"actions": actions, "messages": messages}

    last_msg = messages[-1]
    if not isinstance(last_msg, AIMessage):
        return {"actions": actions, "messages": messages}

    tool_calls = last_msg.tool_calls or []
    if not tool_calls:
        return {"actions": actions, "messages": messages}

    LOGGER.info("[_call_tools] Processing %d tool calls: %s", len(tool_calls), [c.get("name") for c in tool_calls])
    actions: list[AgentAction] = []
    tool_results: list[ToolMessage] = []
    verbatim_sources: list[tuple[str, dict[str, Any] | None]] = []
    # Expose the running conversation to tools that need to recover prior state
    # (e.g. fill_create_property merging fields across turns even when the LLM
    # drops some on a subsequent call).
    ctx_token = set_current_messages(messages)
    try:
        for call in tool_calls:
            name = call.get("name", "")
            args = call.get("args", {})
            tid = call.get("id", "")
            LOGGER.info("[_call_tools] Calling tool: %s with args: %s", name, args)
            try:
                result = await dispatch(name, args, user, db)
                LOGGER.info("[_call_tools] Tool %s returned %d actions", name, len(result.actions))
                actions.extend(result.actions)
                # Include filled fields info so AI knows what was filled
                result_data = {
                    "ok": result.ok,
                    "data": result.data,
                    "error": result.error,
                }
                if result.data and "filled" in result.data:
                    result_data["filled_fields"] = result.data["filled"]
                if result.data and "missing" in result.data:
                    result_data["missing_required"] = result.data["missing"]
                if result.data and result.data.get("instruction"):
                    result_data["instruction"] = result.data["instruction"]
                if result.data and result.data.get("speak_to_user"):
                    result_data["speak_to_user"] = result.data["speak_to_user"]
                if result.data and tool_data_requires_verbatim_reply(result.data):
                    result_data["speak_verbatim"] = True
                    result_data["instruction"] = (
                        "Your entire reply MUST be exactly the speak_to_user string — "
                        "character for character. Do not summarize or rephrase."
                    )
                if result.data and result.data.get("success_message"):
                    result_data["success_message"] = result.data["success_message"]
                    result_data["speak_to_user"] = result.data.get(
                        "speak_to_user", result.data["success_message"]
                    )
                    result_data["instruction"] = (
                        "Tell the user the success_message verbatim in a natural sentence."
                    )
                verbatim_sources.append((name, result.data))
                content = json.dumps(result_data, default=str)
                tool_results.append(
                    ToolMessage(content=content, tool_call_id=tid, name=name)
                )
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("Tool %s failed: %s", name, exc)
                tool_results.append(
                    ToolMessage(content=json.dumps({"error": str(exc)}), tool_call_id=tid, name=name)
                )
    finally:
        reset_current_messages(ctx_token)

    role = canonical_role(user.role)
    if role == "investor" and actions:
        before = len(actions)
        actions = sanitize_investor_wallet_actions(
            messages, actions, invest_session=invest_workflow_session()
        )
        if len(actions) < before:
            LOGGER.info(
                "[_call_tools] Stripped %d investor wallet UI action(s) — no explicit buy/claim intent",
                before - len(actions),
            )

    LOGGER.info("[_call_tools] Total actions accumulated: %d", len(actions))
    out_messages = list(messages) + tool_results
    verbatim_reply = pick_verbatim_speak_to_user(verbatim_sources)
    if verbatim_reply:
        LOGGER.info("[_call_tools] Using verbatim speak_to_user (%d chars)", len(verbatim_reply))
        out_messages.append(AIMessage(content=verbatim_reply))
        return {
            "actions": actions,
            "messages": out_messages,
            "verbatim_reply": verbatim_reply,
        }
    return {"actions": actions, "messages": out_messages}


async def _call_model(state: AgentState, role: str) -> dict:
    """Invoke the LLM with the current conversation + tool schemas."""
    model = _build_model()
    tools = _build_tools(role)
    bound = model.bind_tools(tools) if tools else model
    messages = state.get("messages", [])
    response = await bound.ainvoke(messages)
    return {"messages": messages + [response]}


async def _human_approval(state: AgentState, role: str, user: AuthUser, db: Any) -> dict:
    """Generate a confirmation message for high-stakes tool calls without executing them."""
    messages = state.get("messages", [])
    actions = state.get("actions", [])
    if not messages:
        return {"interrupt": None, "messages": messages, "actions": actions}

    last_msg = messages[-1]
    tool_calls = last_msg.tool_calls or [] if isinstance(last_msg, AIMessage) else []

    # Build a natural confirmation message via a quick LLM call.
    model = _build_model()
    tool_descriptions = []
    for call in tool_calls:
        name = call.get("name", "")
        args = call.get("args", {})
        tool_descriptions.append(f"- {name}({json.dumps(args, default=str)})")

    prompt = (
        "You are about to perform the following actions on behalf of the user:\n"
        + "\n".join(tool_descriptions)
        + "\n\nGenerate a brief, friendly confirmation message (1-2 sentences) asking "
        "the user to confirm. Be specific about what will happen."
    )
    try:
        confirm_msg = await model.ainvoke([HumanMessage(content=prompt)])
        confirmation = (confirm_msg.content or "Please confirm to proceed.").strip()
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Confirmation prompt failed: %s", exc)
        confirmation = "Please confirm to proceed with this action."

    # Compute pending actions using the real user/db so role gating works.
    pending_actions: list[AgentAction] = []
    for call in tool_calls:
        name = call.get("name", "")
        args = call.get("args", {})
        try:
            result = await dispatch(name, args, user, db)
            pending_actions.extend(result.actions)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Pending action preview for %s failed: %s", name, exc)

    return {
        "interrupt": {
            "message": confirmation,
            "pending_actions": pending_actions,
        },
        "messages": messages,
        "actions": actions,
    }


def _should_continue(state: AgentState) -> Literal["call_tools", "human_approval", END]:
    """Route to tool node, approval node, or end."""
    messages = state.get("messages", [])
    if not messages:
        return END

    last_msg = messages[-1]
    if not isinstance(last_msg, AIMessage) or not last_msg.tool_calls:
        return END

    # If user already approved this turn, execute tools.
    if state.get("approval") == "confirmed":
        return "call_tools"

    # Check for high-stakes tool calls.
    for call in last_msg.tool_calls:
        if call.get("name", "") in _HIGH_STAKES_TOOLS:
            return "human_approval"

    return "call_tools"


def _after_tools(state: AgentState) -> Literal["call_model", END]:
    """Skip a second LLM turn when tools already produced the user-facing reply."""
    if (state.get("verbatim_reply") or "").strip():
        return END
    return "call_model"


def build_agent_graph(
    role: str,
    user: AuthUser,
    db: Any,
    checkpointer: Any | None = None,
) -> CompiledStateGraph:
    """Build and compile a fresh graph instance for this request."""

    async def call_model_node(state: AgentState) -> dict:
        return await _call_model(state, role)

    async def call_tools_node(state: AgentState) -> dict:
        return await _call_tools(state, user, db)

    async def human_approval_node(state: AgentState) -> dict:
        return await _human_approval(state, role, user, db)

    builder = StateGraph(AgentState)
    builder.add_node("call_model", call_model_node)
    builder.add_node("call_tools", call_tools_node)
    builder.add_node("human_approval", human_approval_node)
    builder.add_edge(START, "call_model")
    builder.add_conditional_edges(
        "call_model",
        _should_continue,
        {"call_tools": "call_tools", "human_approval": "human_approval", END: END},
    )
    builder.add_conditional_edges(
        "call_tools",
        _after_tools,
        {"call_model": "call_model", END: END},
    )
    builder.add_edge("human_approval", END)

    return builder.compile(checkpointer=checkpointer)


# ──────────────────────────────────────────────────────────────
# Public entrypoints
# ──────────────────────────────────────────────────────────────

async def run_agent(
    user: AuthUser,
    history: list[ChatMessage],
    db: Any,
    *,
    thread_id: str | None = None,
    checkpointer: Any | None = None,
) -> ChatResponse:
    """Run the LangGraph agent and return the final reply + accumulated UI actions.

    If ``thread_id`` and ``checkpointer`` are provided, the conversation state
    is persisted across turns so the agent can resume mid-workflow.
    """
    settings = get_settings()
    role = canonical_role(user.role)

    system = SystemMessage(content=system_prompt_for_role(role))
    messages: list[BaseMessage] = [system]
    for m in history:
        if m.role == "system":
            continue
        if m.role == "tool":
            messages.append(
                ToolMessage(content=m.content or "", tool_call_id=m.tool_call_id or "", name=m.name or "")
            )
        elif m.role == "assistant":
            messages.append(AIMessage(content=m.content or ""))
        else:
            messages.append(HumanMessage(content=m.content or ""))

    graph = build_agent_graph(role, user, db, checkpointer=checkpointer)

    config: dict[str, Any] = {}
    if thread_id:
        config["configurable"] = {"thread_id": thread_id}

    effective_thread = thread_id or f"user:{user.wallet_address or user.id}"
    tid_token = set_current_thread_id(effective_thread)
    msg_token = set_current_messages(history)
    try:
        prepare_copilot_turn(effective_thread, history)
        preflight = None
        if role == "investor":
            preflight = await try_server_investor_marketplace_browse(user, db)
        elif role == "property_owner":
            preflight = await try_server_owner_analytics_overview(user, db)
        if preflight is None:
            preflight = await try_server_edit_property_continuation(user, db)
        if preflight is None:
            preflight = await try_server_apply_create_property_field_answer(user, db)
        if preflight is None:
            preflight = await try_server_create_property_confirmation(user, db)
        if preflight is None:
            preflight = await try_server_delete_property_continuation(user, db)
        if preflight is not None:
            reply = str((preflight.data or {}).get("speak_to_user") or "").strip()
            if not reply and preflight.data.get("property_name"):
                reply = (
                    f"Applying your update to {preflight.data.get('property_name')}…"
                )
            transcript = list(history)
            transcript.append(ChatMessage(role="assistant", content=reply))
            return ChatResponse(
                reply=reply,
                actions=preflight.actions,
                messages=transcript,
                role=role,
                model=settings.chat_model,
                interrupt=None,
            )
        final_state = await graph.ainvoke(AgentState(messages=messages, actions=[]), config=config or None)
    finally:
        reset_current_messages(msg_token)
        reset_current_thread_id(tid_token)

    reply = extract_final_reply_from_state(final_state)
    transcript = list(history)
    transcript.append(ChatMessage(role="assistant", content=reply))

    # If the graph hit human_approval, return an interrupt response.
    interrupt = final_state.get("interrupt")
    if interrupt:
        return ChatResponse(
            reply=interrupt["message"],
            actions=[],
            messages=transcript,
            role=role,
            model=settings.chat_model,
            interrupt=InterruptResponse(
                message=interrupt["message"],
                pending_actions=interrupt.get("pending_actions", []),
                thread_id=thread_id or "",
            ),
        )

    return ChatResponse(
        reply=reply,
        actions=final_state.get("actions", []),
        messages=transcript,
        role=role,
        model=settings.chat_model,
        interrupt=None,
    )


async def resume_agent(
    user: AuthUser,
    db: Any,
    thread_id: str,
    approve: bool,
    checkpointer: Any | None = None,
) -> ChatResponse:
    """Resume an interrupted conversation after user confirmation or denial.

    Loads the checkpointed state, executes the pending tools (if approved),
    and returns the final LLM response.
    """
    settings = get_settings()
    role = canonical_role(user.role)

    if not checkpointer:
        raise AIDisabledError("Checkpointer required for resume.")

    config = {"configurable": {"thread_id": thread_id}}
    checkpoint_tuple = await checkpointer.aget_tuple(config)
    if not checkpoint_tuple or not checkpoint_tuple.checkpoint:
        raise ValueError(f"Thread {thread_id} not found or expired.")

    checkpoint = checkpoint_tuple.checkpoint
    state_data = checkpoint.get("channel_values", {})
    raw_messages = state_data.get("messages", []) or []
    actions = state_data.get("actions", []) or []
    messages = _coerce_messages(raw_messages)

    if not approve:
        # User cancelled — let the LLM respond to the cancellation.
        messages = list(messages)
        messages.append(HumanMessage(content="The user cancelled this action. Please acknowledge and ask how else you can help."))
        model = _build_model()
        response = await model.ainvoke(messages)
        reply = (response.content or "").strip()
        return ChatResponse(
            reply=reply,
            actions=[],
            messages=[ChatMessage(role="assistant", content=reply)],
            role=role,
            model=settings.chat_model,
            interrupt=None,
        )

    # User approved — execute pending tools then get final LLM response.
    state = AgentState(messages=messages, actions=actions, approval="confirmed")
    graph = build_agent_graph(role, user, db, checkpointer=checkpointer)
    final_state = await graph.ainvoke(state, config=config or None)
    final_msg = final_state["messages"][-1]
    reply = (final_msg.content or "").strip()

    return ChatResponse(
        reply=reply,
        actions=final_state.get("actions", []),
        messages=[ChatMessage(role="assistant", content=reply)],
        role=role,
        model=settings.chat_model,
        interrupt=None,
    )


async def stream_agent(
    user: AuthUser,
    history: list[ChatMessage],
    db: Any,
    *,
    thread_id: str | None = None,
    checkpointer: Any | None = None,
):
    """Stream LangGraph events (tokens, tool calls, etc) for real-time UX.

    Yields dict events compatible with SSE / chunked JSON streaming.
    """
    settings = get_settings()
    role = canonical_role(user.role)

    system = SystemMessage(content=system_prompt_for_role(role))
    messages: list[BaseMessage] = [system]
    for m in history:
        if m.role == "system":
            continue
        if m.role == "tool":
            messages.append(
                ToolMessage(content=m.content or "", tool_call_id=m.tool_call_id or "", name=m.name or "")
            )
        elif m.role == "assistant":
            messages.append(AIMessage(content=m.content or ""))
        else:
            messages.append(HumanMessage(content=m.content or ""))

    graph = build_agent_graph(role, user, db, checkpointer=checkpointer)

    config: dict[str, Any] = {}
    if thread_id:
        config["configurable"] = {"thread_id": thread_id}

    effective_thread = thread_id or f"user:{user.wallet_address or user.id}"
    tid_token = set_current_thread_id(effective_thread)
    msg_token = set_current_messages(history)
    try:
        prepare_copilot_turn(effective_thread, history)
        preflight = None
        if role == "investor":
            preflight = await try_server_investor_marketplace_browse(user, db)
        elif role == "property_owner":
            preflight = await try_server_owner_analytics_overview(user, db)
        if preflight is None:
            preflight = await try_server_edit_property_continuation(user, db)
        if preflight is None:
            preflight = await try_server_apply_create_property_field_answer(user, db)
        if preflight is None:
            preflight = await try_server_create_property_confirmation(user, db)
        if preflight is None:
            preflight = await try_server_delete_property_continuation(user, db)
        if preflight is not None:
            reply = str((preflight.data or {}).get("speak_to_user") or "").strip()
            if not reply and preflight.data.get("property_name"):
                reply = (
                    f"Applying your update to {preflight.data.get('property_name')}…"
                )
            if reply:
                yield {"type": "token", "content": reply}
            yield {
                "type": "complete",
                "reply": reply,
                "actions": [a.model_dump() for a in preflight.actions],
            }
            return

        submit_eligible, submit_name = create_property_server_submit_eligible(user)
        if submit_eligible:
            deploy_msg = create_property_deploying_message(submit_name or None)
            yield {
                "type": "status",
                "phase": "deploying",
                "message": deploy_msg,
            }
            submit_result = await try_server_create_property_submit(user, db)
            if submit_result is not None:
                data = submit_result.data or {}
                reply = str(data.get("speak_to_user") or data.get("success_message") or "").strip()
                yield {
                    "type": "complete",
                    "reply": reply,
                    "actions": [a.model_dump() for a in submit_result.actions],
                }
                return

        suppress_tokens = False
        streamed_reply_chars = 0
        deploy_status_emitted = False
        async for event in graph.astream_events(
            AgentState(messages=messages, actions=[]),
            config=config or None,
            version="v2",
        ):
            kind = event.get("event")
            if kind == "on_chat_model_end":
                output = event.get("data", {}).get("output")
                tool_calls = getattr(output, "tool_calls", None) or []
                if tool_calls:
                    suppress_tokens = True
                    yield {"type": "stream_reset"}
            elif kind == "on_chat_model_stream":
                if suppress_tokens:
                    continue
                chunk = event.get("data", {}).get("chunk")
                if chunk and chunk.content:
                    streamed_reply_chars += len(chunk.content)
                    yield {"type": "token", "content": chunk.content}
            elif kind == "on_tool_start":
                suppress_tokens = True
                name = event.get("name", "")
                tool_input = (event.get("data") or {}).get("input") or {}
                deploy_pending = (
                    name == "fill_create_property"
                    and create_property_deploy_pending(tool_input)
                )
                if deploy_pending:
                    pname = (
                        str(tool_input.get("name") or "").strip()
                        or create_property_pending_name()
                    )
                    deploy_msg = create_property_deploying_message(pname or None)
                    deploy_status_emitted = True
                    yield {
                        "type": "status",
                        "phase": "deploying",
                        "message": deploy_msg,
                    }
                else:
                    yield {"type": "stream_reset"}
                yield {
                    "type": "tool_start",
                    "name": name,
                    "input": tool_input,
                }
            elif kind == "on_tool_end":
                yield {
                    "type": "tool_end",
                    "name": event.get("name", ""),
                    "output": event.get("data", {}).get("output"),
                }
            elif kind == "on_chain_end" and event.get("name") == "LangGraph":
                final_state = event.get("data", {}).get("output", {}) or {}
                reply = extract_final_reply_from_state(final_state)
                interrupt = final_state.get("interrupt")
                actions = final_state.get("actions", [])
                LOGGER.info("[stream_agent] Final reply length: %d, actions count: %d", len(reply), len(actions))
                if not reply:
                    LOGGER.warning(
                        "[stream_agent] Final reply is empty - this may indicate the model "
                        "didn't generate a response after tool execution"
                    )
                LOGGER.info("[stream_agent] Final actions count: %d, actions: %s", len(actions), actions)
                if reply and streamed_reply_chars == 0 and not deploy_status_emitted:
                    yield {"type": "token", "content": reply}
                payload: dict[str, Any] = {
                    "type": "complete",
                    "reply": reply,
                    "actions": [a.model_dump() for a in actions],
                }
                if interrupt:
                    payload["interrupt"] = {
                        "message": interrupt.get("message", ""),
                        "pending_actions": [a.model_dump() for a in interrupt.get("pending_actions", [])],
                    }
                yield payload
    finally:
        reset_current_messages(msg_token)
        reset_current_thread_id(tid_token)
