"""Investor copilot guards — keep chat advisory unless the user clearly requests a wallet action.

The LLM sometimes calls ``start_invest`` / ``start_claim_rewards`` during browse or Q&A
turns (e.g. "show marketplace", "what's my portfolio"). These helpers gate wallet UI
actions server-side so the frontend never opens invest/claim dialogs or MetaMask paths
by mistake.
"""
from __future__ import annotations

import re
from typing import Any

from backend.ai.schemas import AgentAction

_INVESTOR_WALLET_MODALS = frozenset({"INVEST_PROPERTY", "CLAIM_REWARDS"})

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
    return " ".join((text or "").split())


def extract_last_human_utterance(messages: list[Any] | None) -> str:
    """Return the latest human/user line from LangGraph or API history."""
    if not messages:
        return ""
    last_human_idx: int | None = None
    for i, msg in enumerate(messages):
        role = ""
        if isinstance(msg, dict):
            role = (msg.get("type") or msg.get("role") or "").lower()
        else:
            cls = type(msg).__name__.lower()
            if "human" in cls:
                role = "human"
            elif "user" in cls:
                role = "user"
        if role in ("human", "user"):
            last_human_idx = i
    if last_human_idx is None:
        return ""
    msg = messages[last_human_idx]
    content = getattr(msg, "content", None)
    if content is None and isinstance(msg, dict):
        content = msg.get("content")
    return _normalize_text(content if isinstance(content, str) else "")


def wants_to_begin_invest_workflow(text: str) -> bool:
    """True when the user asks to invest but has not necessarily named a property yet."""
    t = _normalize_text(text)
    if not t or _INVEST_RESEARCH.search(t):
        return False
    if _BEGIN_INVEST_WORKFLOW.search(t):
        return True
    return False


def has_explicit_invest_intent(text: str) -> bool:
    """True when the user is ordering a buy/invest, not researching."""
    t = _normalize_text(text)
    if not t:
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
    """True while a guided invest form is being collected or submitted."""
    if not session:
        return False
    if session.get("completing_submit"):
        return True
    return bool(session.get("in_progress")) and not session.get("submitted")


def investor_invest_wallet_permitted(
    user_text: str,
    invest_session: dict | None = None,
) -> bool:
    """Whether invest modal / MetaMask submit actions may be emitted this turn."""
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


_INVEST_ORDER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?i)(?:please\s+)?(?:buy|invest|purchase)\s+"
        r"(?P<amount>\d+|one|two|three|four|five|six|seven|eight|nine|ten|a|an|single)\s*"
        r"(?:tokens?)?\s*(?:in|into|of)\s+"
        r"(?P<property>.+?)(?:\s+property)?\s*\.?$"
    ),
    re.compile(
        r"(?i)(?:buy|invest|purchase)\s+(?:in|into|of)\s+(?P<property>.+?)\s+"
        r"(?:for\s+)?(?P<amount>\d+|one|two|three|four|five|a|an|single)\s*tokens?"
    ),
    re.compile(
        r"(?i)^(?P<amount>\d+|one|two|three|four|five|a|an|single)\s*tokens?\s*"
        r"(?:in|into|of)\s+(?P<property>.+?)(?:\s+property)?\s*\.?$"
    ),
    re.compile(
        r"(?i)(?:buy|invest|purchase)\s+(?:in|into|of)\s+(?P<property>.+?)(?:\s+property)?\s*\.?$"
    ),
)


def parse_invest_token_amount(text: str) -> str | None:
    """Parse a whole token count from voice/chat (digits or spoken words)."""
    utterance = _normalize_text(text)
    if not utterance:
        return None
    digit = re.search(r"(?i)\b(\d+)\s*tokens?\b", utterance)
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


def extract_invest_property_hint_from_utterance(text: str) -> str:
    """Best-effort property name when the user did not use a strict invest pattern."""
    utterance = _normalize_text(text)
    if not utterance:
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
    return _clean_invest_property_name(stripped)


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
    if invest_turn_explicit_token_amount(text, args_token=args_token):
        return False
    return invest_turn_specifies_property(text, args_property=args_property)


def parse_invest_order_from_utterance(text: str) -> dict[str, str]:
    """Extract property_name and/or token_amount from a buy/invest voice or chat line."""
    utterance = _normalize_text(text)
    if not utterance:
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
    text = str(raw or "0").strip()
    if not text:
        return "0"
    try:
        value = float(text)
    except (TypeError, ValueError):
        return text
    if value == int(value):
        return str(int(value))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def format_invest_target_property_speak(
    prop: dict[str, Any],
    *,
    token_amount: int | str | None = None,
) -> str:
    """Single-property summary for an invest order — not the full marketplace catalog."""
    name = str(prop.get("name") or f"Property {prop.get('id')}")
    pid = prop.get("id")
    location = str(prop.get("location") or "").strip()
    symbol = str(prop.get("token_symbol") or "").strip()
    available = _format_token_count(prop.get("tokens_available"))
    price = _format_eth_amount(prop.get("token_sale_price_eth"))
    sold = str(prop.get("sold_percentage") or "0").strip()
    rent = prop.get("monthly_rent_eth")

    lines = [
        f"Investment target: {name} (#{pid})",
    ]
    detail_bits: list[str] = []
    if location:
        detail_bits.append(location)
    if symbol:
        detail_bits.append(symbol)
    detail_bits.append(f"{sold}% sold")
    detail_bits.append(f"{available} tokens available")
    if price and price not in ("0", "0.0"):
        detail_bits.append(f"{price} ETH per token")
    if rent not in (None, "", "0", "0.0"):
        detail_bits.append(f"monthly rent {_format_eth_amount(rent)} ETH")
    lines.append(" — ".join(detail_bits))

    if token_amount is not None:
        try:
            amount_int = int(token_amount)
        except (TypeError, ValueError):
            amount_int = None
        if amount_int and amount_int > 0 and price and price not in ("0", "0.0"):
            try:
                total = float(price) * amount_int
                lines.append(
                    f"Order: {amount_int} token{'s' if amount_int != 1 else ''} "
                    f"(about {_format_eth_amount(total)} ETH plus gas)."
                )
            except (TypeError, ValueError):
                lines.append(
                    f"Order: {amount_int} token{'s' if amount_int != 1 else ''}."
                )
        elif amount_int and amount_int > 0:
            lines.append(f"Order: {amount_int} token{'s' if amount_int != 1 else ''}.")

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
        sold = str(prop.get("sold_percentage") or "0").strip()
        available = _format_token_count(prop.get("tokens_available"))
        price = str(prop.get("token_sale_price_eth") or "").strip()
        rent = prop.get("monthly_rent_eth")
        parts = [f"{index}. {name} (#{pid})"]
        detail_bits: list[str] = []
        if location:
            detail_bits.append(location)
        if symbol:
            detail_bits.append(symbol)
        detail_bits.append(f"{sold}% sold")
        detail_bits.append(f"{available} tokens available")
        if price and price not in ("0", "0.0"):
            detail_bits.append(f"{price} ETH/token")
        if rent not in (None, "", "0", "0.0"):
            detail_bits.append(f"monthly rent {rent} ETH")
        lines.append(f"   {parts[0]} - {', '.join(detail_bits)}")
    lines.extend(
        [
            "",
            "I've opened the marketplace page. Say which property you'd like to invest in, "
            "or ask for more details on any listing above.",
        ]
    )
    return "\n".join(lines)
