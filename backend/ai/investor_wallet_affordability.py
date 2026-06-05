"""Investor copilot — wallet-based whole-token affordability guidance (read-only)."""
from __future__ import annotations

import re
from typing import Any

from backend.ai.investor_guards import _clean_invest_property_name, _normalize_text
from backend.services.investment_funding import read_sale_price_per_token_wei
from backend.services.wallet_funding import format_eth_funding_display, read_native_balance_wei

_WALLET_AFFORDABILITY_INTENT = re.compile(
    r"(?i)"
    r"(?:\b(?:based\s+on|with|from)\s+(?:my\s+)?wallet\s+(?:balance|eth)\b.*\bhow\s+many\s+tokens?\b)|"
    r"(?:\bhow\s+many\s+tokens?\s+(?:can|could|should)\s+i\s+(?:buy|afford|get|purchase)\b)|"
    r"(?:\bwhat\s+can\s+i\s+afford\s+to\s+buy\b)|"
    r"(?:\b(?:wallet|balance).*\bhow\s+many\s+tokens?\b)"
)

_EXPLICIT_BUY_ORDER = re.compile(
    r"(?i)\b(?:buy|invest|purchase)\s+(?:\d+|one|two|three|four|five|a|an|single)\s+tokens?\b"
)


def has_investor_wallet_affordability_intent(text: str) -> bool:
    """True when the investor asks how many whole tokens their wallet can afford."""
    utterance = _normalize_text(text)
    if not utterance:
        return False
    if _EXPLICIT_BUY_ORDER.search(utterance):
        return False
    if not re.search(r"(?i)\b(?:token|tokens)\b", utterance):
        return False
    if _WALLET_AFFORDABILITY_INTENT.search(utterance):
        return True
    return bool(
        re.search(r"(?i)\bhow\s+many\s+tokens?\b", utterance)
        and re.search(r"(?i)\b(?:wallet|balance|afford)\b", utterance)
    )


def extract_wallet_affordability_property_hint(text: str) -> str:
    """Property id (#n) or spoken name from a wallet-affordability question."""
    utterance = _normalize_text(text)
    if not utterance:
        return ""

    id_match = re.search(r"(?i)(?:property\s*)?#(\d+)\b", utterance)
    if id_match:
        return f"#{id_match.group(1)}"

    patterns = (
        r"(?i)\b(?:in|into|of|for)\s+(?:the\s+)?property\s+(.+?)(?:\?|\.|$)",
        r"(?i)\b(?:in|into|of|for)\s+(.+?)(?:\?|\.|$)",
        r"(?i)\bproperty\s+(.+?)(?:\?|\.|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, utterance)
        if not match:
            continue
        raw_name = match.group(1)
        raw_name = re.split(
            r"(?i)\s+(?:with|based\s+on|using)\s+(?:my\s+)?(?:wallet|balance)\b",
            raw_name,
            maxsplit=1,
        )[0]
        name = _clean_invest_property_name(raw_name)
        if name and name.lower() not in {"it", "this", "that", "property"}:
            return name
    return ""


def wallet_affordability_property_prompt() -> str:
    return (
        "Which property should I use for the affordability estimate? "
        "Say the property name or #id (for example, Gold Plaza or #4)."
    )


def compute_affordable_whole_tokens(
    balance_wei: int,
    sale_price_per_token_wei: int,
    *,
    tokens_available: int,
) -> int:
    """Maximum whole tokens affordable from wallet ETH, capped by listing supply."""
    price = int(sale_price_per_token_wei)
    if price <= 0:
        return 0
    balance = max(0, int(balance_wei))
    by_wallet = balance // price
    supply = max(0, int(tokens_available))
    return max(0, min(by_wallet, supply))


def format_investor_wallet_affordability_speak(
    prop: dict[str, Any],
    *,
    affordable_tokens: int,
    balance_wei: int,
    sale_price_per_token_wei: int,
) -> str:
    """Verbatim affordability answer — whole tokens only, no fractional amounts."""
    name = str(prop.get("name") or f"Property {prop.get('id')}")
    pid = prop.get("id")
    balance_eth = format_eth_funding_display(balance_wei)
    price_eth = format_eth_funding_display(sale_price_per_token_wei)
    available = int(str(prop.get("tokens_available") or "0") or 0)
    whole_only = (
        "Token purchases are whole numbers only — you cannot buy fractional tokens on-chain."
    )

    if affordable_tokens <= 0:
        return (
            f"Your wallet balance is {balance_eth} ETH, which is not enough to buy even "
            f"1 whole token in {name} (#{pid}) at {price_eth} ETH per token.\n\n"
            f"{whole_only} Add ETH to your wallet or choose another listing."
        )

    order_wei = sale_price_per_token_wei * affordable_tokens
    order_eth = format_eth_funding_display(order_wei)
    capped = affordable_tokens < (balance_wei // sale_price_per_token_wei)
    supply_note = (
        f" Only {available:,} token(s) remain for sale, so that is the maximum you can buy "
        "right now."
        if capped and available > 0
        else ""
    )

    token_label = "token" if affordable_tokens == 1 else "tokens"
    return (
        f"Based on your wallet balance of {balance_eth} ETH, you can buy up to "
        f"{affordable_tokens:,} whole {token_label} in {name} (#{pid}) at {price_eth} ETH "
        f"per token.{supply_note}\n\n"
        f"{affordable_tokens:,} {token_label} would cost about {order_eth} ETH (plus gas).\n\n"
        f"{whole_only} Say how many whole tokens you want to buy when you are ready to invest."
    )


def build_wallet_affordability_tool_payload(
    prop: dict[str, Any],
    *,
    affordable_tokens: int,
    balance_wei: int,
    sale_price_per_token_wei: int,
) -> dict[str, Any]:
    speak = format_investor_wallet_affordability_speak(
        prop,
        affordable_tokens=affordable_tokens,
        balance_wei=balance_wei,
        sale_price_per_token_wei=sale_price_per_token_wei,
    )
    return {
        "investor_wallet_affordability": True,
        "property_id": int(prop.get("id") or 0),
        "property_name": prop.get("name"),
        "affordable_whole_tokens": affordable_tokens,
        "wallet_eth": format_eth_funding_display(balance_wei),
        "sale_price_eth": format_eth_funding_display(sale_price_per_token_wei),
        "tokens_available": int(str(prop.get("tokens_available") or "0") or 0),
        "whole_tokens_only": True,
        "speak_to_user": speak,
        "speak_verbatim": True,
        "instruction": (
            "Read speak_to_user verbatim. This is a read-only affordability estimate — "
            "do NOT open the invest dialog or MetaMask. Whole token counts only."
        ),
    }


def read_wallet_balance_wei(wallet_address: str) -> int:
    return read_native_balance_wei(wallet_address)


def read_property_sale_price_wei(property_item: dict[str, Any]) -> int:
    return read_sale_price_per_token_wei(property_item)
