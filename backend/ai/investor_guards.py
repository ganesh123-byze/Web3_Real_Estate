"""Investor copilot guards — keep chat advisory unless the user clearly requests a wallet action.

The LLM sometimes calls ``start_invest`` / ``start_claim_rewards`` during browse or Q&A
turns (e.g. "show marketplace", "what's my portfolio"). These helpers gate wallet UI
actions server-side so the frontend never opens invest/claim dialogs or MetaMask paths
by mistake.
"""
from __future__ import annotations

import re
from typing import Any

from backend.ai.chat_stat_format import (
    format_chat_stat_eth_amount,
    format_chat_stat_percentage_label,
)
from backend.ai.schemas import AgentAction

_INVESTOR_WALLET_MODALS = frozenset({"INVEST_PROPERTY", "CLAIM_REWARDS"})

INVEST_TARGET_SUMMARY_HEADING = "Investment summary"
PORTFOLIO_YIELD_SUMMARY_HEADING = "Yield & returns summary"
INVESTOR_PORTFOLIO_HEADING = "Your portfolio details"

# Informational / browse phrasing — never open wallet UI when this matches alone.
_INFO_OR_BROWSE = re.compile(
    r"\b("
    r"how\s+(?:much|many|do|does|can|should|would|to)|"
    r"what(?:'s|\s+is|\s+are|\s+should|\s+can|\s+would)?|"
    r"which|where|when|why|who|"
    r"show\s+me|tell\s+me|list|summarize|summary|overview|"
    r"compare|best|worst|top|recommend|suggest|"
    r"explain|describe|help\s+me\s+understand|"
    r"marketplace|browse|available|opportunities|"
    r"portfolio|holdings|my\s+tokens|my\s+shares|"
    r"claimable|unclaimed|how\s+much\s+can\s+i\s+claim|"
    r"earned|yield|history|transactions?|activity|stats?"
    r")\b",
    re.IGNORECASE,
)

_INVEST_TOKEN_AMOUNT_WORDS: dict[str, int] = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "single": 1,
}

# Imperative buy / invest — user wants the invest dialog, not just research.
_INVEST_TRANSACTIONAL = re.compile(
    r"\b("
    r"(?:please\s+)?(?:buy|purchase)\s+(?:\d+|one|two|three|four|five|a|an|single)\s+tokens?|"
    r"(?:please\s+)?invest\s+(?:\d+|one|two|three|four|five|a|an|single)\s+tokens?\s+(?:in|into|of)\b|"
    r"(?:please\s+)?invest\s+(?:\d+\s+)?(?:tokens?\s+)?(?:in|into|of)\b|"
    r"(?:please\s+)?invest\s+\d+\b|"
    r"open\s+(?:the\s+)?invest(?:ment)?\s+dialog|"
    r"i\s+want\s+to\s+(?:buy|invest)|"
    r"i(?:'d|\s+would)\s+like\s+to\s+(?:buy|invest)|"
    r"let(?:'s|\s+us)\s+invest|"
    r"start\s+investing\s+in|"
    r"put\s+money\s+into|"
    r"buy\s+into\b"
    r")\b",
    re.IGNORECASE,
)

# Imperative claim — user wants to withdraw yield, not just see amounts.
_CLAIM_TRANSACTIONAL = re.compile(
    r"\b("
    r"(?:please\s+)?claim\s+(?:my\s+)?(?:rewards|yield|rental\s+yield|earnings)|"
    r"(?:please\s+)?withdraw\s+(?:my\s+)?(?:rewards|yield)|"
    r"claim\s+(?:from|on|for)\b|"
    r"i\s+want\s+to\s+claim|"
    r"let(?:'s|\s+us)\s+claim"
    r")\b",
    re.IGNORECASE,
)

# Bare invest openers — not a property name (mirror tenant pay-rent generic phrases).
_GENERIC_INVEST_PHRASE = re.compile(
    r"(?i)^(?:"
    r"invest(?:ment|ing)?|"
    r"i\s+want\s+to\s+invest(?:\s+in(?:\s+a)?\s+property)?|"
    r"help\s+me\s+invest(?:\s+in(?:\s+a)?\s+property)?|"
    r"let(?:'s|\s+us)\s+invest|"
    r"start\s+(?:an?\s+)?invest(?:ment|ing)?|"
    r"make\s+(?:an?\s+)?investment|"
    r"i(?:'d|\s+would)\s+like\s+to\s+invest|"
    r"ready\s+to\s+invest|"
    r"i\s+want\s+to\s+buy(?:\s+tokens?)?|"
    r"i(?:'d|\s+would)\s+like\s+to\s+buy(?:\s+tokens?)?|"
    r"open\s+(?:the\s+)?invest(?:ment)?\s+dialog"
    r")$"
)

