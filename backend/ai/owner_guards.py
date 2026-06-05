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


def has_owner_investors_intent(text: str) -> bool:
    """True when the admin wants their token holders / investors list (not create summary)."""
    t = _normalize_text(text).lower()
    if not t:
        return False
    if re.search(r"\b(?:create|add)\s+(?:a\s+)?(?:new\s+)?propert", t):
        return False
    if re.search(r"\bhelp\s+me\s+create\b", t):
        return False
    if "investors holding shares of my properties" in t:
        return True
    if re.search(r"\b(?:my|show|list|who)\s+investors\b", t):
        return True
    if re.search(r"\binvestors?\s+(?:on|for|in|of)\s+my\s+propert", t):
        return True
    if re.search(r"\b(?:token\s+)?holders?\b", t) and re.search(r"\b(?:my|mine)\b", t):
        return True
    if re.search(r"\bwho\s+invested\b", t) and re.search(r"\b(?:my|mine)\b", t):
        return True
    return False


def has_owner_browse_intent(text: str) -> bool:
    """True when the admin wants portfolio/rent/investor data — not create-property steps."""
    return (
        has_owner_analytics_intent(text)
        or has_owner_investors_intent(text)
        or has_owner_rent_intent(text)
    )


def has_owner_rent_intent(text: str) -> bool:
    """True for rent collection / yield / analytics — not create-property confirmation."""
    t = _normalize_text(text).lower()
    if not t:
        return False
    if re.search(r"\b(?:create|add)\s+(?:a\s+)?(?:new\s+)?propert", t):
        return False
    if re.search(r"\bhelp\s+me\s+create\b", t):
        return False
    if "pending rent collections and overdue tenants" in t:
        return True
    if re.search(r"\brent\s+collection", t):
        return True
    if re.search(r"\brent\s+yield\b", t):
        return True
    if re.search(r"\b(?:rental|rent)\s+yield\b", t):
        return True
    if re.search(r"\byield\s+value\b", t) and re.search(r"\b(?:rent|rental)\b", t):
        return True
    if re.search(r"\b(?:my|show)\s+.*\byield\b", t) and re.search(r"\b(?:rent|rental)\b", t):
        return True
    if re.search(r"\brent\s+collection", t):
        return True
    if re.search(r"\b(?:pending|overdue)\s+rent\b", t):
        return True
    if re.search(r"\brent\s+(?:i(?:'ve| have)?\s+)?collected\b", t):
        return True
    if re.search(r"\b(?:my|show)\s+rent\s+analytics\b", t):
        return True
    if re.search(r"\btotal\s+rent\s+collected\b", t):
        return True
    return False


def _short_wallet(wallet: str) -> str:
    w = str(wallet or "").strip()
    if len(w) < 12:
        return w or "unknown"
    return f"{w[:6]}…{w[-4:]}"


def _format_owner_investor_ownership_pct(pct: Any) -> str:
    try:
        value = float(pct)
    except (TypeError, ValueError):
        return "0%"
    if value <= 0:
        return "0%"
    if value < 0.01:
        return f"{value:.4f}%"
    return f"{value:.2f}%"


def format_owner_investors_speak(data: dict[str, Any]) -> str:
    """Verbatim investors summary for My investors quick action / chat."""
    total = int(data.get("total_investors") or 0)
    properties = list(data.get("properties") or [])
    if total <= 0 or not properties:
        return (
            "You do not have any investors holding tokens on your properties yet. "
            "After token sales, investors will appear here grouped by listing."
        )

    lines = [
        f"Investors on your properties ({total} wallet{'s' if total != 1 else ''} across "
        f"{len(properties)} listing{'s' if len(properties) != 1 else ''}):",
        "",
    ]
    for index, prop in enumerate(properties[:8], start=1):
        name = str(prop.get("property_name") or f"Property {prop.get('property_id')}")
        investors = list(prop.get("investors") or [])
        lines.append(f"{index}. {name} — {len(investors)} investor{'s' if len(investors) != 1 else ''}")
        for inv in investors[:5]:
            wallet = _short_wallet(str(inv.get("wallet_address") or ""))
            tokens = inv.get("token_amount")
            pct = _format_owner_investor_ownership_pct(inv.get("ownership_percentage"))
            lines.append(f"   • {wallet}: {tokens} tokens ({pct} of supply)")
        if len(investors) > 5:
            lines.append(f"   • …and {len(investors) - 5} more")
        lines.append("")

    lines.append("Open the Investors page on your dashboard for the full table.")
    return "\n".join(lines).strip()


def format_owner_rent_speak(
    analytics: dict[str, Any],
    collections: dict[str, Any],
) -> str:
    """Verbatim rent / yield summary — not a create-property confirmation."""
    collected = _format_eth_amount(analytics.get("total_rent_collected_eth"))
    payments_count = int(analytics.get("payments_count") or 0)
    active_rentals = int(analytics.get("active_rentals") or 0)
    recent = list(collections.get("payments") or [])[:5]

    lines = [
        "Rent and yield across your properties:",
        "",
        f"Total rent collected: {collected} ETH ({payments_count} payment"
        f"{'s' if payments_count != 1 else ''})",
        f"Active rentals: {active_rentals}",
    ]

    if recent:
        lines.extend(["", "Recent rent payments:"])
        for index, row in enumerate(recent, start=1):
            name = str(row.get("property_name") or f"Property {row.get('property_id')}")
            amount = _format_eth_amount(row.get("amount_eth"))
            status = str(row.get("payment_status") or "recorded")
            lines.append(f"{index}. {name} — {amount} ETH ({status})")
    else:
        lines.extend(
            [
                "",
                "No rent payments recorded yet on your listings.",
            ]
        )

    lines.extend(
        [
            "",
            "Open Rent Management on your dashboard for collections, distributions, and overdue tenants.",
        ]
    )
    return "\n".join(lines)


def owner_investors_tool_payload(data: dict[str, Any]) -> dict[str, Any]:
    speak = format_owner_investors_speak(data)
    return {
        **data,
        "owner_investors_overview": True,
        "speak_to_user": speak,
        "speak_verbatim": True,
        "instruction": (
            "Read speak_to_user verbatim. This is the admin's investor list — "
            "not a create-property confirmation summary."
        ),
    }


def owner_rent_tool_payload(
    analytics: dict[str, Any],
    collections: dict[str, Any],
) -> dict[str, Any]:
    speak = format_owner_rent_speak(analytics, collections)
    return {
        "rent_analytics": analytics,
        "rent_collections": collections,
        "owner_rent_overview": True,
        "speak_to_user": speak,
        "speak_verbatim": True,
        "instruction": (
            "Read speak_to_user verbatim. This is rent/yield data across the admin's "
            "properties — not a create-property confirmation summary."
        ),
    }
