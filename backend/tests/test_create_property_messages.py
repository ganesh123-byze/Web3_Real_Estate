"""Copy for copilot create-property deploy + success (text and voice)."""
from backend.ai.create_property_messages import (
    create_property_deploying_message,
    create_property_success_message,
)


def test_deploying_message_without_name():
    msg = create_property_deploying_message()
    assert "details are submitted" in msg.lower()
    assert "hold" in msg.lower()
    assert "deploy" in msg.lower()


def test_deploying_message_with_name():
    msg = create_property_deploying_message("Sunset Villas")
    assert "Sunset Villas" in msg
    assert "details" in msg.lower()


def test_success_message_with_name():
    msg = create_property_success_message("Sunset Villas")
    assert "Sunset Villas" in msg
    assert "successfully created" in msg.lower()


def test_success_message_includes_rent_warning():
    warning = "Monthly rent exceeds the on-chain limit of 100 ETH."
    msg = create_property_success_message("Tower One", rent_sync_warning=warning)
    assert "Tower One" in msg
    assert warning in msg
    assert "Sync Rent Chain" in msg