# User wants to start a guided invest flow (property name first, then amount).
_BEGIN_INVEST_WORKFLOW = re.compile(
    r"\b("
    r"i\s+want\s+to\s+invest|"
    r"help\s+me\s+invest|"
    r"let(?:'s|\s+us)\s+invest\b|"
    r"start\s+(?:an?\s+)?invest(?:ment|ing)?|"
    r"make\s+(?:an?\s+)?investment|"
    r"i(?:'d|\s+would)\s+like\s+to\s+invest\b|"
    r"ready\s+to\s+invest"
    r")\b",
    re.IGNORECASE,
)

# Soft "invest" mentions that are research, not orders.
_INVEST_RESEARCH = re.compile(
    r"\b("
    r"how\s+to\s+invest|"
    r"should\s+i\s+invest|"
    r"worth\s+investing|"
    r"properties?\s+to\s+invest\s+in|"
    r"investment\s+opportunities|"
    r"thinking\s+about\s+investing|"
    r"learn\s+about\s+investing"
    r")\b",
    re.IGNORECASE,
)


def _normalize_text(text: str) -> str:
    from backend.ai.investor_voice_parsers import normalize_invest_voice_utterance

    return normalize_invest_voice_utterance(text)


def _human_message_role(msg: Any) -> str:
    """Normalize role from API ChatMessage, LangGraph messages, or dict history."""
    if isinstance(msg, dict):
        return (msg.get("type") or msg.get("role") or "").lower()
    role = getattr(msg, "role", None)
    if role is not None:
        return str(role).lower()
    msg_type = getattr(msg, "type", None)
    if msg_type is not None:
        return str(msg_type).lower()
    cls = type(msg).__name__.lower()
    if "human" in cls:
        return "human"
    if "user" in cls:
        return "user"
    return ""


def extract_last_human_utterance(messages: list[Any] | None) -> str:
    """Return the latest human/user line from LangGraph or API history."""
    if not messages:
        return ""
    last_human_idx: int | None = None
    for i, msg in enumerate(messages):
        if _human_message_role(msg) in ("human", "user"):
            last_human_idx = i
    if last_human_idx is None:
        return ""
    msg = messages[last_human_idx]
    content = getattr(msg, "content", None)
    if content is None and isinstance(msg, dict):
        content = msg.get("content")
    return _normalize_text(content if isinstance(content, str) else "")


def is_generic_invest_phrase(text: str) -> bool:
    """Utterances that start invest but do not name a property."""
    utterance = re.sub(r"[.!?]+$", "", _normalize_text(text)).strip()
    if not utterance:
        return False
    if _GENERIC_INVEST_PHRASE.match(utterance):
        return True
    if utterance.lower() == "invest":
        return True
    return bool(_BEGIN_INVEST_WORKFLOW.search(utterance))


def wants_to_begin_invest_workflow(text: str) -> bool:
    """True when the user asks to invest but has not necessarily named a property yet."""
    t = _normalize_text(text)
    if not t or _INVEST_RESEARCH.search(t):
        return False
    if is_generic_invest_phrase(t):
        return True
    if t.lower() == "invest":
        return True
    if _BEGIN_INVEST_WORKFLOW.search(t):
        return True
    return False


def invest_utterance_names_property(
    text: str,
    *,
    quick_action_id: str | None = None,
) -> bool:
    """True when the user named a concrete property (id or title), not only 'invest'."""
    utterance = _normalize_text(text)
    if not utterance:
        return False

    from backend.ai.investor_quick_actions import (
        is_investor_advisory_intent,
        investor_quick_action_interrupts_workflow,
    )

    if investor_quick_action_interrupts_workflow(quick_action_id):
        return False
    if is_investor_advisory_intent(utterance):
        return False
    if is_generic_invest_phrase(utterance):
        return False

    if re.search(r"(?i)(?:property\s*)?#(\d+)\b", utterance):
        return True

    for pattern in _INVEST_ORDER_PATTERNS:
        match = pattern.search(utterance)
        if match and _clean_invest_property_name(match.groupdict().get("property") or ""):
            return True

    if invest_utterance_has_decimal_token_amount(utterance):
        prop = _extract_invest_property_from_decimal_order(utterance)
        if prop:
            return True

    hint = extract_invest_property_hint_from_utterance(utterance)
    return bool(hint and not is_generic_invest_phrase(hint))


