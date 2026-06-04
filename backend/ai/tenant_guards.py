"""Tenant copilot guards — pay-rent wallet actions and property #id resolution."""
from __future__ import annotations

import re

_PAY_RENT_INFO = re.compile(
    r"\b("
    r"how\s+much|when\s+is|when\s+do\s+i|due\s+date|next\s+due|"
    r"payment\s+history|rent\s+history|last\s+paid|history|"
    r"who\s+owns|tell\s+me\s+about"
    r")\b",
    re.IGNORECASE,
)

_PAY_RENT_TRANSACTIONAL = re.compile(
    r"\b("
    r"(?:please\s+)?pay\s+(?:the\s+|my\s+|this\s+)?(?:month(?:'s|s)?\s+)?rent\b|"
    r"(?:please\s+)?(?:submit|send|make)\s+(?:the\s+)?(?:my\s+)?rent\s+payment\b|"
    r"i\s+want\s+to\s+pay\s+(?:the\s+)?(?:my\s+)?rent\b|"
    r"let(?:'s|\s+us)\s+pay\s+rent\b|"
    r"pay\s+rent\s+(?:for|on)\b"
    r")\b",
    re.IGNORECASE,
)

_BEGIN_PAY_RENT_WORKFLOW = re.compile(
    r"\b("
    r"i\s+want\s+to\s+pay\s+rent|"
    r"help\s+me\s+pay\s+rent|"
    r"start\s+paying\s+rent|"
    r"ready\s+to\s+pay\s+rent"
    r")\b",
    re.IGNORECASE,
)


def _normalize_text(text: str) -> str:
    return " ".join((text or "").split())


def pay_rent_workflow_active(session: dict | None) -> bool:
    """True while a guided pay-rent form is being collected or submitted."""
    if not session:
        return False
    if session.get("completing_submit"):
        return True
    return bool(session.get("in_progress")) and not session.get("submitted")


def wants_to_begin_pay_rent_workflow(text: str) -> bool:
    """User asked to pay rent but may not have named a property yet."""
    t = _normalize_text(text)
    if not t:
        return False
    return bool(_BEGIN_PAY_RENT_WORKFLOW.search(t))


def has_explicit_pay_rent_intent(text: str) -> bool:
    """True when the user is ordering a rent payment, not browsing rent history."""
    t = _normalize_text(text)
    if not t:
        return False
    if _PAY_RENT_INFO.search(t) and not _PAY_RENT_TRANSACTIONAL.search(t):
        return False
    if _PAY_RENT_TRANSACTIONAL.search(t):
        return True
    if re.search(r"(?i)#(\d+)\b", t) and re.search(r"(?i)\brent\b", t):
        return True
    return wants_to_begin_pay_rent_workflow(t)


def extract_pay_rent_property_hint_from_utterance(text: str) -> str:
    """Property id (#n) or spoken name from a pay-rent utterance."""
    utterance = _normalize_text(text)
    if not utterance:
        return ""

    id_match = re.search(r"(?i)(?:property\s*)?#(\d+)\b", utterance)
    if id_match:
        return f"#{id_match.group(1)}"

    stripped = re.sub(
        r"(?i)^(?:please\s+)?(?:help\s+me\s+)?(?:i\s+want\s+to\s+)?"
        r"(?:pay|submit|send|make)\s+(?:the\s+|my\s+|this\s+)?"
        r"(?:month(?:'s|s)?\s+)?rent\s*(?:for|on)?\s*",
        "",
        utterance,
    ).strip()
    stripped = re.sub(r"(?i)^(?:for|on)\s+", "", stripped).strip()
    return stripped
