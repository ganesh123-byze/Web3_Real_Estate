"""Tenant copilot quick-action routing — keep UI shortcuts out of pay-rent field parsing."""
from __future__ import annotations

import re

from backend.ai.tenant_guards import _normalize_text, has_tenant_rental_browse_intent

TENANT_QUICK_ACTION_IDS = frozenset(
    {
        "tenant.pay",
        "tenant.rental",
        "tenant.history",
        "tenant.transactions",
    }
)

# Quick actions / browse phrases that are not a rental property name.
_TENANT_RENTAL_DETAILS_INTENT = re.compile(
    r"\b("
    r"my\s+(?:current\s+)?rental|rental\s+details?|lease\s+details?|"
    r"current\s+rental|lease\b"
    r")\b",
    re.IGNORECASE,
)

_TENANT_PAYMENT_HISTORY_INTENT = re.compile(
    r"\b("
    r"rent\s+payment\s+history|payment\s+history|rent\s+history|"
    r"my\s+payments?|last\s+paid"
    r")\b",
    re.IGNORECASE,
)

_TENANT_TRANSACTIONS_INTENT = re.compile(
    r"\b("
    r"recent\s+transactions?|my\s+transactions?|"
    r"transaction\s+history|all\s+my\s+recent\s+transactions?"
    r")\b",
    re.IGNORECASE,
)

_GENERIC_PAY_RENT_PHRASE = re.compile(
    r"(?i)^(?:this\s+month(?:'s|s)?\s+rent|my\s+rent|the\s+rent|month(?:'s|s)?\s+rent)$"
)


def tenant_quick_action_interrupts_workflow(quick_action_id: str | None) -> bool:
    """True for tenant shortcuts that must not fill pay-rent property_name."""
    if not quick_action_id:
        return False
    return quick_action_id in TENANT_QUICK_ACTION_IDS and quick_action_id != "tenant.pay"


def is_tenant_advisory_intent(text: str) -> bool:
    """Browse rentals, rental details, payment history, transactions — not a property name."""
    utterance = _normalize_text(text)
    if not utterance:
        return False
    if has_tenant_rental_browse_intent(utterance):
        return True
    if _TENANT_RENTAL_DETAILS_INTENT.search(utterance) and re.search(
        r"(?i)\b(?:show|tell|what|my|current)\b",
        utterance,
    ):
        return True
    if _TENANT_PAYMENT_HISTORY_INTENT.search(utterance):
        return True
    if _TENANT_TRANSACTIONS_INTENT.search(utterance):
        return True
    return False


def is_generic_pay_rent_phrase(text: str) -> bool:
    """Utterances that start pay rent but do not name a property."""
    utterance = _normalize_text(text)
    return bool(utterance and _GENERIC_PAY_RENT_PHRASE.match(utterance))


def tenant_turn_interrupts_workflow(
    utterance: str,
    *,
    quick_action_id: str | None = None,
) -> bool:
    """True when this turn should exit guided pay-rent property collection."""
    if quick_action_id == "tenant.pay":
        return False
    if tenant_quick_action_interrupts_workflow(quick_action_id):
        return True
    return is_tenant_advisory_intent(utterance)