def has_explicit_invest_intent(text: str) -> bool:
    """True when the user is ordering a buy/invest, not researching."""
    t = _normalize_text(text)
    if not t:
        return False
    from backend.ai.investor_wallet_affordability import has_investor_wallet_affordability_intent

    if has_investor_wallet_affordability_intent(t):
        return False
    if has_investor_portfolio_intent(t):
        return False
    if _INVEST_RESEARCH.search(t):
        return False
    parsed = parse_invest_order_from_utterance(t)
    if parsed.get("property_name") and parsed.get("token_amount"):
        return True
    if parsed.get("property_name") and re.search(
        r"(?i)\b(?:buy|invest|purchase|tokens?)\b", t
    ):
        return True
    if _INVEST_TRANSACTIONAL.search(t):
        if _INFO_OR_BROWSE.search(t) and not re.search(
            r"(?i)\b(?:buy|purchase)\s+(?:\d+|one|two|a|an)\s+tokens?|"
            r"invest\s+(?:\d+|one|two|a|an)\s+tokens?",
            t,
        ):
            return False
        return True
    return wants_to_begin_invest_workflow(t)


def invest_workflow_active(session: dict | None) -> bool:
    """True while a guided invest form is collecting fields (not after a completed order)."""
    if not session:
        return False
    if session.get("submitted"):
        return False
    return bool(
        session.get("in_progress") or session.get("awaiting_invest_confirmation")
    )


def investor_invest_wallet_permitted(
    user_text: str,
    invest_session: dict | None = None,
) -> bool:
    """Whether invest modal / MetaMask submit actions may be emitted this turn."""
    if invest_session and invest_session.get("completing_submit"):
        return True
    if invest_session and invest_session.get("awaiting_invest_confirmation"):
        return False
    if invest_workflow_active(invest_session):
        return True
    return has_explicit_invest_intent(user_text)


def has_explicit_claim_intent(text: str) -> bool:
    """True when the user wants to execute a claim, not just see claimable totals."""
    t = _normalize_text(text)
    if not t:
        return False
    if _CLAIM_TRANSACTIONAL.search(t):
        return True
    return False


_PORTFOLIO_INTENT = re.compile(
    r"\b("
    r"(?:my\s+)?(?:investment\s+)?portfolio\b|"
    r"(?:my\s+)?holdings?\b|"
    r"my\s+tokens?\b|"
    r"my\s+shares?\b|"
    r"what\s+do\s+i\s+own\b|"
    r"show\s+(?:me\s+)?(?:my\s+)?investments?\b|"
    r"portfolio\s+summary\b|"
    r"summarize\s+my\s+portfolio\b|"
    r"current\s+valuations?\b"
    r")\b",
    re.IGNORECASE,
)


def has_investor_portfolio_intent(text: str) -> bool:
    """True when the user wants a fresh portfolio/holdings snapshot (read-only)."""
    utterance = _normalize_text(text)
    if not utterance:
        return False
    if not _PORTFOLIO_INTENT.search(utterance):
        return False
    if _INVEST_TRANSACTIONAL.search(utterance) and not re.search(
        r"(?i)\b(?:portfolio|holdings?|my\s+tokens?|my\s+shares?|investment\s+portfolio|valuations?)\b",
        utterance,
    ):
        return False
    return True


def _format_portfolio_ownership_pct(pct: Any) -> str:
    """Human-readable ownership % for portfolio holdings."""
    if pct is None:
        return "—"
    try:
        value = float(pct)
    except (TypeError, ValueError):
        return "—"
    if value <= 0:
        return "0%" if value == 0 else "—"
    return format_chat_stat_percentage_label(value)


def format_investor_portfolio_speak(
    portfolio_data: dict[str, Any],
    yield_data: dict[str, Any] | None = None,
) -> str:
    """Live portfolio snapshot for chat — Your portfolio details card."""
    holdings = list(portfolio_data.get("holdings") or [])
    count = int(portfolio_data.get("count") or len(holdings))

    lines = [
        INVESTOR_PORTFOLIO_HEADING,
        f"Properties invested: {count}",
    ]

    total_tokens = 0
    for holding in holdings:
        total_tokens += int(holding.get("token_amount") or 0)

    if count == 0:
        lines.append("Total tokens held: 0")
        lines.append("Holdings: You have no token holdings recorded yet.")
        lines.append(
            "Tip: After you invest, ask for your portfolio again — balances refresh "
            "from your wallet on-chain."
        )
    else:
        lines.append(f"Total tokens held: {total_tokens}")
        for holding in holdings:
            name = str(holding.get("property_name") or f"Property {holding.get('property_id')}")
            pid = holding.get("property_id")
            tokens = int(holding.get("token_amount") or 0)
            pct = holding.get("ownership_percentage")
            lines.append(f"Property: {name} (#{pid})")
            lines.append(f"Tokens held: {tokens}")
            lines.append(f"Ownership: {_format_portfolio_ownership_pct(pct)}")

    if yield_data and count > 0:
        earned = str(yield_data.get("total_earned_eth") or "0").strip()
        claimable = str(yield_data.get("total_claimable_eth") or "0").strip()
        lines.append(f"Total rental yield earned: {earned} ETH")
        lines.append(f"Claimable rewards: {claimable} ETH")

    return "\n".join(lines)


