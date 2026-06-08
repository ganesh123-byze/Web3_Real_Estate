"""Investor copilot quick-action routing — keep UI shortcuts out of invest field parsing."""
from __future__ import annotations

import re

from backend.ai.investor_guards import _normalize_text, has_investor_portfolio_intent
from backend.ai.investor_marketplace import has_marketplace_browse_intent
from backend.ai.investor_wallet_affordability import has_investor_wallet_affordability_intent

INVESTOR_QUICK_ACTION_IDS = frozenset(
    {
        "investor.marketplace",
        "investor.portfolio",
        "investor.yield",
        "investor.transactions",
    }
)

_INVESTOR_YIELD_INTENT = re.compile(
    r"\b("
    r"yield|returns?|projected\s+returns?|rental\s+yield|"
    r"claimable|earned|earnings?"
    r")\b",
    re.IGNORECASE,
)

_INVESTOR_TRANSACTIONS_INTENT = re.compile(
    r"\b("
    r"recent\s+transactions?|my\s+transactions?|"
    r"transaction\s+history|payment\s+history|activity"
    r")\b",
    re.IGNORECASE,
)


def investor_quick_action_interrupts_workflow(quick_action_id: str | None) -> bool:
    """True when the UI sent a known investor quick-action id."""
    return bool(quick_action_id and quick_action_id in INVESTOR_QUICK_ACTION_IDS)


def is_investor_advisory_intent(text: str) -> bool:
    """Browse / portfolio / yield / transactions / affordability — not invest field input."""
    utterance = _normalize_text(text)
    if not utterance:
        return False
    if has_investor_wallet_affordability_intent(utterance):
        return True
    if has_marketplace_browse_intent(utterance):
        return True
    if has_investor_portfolio_intent(utterance):
        return True
    if _INVESTOR_TRANSACTIONS_INTENT.search(utterance):
        return True
    if _INVESTOR_YIELD_INTENT.search(utterance) and re.search(
        r"(?i)\b(?:what|show|tell|how\s+much|my|current|projected)\b",
        utterance,
    ):
        return True
    return False


def investor_turn_interrupts_workflow(
    utterance: str,
    *,
    quick_action_id: str | None = None,
) -> bool:
    """True when this turn should exit the guided invest workflow."""
    return investor_quick_action_interrupts_workflow(
        quick_action_id
    ) or is_investor_advisory_intent(utterance)
