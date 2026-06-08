"""Unit tests for identity-first property name resolution."""
from backend.ai.property_name_resolution import (
    property_broad_match_score,
    property_identity_match_score,
    resolve_property_query_from_items,
)


def test_identity_score_ignores_location_substring():
    prop = {"name": "Golden Heist Villa", "location": "Brightcone Hills", "token_symbol": "GHV"}
    assert property_identity_match_score("brightcone", prop) < 0.72
    assert property_broad_match_score("brightcone", prop) >= 0.94


def test_resolve_prefers_exact_property_name():
    items = [
        {"id": 1, "name": "Brightcone", "token_symbol": "BC"},
        {"id": 2, "name": "Golden Heist Villa", "location": "Brightcone Hills", "token_symbol": "GHV"},
    ]
    prop, err = resolve_property_query_from_items(
        items,
        "brightcone",
        label="investable properties",
        not_found_prefix="No investable property found matching",
    )
    assert err is None
    assert prop and int(prop["id"]) == 1