def has_marketplace_browse_intent(text: str) -> bool:
    """True when the user wants to browse/list marketplace listings (not buy yet)."""
    t = _normalize_text(text).lower()
    if not t:
        return False
    if has_explicit_invest_intent(text):
        return False
    if re.search(
        r"\b(?:take\s+me\s+to|go\s+to|open)\s+(?:the\s+)?marketplace\b",
        t,
    ):
        return True
    if re.search(r"\bbrowse\s+(?:the\s+)?marketplace\b", t):
        return True
    if re.search(r"\bmarketplace\b", t) and re.search(
        r"\b(?:show|available|properties|opportunities|invest)\b", t
    ):
        return True
    if re.search(r"\b(?:show|list|what).*\b(?:available|for\s+sale|opportunities)\b", t):
        return True
    if re.search(r"\bproperties?\s+(?:to\s+)?invest\s+in\b", t):
        return True
    if re.search(r"\bbrowse\b", t) and re.search(r"\bpropert", t):
        return True
    return False


def wallet_ui_allowed(modal: str, user_text: str, *, invest_session: dict | None = None) -> bool:
    if modal == "INVEST_PROPERTY":
        return investor_invest_wallet_permitted(user_text, invest_session)
    if modal == "CLAIM_REWARDS":
        return has_explicit_claim_intent(user_text)
    return True


def sanitize_investor_wallet_actions(
    messages: list[Any] | None,
    actions: list[AgentAction],
    *,
    invest_session: dict | None = None,
) -> list[AgentAction]:
    """Drop invest/claim modal actions unless permitted for this turn."""
    if not actions:
        return actions
    user_text = extract_last_human_utterance(messages)
    invest_ok = investor_invest_wallet_permitted(user_text, invest_session)
    claim_ok = has_explicit_claim_intent(user_text)
    completing = bool((invest_session or {}).get("completing_submit"))

    filtered: list[AgentAction] = []
    for action in actions:
        modal = action.modal or ""
        if modal in _INVESTOR_WALLET_MODALS:
            if modal == "INVEST_PROPERTY" and not invest_ok:
                continue
            if modal == "CLAIM_REWARDS" and not claim_ok:
                continue
        if (
            action.type == "SUBMIT_FORM"
            and modal == "INVEST_PROPERTY"
            and not (invest_ok and completing)
        ):
            continue
        if action.type == "SUBMIT_FORM" and modal == "CLAIM_REWARDS" and not claim_ok:
            continue
        filtered.append(action)
    return filtered


def invest_tool_blocked_message() -> str:
    return (
        "Blocked: the user's latest message is informational or browse-only, not an "
        "explicit buy/invest order. Do NOT open the invest dialog or mention MetaMask. "
        "Use list_properties, get_property_details, or navigate to /investor/marketplace. "
        "Tell them they can tap Invest on a property card when they are ready."
    )


def claim_tool_blocked_message() -> str:
    return (
        "Blocked: the user asked about claimable amounts or history, not to execute a "
        "claim. Do NOT open the claim dialog or mention MetaMask. Use "
        "get_my_claimable_rewards or get_my_claim_history. If they want to claim later, "
        "they can use Claim via MetaMask on the dashboard."
    )


def _format_token_count(raw: Any) -> str:
    try:
        value = float(str(raw or "0"))
    except (TypeError, ValueError):
        return "0"
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


_INVEST_WHOLE_AMOUNT = (
    r"(?P<amount>(?<!\d)\d+(?!\.\d)|one|two|three|four|five|six|seven|eight|nine|ten|a|an|single)"
)

_INVEST_ORDER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?i)(?:please\s+)?(?:buy|invest|purchase)\s+"
        + _INVEST_WHOLE_AMOUNT
        + r"\s*(?:tokens?)?\s*(?:in|into|of)\s+"
        r"(?P<property>.+?)(?:\s+property)?\s*\.?$"
    ),
    re.compile(
        r"(?i)(?:buy|invest|purchase)\s+(?:in|into|of)\s+(?P<property>.+?)\s+"
        r"(?:for\s+)?"
        + _INVEST_WHOLE_AMOUNT
        + r"\s*tokens?"
    ),
    re.compile(
        r"(?i)^"
        + _INVEST_WHOLE_AMOUNT
        + r"\s*tokens?\s*(?:in|into|of)\s+(?P<property>.+?)(?:\s+property)?\s*\.?$"
    ),
    re.compile(
        r"(?i)(?:buy|invest|purchase)\s+(?:in|into|of)\s+(?P<property>.+?)(?:\s+property)?\s*\.?$"
    ),
)


