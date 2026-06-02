"""Token symbol collection prompt for admin create-property copilot."""
from backend.ai.workflow_parsers import (
    create_property_field_collection_speak,
    create_property_token_symbol_prompt,
)


def test_token_symbol_prompt_includes_examples():
    msg = create_property_token_symbol_prompt()
    assert "ticker" in msg.lower()
    assert "OCEAN" in msg
    assert "ETH" in msg


def test_token_symbol_prompt_suggests_from_property_name():
    msg = create_property_token_symbol_prompt("Sunset Beach Villas")
    assert "Sunset" in msg or "SBV" in msg.upper() or "S" in msg


def test_field_collection_speak_only_for_token_symbol():
    assert create_property_field_collection_speak("token_symbol", {"name": "Ocean Tower"}) is not None
    assert create_property_field_collection_speak("location", {"name": "Ocean Tower"}) is None
