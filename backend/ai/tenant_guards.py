"""Tenant copilot guards — pay-rent wallet actions and property #id resolution."""
from __future__ import annotations

import re
from typing import Any

PAY_RENT_SUMMARY_HEADING = "Rent payment summary"

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
    if session.get("awaiting_pay_rent_confirmation"):
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


def pay_rent_utterance_names_property(
    text: str,
    *,
    quick_action_id: str | None = None,
) -> bool:
    """True when the user named a concrete property (id or title), not only 'pay rent'."""
    utterance = _normalize_text(text)
    if not utterance:
        return False

    from backend.ai.tenant_quick_actions import (
        is_tenant_advisory_intent,
        tenant_quick_action_interrupts_workflow,
    )

    if tenant_quick_action_interrupts_workflow(quick_action_id):
        return False
    if is_tenant_advisory_intent(utterance):
        return False

    if re.search(r"(?i)(?:property\s*)?#(\d+)\b", utterance):
        return True
    hint = extract_pay_rent_property_hint_from_utterance(
        utterance, quick_action_id=quick_action_id
    )
    if not hint or hint in {".", "-", "?"}:
        return False
    return len(hint) >= 2



def _pay_rent_property_hint_after_strip(utterance: str) -> str:
    stripped = re.sub(
        r"(?i)^(?:please\s+)?(?:help\s+me\s+)?(?:i\s+want\s+to\s+)?"
        r"(?:pay|submit|send|make)\s+(?:the\s+|my\s+|this\s+)?"
        r"(?:month(?:'s|s)?\s+)?rent\s*(?:for|on)?\s*",
        "",
        utterance,
    ).strip()
    return re.sub(r"(?i)^(?:for|on)\s+", "", stripped).strip()


def extract_pay_rent_property_hint_from_utterance(
    text: str,
    *,
    quick_action_id: str | None = None,
) -> str:
    """Property id (#n) or spoken name from a pay-rent utterance."""
    utterance = _normalize_text(text)
    if not utterance:
        return ""

    from backend.ai.tenant_quick_actions import (
        is_generic_pay_rent_phrase,
        is_tenant_advisory_intent,
        tenant_quick_action_interrupts_workflow,
    )

    if tenant_quick_action_interrupts_workflow(quick_action_id):
        return ""
    if is_tenant_advisory_intent(utterance):
        return ""

    id_match = re.search(r"(?i)(?:property\s*)?#(\d+)\b", utterance)
    if id_match:
        return f"#{id_match.group(1)}"

    stripped = re.sub(r"[.!?]+$", "", _pay_rent_property_hint_after_strip(utterance)).strip()
    if not stripped or stripped.endswith("rent") or is_generic_pay_rent_phrase(stripped):
        return ""
    return stripped


def format_pay_rent_target_speak(prop: dict[str, Any]) -> str:
    """Single-property rent summary for chat confirmation."""
    name = str(prop.get("name") or f"Property {prop.get('id')}")
    pid = prop.get("id")
    location = str(prop.get("location") or "").strip()
    rent = str(prop.get("monthly_rent_eth") or "").strip()

    lines = [PAY_RENT_SUMMARY_HEADING, f"Property: {name} (#{pid})"]
    if location:
        lines.append(f"Location: {location}")
    if rent and rent not in ("0", "0.0"):
        lines.append(f"Monthly rent: {rent} ETH")
    else:
        lines.append("Monthly rent: —")
    return "\n".join(lines)


def format_pay_rent_confirmation_summary(prop: dict[str, Any]) -> str:
    """Rent payment summary with yes/no confirmation footer."""
    summary = format_pay_rent_target_speak(prop)
    return (
        f"{summary}\n\n"
        "Reply Yes to proceed with this rent payment in MetaMask, or No to cancel."
    )


_TENANT_RENTAL_BROWSE = re.compile(
    r"(?i)"
    r"(?:\b(?:take\s+me\s+to|go\s+to|open)\s+(?:the\s+)?(?:tenant\s+)?rentals?\b)|"
    r"(?:\bbrowse\s+(?:the\s+)?(?:available\s+)?rentals?\b)|"
    r"(?:\bwhat\s+can\s+i\s+rent\b)|"
    r"(?:\brentals?\s+(?:available|dashboard)\b)|"
    r"(?:\b(?:show|list|what|which).*\b(?:available|for\s+rent|to\s+rent)\b)|"
    r"(?:\bpropert(?:y|ies).*\b(?:available|for\s+rent|to\s+rent)\b)"
)


def has_tenant_rental_browse_intent(text: str) -> bool:
    """True when the tenant wants to browse rentable listings — not pay rent yet."""
    utterance = _normalize_text(text)
    if not utterance:
        return False
    if _PAY_RENT_TRANSACTIONAL.search(utterance) and not re.search(
        r"(?i)\b(?:show|list|available|what|which|browse)\b",
        utterance,
    ):
        return False
    if _TENANT_RENTAL_BROWSE.search(utterance):
        return True
    if re.search(r"(?i)\b(?:show|list|what|which).*\bavailable\b", utterance) and re.search(
        r"(?i)\b(?:rent|rental)\b",
        utterance,
    ):
        return True
    if re.search(r"(?i)\bpropert(?:y|ies)\b", utterance) and re.search(
        r"(?i)\b(?:for\s+rent|to\s+rent)\b",
        utterance,
    ):
        return True
    return False


def format_tenant_rental_catalog_speak(
    available: list[dict[str, Any]],
    *,
    total_listed: int,
) -> str:
    """Verbatim rentals summary for tenant browse turns."""
    if not available:
        if total_listed <= 0:
            return (
                "There are no funded properties on the tenant Rentals dashboard yet. "
                "Check back after investors fund new listings."
            )
        return (
            f"There are {total_listed} funded listing(s), but none are available to pay "
            "rent on right now — rent may be disabled, already paid this cycle, or "
            "claimed by another tenant. Ask again later or say which property you need."
        )

    lines = [
        "Here are the properties available for rent right now:",
        "",
    ]
    for index, prop in enumerate(available, start=1):
        name = str(prop.get("name") or f"Property {prop.get('id')}")
        pid = prop.get("id")
        location = str(prop.get("location") or "").strip()
        rent = str(prop.get("monthly_rent_eth") or "").strip()
        detail_bits: list[str] = []
        if location:
            detail_bits.append(location)
        if rent and rent not in ("0", "0.0"):
            detail_bits.append(f"monthly rent {rent} ETH")
        else:
            detail_bits.append("monthly rent —")
        lines.append(f"   {index}. {name} (#{pid}) - {', '.join(detail_bits)}")
    lines.extend(
        [
            "",
            "I've opened the Rentals page. Say which property you'd like to pay rent on "
            "(name or #id), or ask for more details on any listing above.",
        ]
    )
    return "\n".join(lines)