_INVEST_DECIMAL_NUMBER_RE = re.compile(r"(?<!\d)\d*\.\d+")


def invest_utterance_has_decimal_token_amount(text: str) -> bool:
    """True when the user supplied a fractional token count (on-chain purchases are whole tokens)."""
    from backend.ai.investor_voice_parsers import (
        invest_spoken_decimal_in_token_context,
        invest_spoken_decimal_token_amount,
    )

    utterance = _normalize_text(text)
    if not utterance:
        return False
    if invest_spoken_decimal_in_token_context(utterance):
        return True
    if not _INVEST_DECIMAL_NUMBER_RE.search(utterance):
        return False
    if re.search(r"(?i)\btokens?\b", utterance):
        return True
    if re.search(r"(?i)\b(?:buy|invest|purchase)\b", utterance):
        return True
    if re.fullmatch(r"(?i)\d*\.\d+", utterance):
        return True
    return False


def invest_token_amount_value_is_decimal(value: str) -> bool:
    from backend.ai.investor_voice_parsers import invest_spoken_decimal_token_amount

    text = str(value or "").strip()
    if not text:
        return False
    if invest_spoken_decimal_token_amount(text):
        return True
    return bool(_INVEST_DECIMAL_NUMBER_RE.search(text))


def invest_token_amount_value_is_negative(value: str) -> bool:
    from backend.ai.investor_voice_parsers import invest_spoken_negative_token_amount

    text = str(value or "").strip()
    if not text:
        return False
    if invest_spoken_negative_token_amount(text):
        return True
    if re.fullmatch(r"-\d+", text):
        return True
    if re.search(r"(?i)\b(?:minus|negative)\b", text) and re.search(r"\d", text):
        return True
    return False


def invest_utterance_has_negative_token_amount(text: str) -> bool:
    """True when the user supplied a negative token count."""
    from backend.ai.investor_voice_parsers import invest_spoken_negative_token_amount

    utterance = _normalize_text(text)
    if not utterance:
        return False
    if invest_spoken_negative_token_amount(utterance):
        return True
    if invest_token_amount_value_is_negative(utterance):
        return True
    if re.search(r"(?i)-\d+\s*tokens?\b", utterance):
        return True
    if re.search(
        r"(?i)\b(?:minus|negative)\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*tokens?\b",
        utterance,
    ):
        return True
    return False


def invest_token_amount_field_is_valid(value: str) -> bool:
    """True for positive whole-number token counts only."""
    text = str(value or "").strip()
    if not text or invest_token_amount_value_is_decimal(text):
        return False
    if invest_token_amount_value_is_negative(text):
        return False
    try:
        return int(text) >= 1
    except (TypeError, ValueError):
        return False


def invest_invalid_token_amount_message(
    rejected_value: str = "",
    *,
    reason: str = "decimal",
) -> str:
    shown = f'"{_normalize_text(rejected_value)}"' if _normalize_text(rejected_value) else "That amount"
    if reason == "negative":
        return (
            f"{shown} isn't valid. Negative token amounts aren't allowed — "
            "please enter a whole number of 1 or greater."
        )
    if reason == "zero":
        return (
            f"{shown} isn't valid. Please enter a whole number of tokens — "
            "1 or greater."
        )
    return (
        f"{shown} isn't valid. Tokens can only be bought in whole numbers, not decimals — "
        "please enter 1 or greater."
    )


def invest_classify_invalid_token_amount_turn(
    text: str,
    *,
    next_field: str | None = None,
    args_token: str | None = None,
) -> str | None:
    """Return 'decimal', 'negative', 'zero', or None when the token answer is acceptable."""
    if args_token not in (None, ""):
        raw = str(args_token).strip()
        if invest_token_amount_value_is_negative(raw):
            return "negative"
        if invest_token_amount_value_is_decimal(raw):
            return "decimal"
        if raw.isdigit() and int(raw) < 1:
            return "zero"

    utterance = _normalize_text(text)
    if not utterance:
        return None

    if invest_utterance_has_negative_token_amount(utterance):
        if next_field == "token_amount":
            return "negative"
        if re.search(r"(?i)\btokens?\b", utterance):
            return "negative"
        if re.search(r"(?i)\b(?:buy|invest|purchase)\b", utterance):
            return "negative"
        if invest_token_amount_value_is_negative(utterance):
            return "negative"

    if invest_utterance_has_decimal_token_amount(utterance):
        if next_field == "token_amount":
            return "decimal"
        if re.search(r"(?i)\btokens?\b", utterance):
            return "decimal"
        if re.search(r"(?i)\b(?:buy|invest|purchase)\b", utterance):
            return "decimal"
        if re.fullmatch(r"(?i)\d*\.\d+", utterance):
            return "decimal"

    if next_field == "token_amount":
        from backend.ai.investor_voice_parsers import invest_spoken_decimal_token_amount

        if invest_spoken_decimal_token_amount(utterance):
            return "decimal"
        if re.fullmatch(r"0+", utterance):
            return "zero"
        if utterance.isdigit() and int(utterance) < 1:
            return "zero"

    return None


