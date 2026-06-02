"""User-facing copy for copilot create-property (text + voice). Single source of truth."""
from __future__ import annotations


def create_property_deploying_message(property_name: str | None = None) -> str:
    """Shown when the user confirmed and on-chain deploy has started."""
    name = (property_name or "").strip()
    if name:
        return (
            f"Your property details for {name} were submitted successfully. "
            "Please hold for a moment while we deploy your listing on-chain."
        )
    return (
        "Your property details were submitted successfully. "
        "Please hold for a moment while we deploy your listing on-chain."
    )


def create_property_success_message(
    property_name: str,
    *,
    rent_sync_warning: str | None = None,
) -> str:
    """Final success line after deploy completes (dashboard-visible listing)."""
    clean = (property_name or "").strip()
    if clean:
        base = f"Your property {clean} was successfully created and is on your Properties dashboard."
    else:
        base = "Your property was successfully created and is on your Properties dashboard."
    warning = (rent_sync_warning or "").strip()
    if not warning:
        return base
    return (
        f"{base} Monthly rent could not be set on-chain automatically ({warning}) "
        "Open the property and use Sync Rent Chain when you are ready."
    )
