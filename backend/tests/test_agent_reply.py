"""Verbatim tool replies bypass LLM paraphrase."""
from __future__ import annotations

from backend.ai.agent_reply import pick_verbatim_speak_to_user, tool_data_requires_verbatim_reply
from backend.ai.workflow_parsers import format_create_property_confirmation_summary


def test_create_property_confirmation_requires_verbatim():
    summary = format_create_property_confirmation_summary(
        {
            "name": "my home apartments",
            "location": "Hyderabad",
            "total_value": "10",
            "token_supply": "100000",
            "token_symbol": "ETH",
            "monthly_rent_eth": "1",
        }
    )
    data = {
        "awaiting_create_confirmation": True,
        "confirmation_summary": summary,
        "speak_to_user": summary,
    }
    assert tool_data_requires_verbatim_reply(data)
    assert "To edit," in summary
    assert "To delete" in summary


def test_pick_verbatim_prefers_last_authoritative_tool():
    speak = "Here are the property details I have:\n- Name: Tower\n\nTo edit,"
    chosen = pick_verbatim_speak_to_user(
        [
            ("list_properties", {"speak_to_user": "ignored"}),
            (
                "fill_create_property",
                {
                    "awaiting_create_confirmation": True,
                    "speak_to_user": speak,
                },
            ),
        ]
    )
    assert chosen == speak