def invest_turn_attempts_decimal_token_amount(
    text: str,
    *,
    next_field: str | None = None,
    args_token: str | None = None,
) -> bool:
    """True when this turn should be rejected as a fractional token purchase."""
    return (
        invest_classify_invalid_token_amount_turn(
            text, next_field=next_field, args_token=args_token
        )
        == "decimal"
    )


def invest_turn_attempts_invalid_token_amount(
    text: str,
    *,
    next_field: str | None = None,
    args_token: str | None = None,
) -> bool:
    """True when this turn should be rejected as an invalid token purchase."""
    return invest_classify_invalid_token_amount_turn(
        text, next_field=next_field, args_token=args_token
    ) is not None


def parse_invest_token_amount(text: str) -> str | None:
    """Parse a whole token count from voice/chat (digits or spoken words)."""
    utterance = _normalize_text(text)
    if not utterance:
        return None
    if invest_utterance_has_negative_token_amount(utterance):
        return None
    if invest_utterance_has_decimal_token_amount(utterance):
        return None
    digit = re.search(r"(?i)(?<!\d\.)(?<!\d)\b(\d+)\b(?!\.\d)\s*tokens?\b", utterance)
    if digit:
        value = int(digit.group(1))
        return str(value) if value > 0 else None
    word = re.search(
        r"(?i)\b(one|two|three|four|five|six|seven|eight|nine|ten|a|an|single)\s+tokens?\b",
        utterance,
    )
    if word:
        amount = _INVEST_TOKEN_AMOUNT_WORDS.get(word.group(1).lower())
        if amount and amount > 0:
            return str(amount)
    lone = re.fullmatch(r"(?i)(\d+)\s*tokens?", utterance)
    if lone:
        value = int(lone.group(1))
        return str(value) if value > 0 else None
    lone_word = re.fullmatch(
        r"(?i)(one|two|three|four|five|six|seven|eight|nine|ten|a|an|single)\s+tokens?",
        utterance,
    )
    if lone_word:
        amount = _INVEST_TOKEN_AMOUNT_WORDS.get(lone_word.group(1).lower())
        if amount and amount > 0:
            return str(amount)
    return None


def _normalize_invest_amount_token(raw: str | None) -> str | None:
    if raw is None:
        return None
    token = str(raw).strip().lower()
    if token.isdigit():
        value = int(token)
        return str(value) if value > 0 else None
    amount = _INVEST_TOKEN_AMOUNT_WORDS.get(token)
    return str(amount) if amount and amount > 0 else None


def invest_utterance_is_token_count_only(text: str) -> bool:
    """True when the user is answering with a token count (e.g. '1' or '5 tokens'), not a property id."""
    utterance = _normalize_text(text)
    if not utterance:
        return False
    if invest_utterance_has_decimal_token_amount(utterance):
        return True
    if invest_utterance_has_negative_token_amount(utterance):
        return True
    if parse_invest_token_amount(utterance):
        return True
    if re.fullmatch(r"\d+", utterance):
        return True
    return bool(
        re.fullmatch(
            r"(?i)(one|two|three|four|five|six|seven|eight|nine|ten|a|an|single)",
            utterance,
        )
    )


def extract_invest_property_hint_from_utterance(text: str) -> str:
    """Best-effort property name when the user did not use a strict invest pattern."""
    utterance = _normalize_text(text)
    if not utterance:
        return ""

    from backend.ai.investor_quick_actions import is_investor_advisory_intent

    if is_generic_invest_phrase(utterance):
        return ""

    if is_investor_advisory_intent(utterance):
        return ""

    if has_investor_portfolio_intent(utterance):
        return ""

    if invest_utterance_is_token_count_only(utterance):
        return ""

    if invest_utterance_has_negative_token_amount(utterance):
        return ""

    if invest_token_amount_value_is_negative(utterance):
        return ""

    if parse_invest_token_amount(utterance) and not re.search(
        r"(?i)\b(?:in|into|of)\b", utterance
    ):
        return ""

    id_match = re.search(r"(?i)(?:property\s*)?#(\d+)\b", utterance)
    if id_match:
        return f"#{id_match.group(1)}"

    stripped = re.sub(
        r"(?i)^(?:please\s+)?(?:help\s+me\s+)?(?:i\s+want\s+to\s+)?(?:buy|invest|purchase)\s+",
        "",
        utterance,
    )
    stripped = re.sub(
        r"(?i)(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|a|an|single)\s*"
        r"tokens?\s*(?:in|into|of)\s+",
        "",
        stripped,
    )
    stripped = re.sub(
        r"(?i)\s+(?:for\s+)?(?:\d+|one|two|three|four|five|a|an|single)\s*tokens?\s*$",
        "",
        stripped,
    )
    stripped = re.sub(r"(?i)^(?:in|into|of)\s+", "", stripped).strip()
    result = _clean_invest_property_name(stripped)
    if not result or is_generic_invest_phrase(result):
        return ""
    return result


