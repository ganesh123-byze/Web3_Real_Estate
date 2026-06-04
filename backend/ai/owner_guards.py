"""Property-owner copilot guards and verbatim portfolio analytics copy."""
from __future__ import annotations

import re
from typing import Any

from backend.ai.investor_guards import extract_last_human_utterance, _normalize_text


def has_owner_analytics_intent(text: str) -> bool:
    """True when the admin wants portfolio analytics, not a single-property detail drill-in."""
    t = _normalize_text(text).lower()
    if not t:
        return False

    if re.search(r"\b(?:details?|info)\s+(?:on|for|about)\s+", t):
        return False
    if re.search(r"\b(?:edit|update|change|delete|create)\s+(?:a\s+)?(?:new\s+)?propert", t):
        return False
    if re.search(r"\bhelp\s+me\s+create\b", t):
        return False

    if "analytics across my properties" in t:
        return True
    if re.search(r"\b(?:view|show|see|get|give)\s+(?:me\s+)?(?:my\s+)?analytics\b", t):
        return True
    if re.search(r"\banalytics\s+(?:across|for|on)\s+my\s+propert", t):
        return True
    if re.search(r"\b(?:dashboard|portfolio)\s+overview\b", t):
        return True
    if re.search(r"\bportfolio\s+(?:analytics|intelligence)\b", t):
        return True
    if re.search(r"\bplatform\s+summary\b", t) and re.search(r"\b(?:my|own)\b", t):
        return True
    if re.search(r"\b(?:rent|investors?).*\b(?:together|overview|summary)\b", t):
        return True
    if re.search(r"\b(?:overview|summary)\b", t) and re.search(
        r"\b(?:analytics|dashboard|portfolio|properties|rent|investors?)\b", t
    ):
        return True
    return False


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


def format_owner_analytics_overview_speak(data: dict[str, Any]) -> str:
    """Verbatim portfolio analytics for admin browse / View Analytics quick action."""
    summary = dict(data.get("summary") or {})
    names = [str(n).strip() for n in (summary.get("property_names") or []) if str(n).strip()]
    count = int(summary.get("properties_you_own") or summary.get("total_properties") or len(names) or 0)

    if count <= 0:
        return (
            "You do not have any dashboard-visible properties yet. "
            "Create a listing first, then ask for analytics again."
        )

    lines = [
        "Portfolio analytics across your properties:",
        "",
        f"You have {count} listing{'s' if count != 1 else ''}"
        + (f": {', '.join(names)}." if names else "."),
        "",
        f"Rent collected: {_format_eth_amount(summary.get('total_rent_collected_eth'))} ETH "
        f"({int(summary.get('rent_payments_count') or 0)} payment"
        f"{'s' if int(summary.get('rent_payments_count') or 0) != 1 else ''})",
        f"Rent distributed to investors: {_format_eth_amount(summary.get('total_rent_distributed_eth'))} ETH "
        f"({int(summary.get('rent_distributions_count') or 0)} distribution"
        f"{'s' if int(summary.get('rent_distributions_count') or 0) != 1 else ''})",
        f"Active rentals: {int(summary.get('active_rentals') or 0)}",
        f"Investors on your properties: {int(summary.get('investors_on_your_properties') or 0)}",
        f"Properties with token sales: {int(summary.get('properties_with_token_sales') or 0)}",
        f"Investment volume recorded: {_format_eth_amount(summary.get('total_investment_volume_eth'))} ETH "
        f"({int(summary.get('total_investments_recorded') or 0)} investment"
        f"{'s' if int(summary.get('total_investments_recorded') or 0) != 1 else ''})",
    ]

    perf = list(data.get("property_performance") or [])[:6]
    if perf:
        lines.extend(["", "Property performance (sold %):"])
        for index, row in enumerate(perf, start=1):
            name = str(row.get("name") or f"Property {row.get('id')}")
            sold_pct = _format_eth_amount(row.get("sold_percentage"))
            sold = _format_eth_amount(row.get("tokens_sold"))
            supply = _format_eth_amount(row.get("token_supply"))
            lines.append(f"{index}. {name} — {sold_pct}% sold ({sold} / {supply} tokens)")

    recent_tx = list(data.get("recent_transactions") or [])
    if recent_tx:
        lines.extend(
            [
                "",
                f"Recent ledger activity: {len(recent_tx)} transaction"
                f"{'s' if len(recent_tx) != 1 else ''} on your listings.",
            ]
        )

    lines.extend(
        [
            "",
            "Open your Dashboard for charts, investor ownership, and transaction breakdown.",
        ]
    )
    return "\n".join(lines)


def owner_analytics_tool_payload(data: dict[str, Any]) -> dict[str, Any]:
    speak = format_owner_analytics_overview_speak(data)
    return {
        **data,
        "owner_analytics_overview": True,
        "speak_to_user": speak,
        "speak_verbatim": True,
        "instruction": (
            "Read speak_to_user verbatim. This is portfolio-wide analytics across every "
            "property the admin created — not a single-property create confirmation summary."
        ),
    }