def _clean_invest_property_name(raw: str) -> str:
    text = _normalize_text(raw)
    text = re.sub(r"(?i)^(?:the\s+)?(?:property\s+)?", "", text).strip()
    text = re.sub(r"(?i)\s+property\s*$", "", text).strip()
    return text


def invest_turn_explicit_token_amount(
    text: str,
    *,
    args_token: str | None = None,
) -> str | None:
    """Token count explicitly provided this turn (utterance or tool args)."""
    if args_token not in (None, ""):
        value = str(args_token).strip()
        return value if value else None
    return parse_invest_order_from_utterance(text).get("token_amount")


def invest_turn_specifies_property(
    text: str,
    *,
    args_property: str | None = None,
) -> bool:
    """True when this turn names a property (id, #id, or name) via speech or tool args."""
    if args_property not in (None, ""):
        return True
    parsed = parse_invest_order_from_utterance(text)
    if parsed.get("property_name"):
        return True
    return bool(extract_invest_property_hint_from_utterance(text))


def should_clear_stale_invest_token_amount(
    text: str,
    *,
    args_property: str | None = None,
    args_token: str | None = None,
) -> bool:
    """Drop a prior token_amount when the user names a property/id without a new count."""
    if invest_utterance_is_token_count_only(text):
        return False
    if invest_turn_explicit_token_amount(text, args_token=args_token):
        return False
    return invest_turn_specifies_property(text, args_property=args_property)


def _extract_invest_property_from_decimal_order(utterance: str) -> str:
    """Property name from orders like 'invest 0.1 token in Gold Plaza' (amount invalid)."""
    patterns = (
        r"(?i)(?:buy|invest|purchase)\s+\d*\.\d+\s*tokens?\s*(?:in|into|of)\s+"
        r"(?P<property>.+?)(?:\s+property)?\s*\.?$",
        r"(?i)(?:buy|invest|purchase)\s+(?:in|into|of)\s+(?P<property>.+?)\s+"
        r"(?:for\s+)?\d*\.\d+\s*tokens?",
        r"(?i)^\d*\.\d+\s*tokens?\s*(?:in|into|of)\s+"
        r"(?P<property>.+?)(?:\s+property)?\s*\.?$",
    )
    for pattern in patterns:
        match = re.search(pattern, utterance)
        if not match:
            continue
        prop = _clean_invest_property_name(match.group("property") or "")
        if prop and not is_generic_invest_phrase(prop):
            return prop
    return ""


def parse_invest_order_from_utterance(text: str) -> dict[str, str]:
    """Extract property_name and/or token_amount from a buy/invest voice or chat line."""
    utterance = _normalize_text(text)
    if not utterance:
        return {}
    if invest_utterance_has_decimal_token_amount(utterance):
        prop = _extract_invest_property_from_decimal_order(utterance)
        return {"property_name": prop} if prop else {}

    if invest_utterance_has_negative_token_amount(utterance):
        return {}

    out: dict[str, str] = {}
    for pattern in _INVEST_ORDER_PATTERNS:
        match = pattern.search(utterance)
        if not match:
            continue
        groups = match.groupdict()
        amount = _normalize_invest_amount_token(groups.get("amount"))
        if amount:
            out["token_amount"] = amount
        prop = _clean_invest_property_name(groups.get("property") or "")
        if prop:
            out["property_name"] = prop
        if out:
            return out

    if invest_utterance_is_token_count_only(utterance):
        amount = parse_invest_token_amount(utterance)
        if not amount and utterance.isdigit():
            value = int(utterance)
            if value > 0:
                return {"token_amount": str(value)}
        if amount:
            return {"token_amount": amount}
        return {}

    amount = parse_invest_token_amount(utterance)
    if amount:
        out["token_amount"] = amount

    hint = extract_invest_property_hint_from_utterance(utterance)
    if hint and "property_name" not in out:
        out["property_name"] = hint

    if out:
        return out

    if hint:
        return {"property_name": hint}

    return {}


def _format_eth_amount(raw: Any) -> str:
    return format_chat_stat_eth_amount(raw)


def _derive_invest_property_summary_rows(prop: dict[str, Any]) -> list[str]:
    """Label: value rows for the investor Investment summary card in chat/voice."""
    name = str(prop.get("name") or f"Property {prop.get('id')}")
    pid = prop.get("id")
    location = str(prop.get("location") or "").strip()
    available = _format_token_count(prop.get("tokens_available"))
    token_price = _format_eth_amount(prop.get("token_sale_price_eth"))
    try:
        monthly_rent = float(prop.get("monthly_rent_eth") or 0)
    except (TypeError, ValueError):
        monthly_rent = 0.0

    return [
        f"Property name: {name} (#{pid})",
        f"Location: {location or '—'}",
        f"Tokens available: {available}",
        (
            f"Price per token: {token_price} ETH"
            if token_price and token_price not in ("0", "0.0")
            else "Price per token: —"
        ),
        (
            f"Monthly rent: {_format_eth_amount(monthly_rent)} ETH"
            if monthly_rent > 0
            else "Monthly rent: —"
        ),
    ]


def format_invest_confirmation_summary(
    prop: dict[str, Any],
    token_amount: int | str | None,
) -> str:
    """Full invest order summary with yes/no confirmation footer."""
    summary = format_invest_target_property_speak(prop, token_amount=token_amount)
    return (
        f"{summary}\n\n"
        "Reply Yes to proceed with this investment in MetaMask, or No to cancel."
    )


def format_invest_target_property_speak(
    prop: dict[str, Any],
    *,
    token_amount: int | str | None = None,
) -> str:
    """Single-property summary for an invest order — investment summary card format."""
    lines = [INVEST_TARGET_SUMMARY_HEADING, *_derive_invest_property_summary_rows(prop)]

    if token_amount is not None:
        try:
            amount_int = int(token_amount)
        except (TypeError, ValueError):
            amount_int = None
        price = _format_eth_amount(prop.get("token_sale_price_eth"))
        if amount_int and amount_int > 0:
            if price and price not in ("0", "0.0"):
                try:
                    total = float(price) * amount_int
                    lines.append(
                        f"Order size: {amount_int} token{'s' if amount_int != 1 else ''} "
                        f"(about {_format_eth_amount(total)} ETH plus gas)"
                    )
                except (TypeError, ValueError):
                    lines.append(
                        f"Order size: {amount_int} token{'s' if amount_int != 1 else ''}"
                    )
            else:
                lines.append(
                    f"Order size: {amount_int} token{'s' if amount_int != 1 else ''}"
                )

    return "\n".join(lines)


def format_investor_marketplace_catalog_speak(
    investable: list[dict[str, Any]],
    *,
    total_listed: int,
) -> str:
    """Verbatim marketplace summary for investor browse turns."""
    if not investable:
        if total_listed <= 0:
            return (
                "There are no properties on the marketplace yet. "
                "Check back after new listings are deployed."
            )
        return (
            f"There are {total_listed} listing(s) on the marketplace, but none have "
            "tokens available to buy right now. Ask again later or say which property "
            "you want details on."
        )

    lines = [
        "Here are the properties open for investment right now:",
        "",
    ]
    for index, prop in enumerate(investable, start=1):
        name = str(prop.get("name") or f"Property {prop.get('id')}")
        pid = prop.get("id")
        location = str(prop.get("location") or "").strip()
        symbol = str(prop.get("token_symbol") or "").strip()
        sold = format_chat_stat_percentage_label(prop.get("sold_percentage") or "0")
        available = _format_token_count(prop.get("tokens_available"))
        price = format_chat_stat_eth_amount(prop.get("token_sale_price_eth") or "")
        rent = prop.get("monthly_rent_eth")
        parts = [f"{index}. {name} (#{pid})"]
        detail_bits: list[str] = []
        if location:
            detail_bits.append(location)
        if symbol:
            detail_bits.append(symbol)
        detail_bits.append(f"{sold} sold")
        detail_bits.append(f"{available} tokens available")
        if price and price not in ("0", "0.0"):
            detail_bits.append(f"{price} ETH/token")
        if rent not in (None, "", "0", "0.0"):
            detail_bits.append(
                f"monthly rent {format_chat_stat_eth_amount(rent)} ETH"
            )
        lines.append(f"   {parts[0]} - {', '.join(detail_bits)}")
    lines.extend(
        [
            "",
            "I've opened the marketplace page. Say which property you'd like to invest in, "
            "or ask for more details on any listing above.",
        ]
    )
    return "\n".join(lines)
