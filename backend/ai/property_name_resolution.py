"""Property name resolution for copilot invest, rent, and owner workflows.

Callers must pass dashboard-visible property rows only (see
``list_copilot_properties`` / ``property_is_copilot_visible``).
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Callable

STRONG_MATCH_THRESHOLD = 0.72
SUBSTRING_MATCH_SCORE = 0.94
AMBIGUITY_SCORE_GAP = 0.08
WEAK_MATCH_THRESHOLD = 0.58


def normalize_match_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def score_normalized_query_against_text(query_norm: str, candidate: object) -> float:
    candidate_norm = normalize_match_text(candidate)
    if not query_norm or not candidate_norm:
        return 0.0
    if query_norm == candidate_norm:
        return 1.0
    if query_norm in candidate_norm or candidate_norm in query_norm:
        return SUBSTRING_MATCH_SCORE
    return SequenceMatcher(None, query_norm, candidate_norm).ratio()


def property_identity_match_score(query: str, prop: dict) -> float:
    """Match listing identity only — property name and token symbol (not location)."""
    query_norm = normalize_match_text(query)
    if not query_norm:
        return 0.0
    scores = [
        score_normalized_query_against_text(query_norm, prop.get("name")),
        score_normalized_query_against_text(query_norm, prop.get("token_symbol")),
    ]
    return max(scores)


def property_broad_match_score(query: str, prop: dict) -> float:
    """Broader match for marketplace search — includes location."""
    query_norm = normalize_match_text(query)
    if not query_norm:
        return 0.0
    candidates = [
        prop.get("name"),
        prop.get("location"),
        prop.get("token_symbol"),
        f"{prop.get('name') or ''} {prop.get('location') or ''}",
    ]
    return max(
        score_normalized_query_against_text(query_norm, candidate)
        for candidate in candidates
        if candidate not in (None, "")
    ) if any(candidate not in (None, "") for candidate in candidates) else 0.0


def rank_properties_by_score(
    query: str,
    items: list[dict],
    scorer: Callable[[str, dict], float],
) -> list[tuple[float, dict]]:
    ranked = [(scorer(query, prop), prop) for prop in items]
    ranked.sort(key=lambda item: (item[0], int(item[1].get("id") or 0)), reverse=True)
    return ranked


def _format_property_options(items: list[tuple[float, dict]], limit: int = 3) -> str:
    return ", ".join((prop.get("name") or f"#{prop.get('id')}") for _, prop in items[:limit])


def find_unique_exact_property_name_match(
    items: list[dict],
    query: str,
) -> dict | None:
    """Return the sole listing whose title equals the spoken query (normalized)."""
    query_norm = normalize_match_text(query)
    if not query_norm:
        return None
    matches = [
        prop
        for prop in items
        if normalize_match_text(prop.get("name")) == query_norm
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def pick_exact_name_from_ranked_ties(
    strong: list[tuple[float, dict]],
    query: str,
) -> dict | None:
    """When several listings tie, prefer an exact title match over symbol/location hits."""
    query_norm = normalize_match_text(query)
    if not query_norm:
        return None
    name_matches = [
        prop
        for _score, prop in strong
        if normalize_match_text(prop.get("name")) == query_norm
    ]
    if len(name_matches) == 1:
        return name_matches[0]
    return None


def pick_unique_property_from_ranked(
    ranked: list[tuple[float, dict]],
    query: str,
    *,
    label: str,
    not_found_prefix: str,
) -> tuple[dict | None, str | None]:
    if not ranked:
        return None, f"No {label} are available right now."

    strong = [(score, prop) for score, prop in ranked if score >= STRONG_MATCH_THRESHOLD]
    if not strong:
        best_score, _best_prop = ranked[0]
        if best_score < WEAK_MATCH_THRESHOLD:
            examples = _format_property_options(ranked)
            return None, f"{not_found_prefix} {query!r}. Try one of: {examples}."
        options = _format_property_options(ranked)
        return None, f"Please confirm which property you mean: {options}."

    if len(strong) > 1 and (strong[0][0] - strong[1][0]) < AMBIGUITY_SCORE_GAP:
        exact_name = pick_exact_name_from_ranked_ties(strong, query)
        if exact_name is not None:
            return exact_name, None
        names = _format_property_options(strong)
        return None, f"Several {label} match {query!r}: {names}. Which one do you mean?"

    return strong[0][1], None


def list_disambiguation_candidate_properties(
    items: list[dict],
    query: str,
) -> list[dict]:
    """Listings the user may mean when resolution is ambiguous for ``query``."""
    q = (query or "").strip()
    if not q or not items:
        return []

    exact_name = find_unique_exact_property_name_match(items, q)
    if exact_name is not None:
        return [exact_name]

    identity_ranked = rank_properties_by_score(q, items, property_identity_match_score)
    strong = [(score, prop) for score, prop in identity_ranked if score >= STRONG_MATCH_THRESHOLD]
    if len(strong) > 1 and (strong[0][0] - strong[1][0]) < AMBIGUITY_SCORE_GAP:
        exact_name = pick_exact_name_from_ranked_ties(strong, q)
        if exact_name is not None:
            return [exact_name]
        return [prop for _score, prop in strong[:3]]

    top_identity_score = identity_ranked[0][0] if identity_ranked else 0.0
    if top_identity_score < STRONG_MATCH_THRESHOLD:
        broad_ranked = rank_properties_by_score(q, items, property_broad_match_score)
        broad_strong = [
            (score, prop) for score, prop in broad_ranked if score >= STRONG_MATCH_THRESHOLD
        ]
        if (
            len(broad_strong) > 1
            and (broad_strong[0][0] - broad_strong[1][0]) < AMBIGUITY_SCORE_GAP
        ):
            exact_name = pick_exact_name_from_ranked_ties(broad_strong, q)
            if exact_name is not None:
                return [exact_name]
            return [prop for _score, prop in broad_strong[:3]]

    return []


def resolve_property_query_from_items(
    items: list[dict],
    query: str,
    *,
    label: str,
    not_found_prefix: str,
    allow_broad_fallback: bool = True,
) -> tuple[dict | None, str | None]:
    """Resolve a spoken property query, preferring name/symbol over location."""
    q = (query or "").strip()
    if not q:
        return None, "Property name is required."
    if not items:
        return None, f"No {label} are available right now."

    exact_name = find_unique_exact_property_name_match(items, q)
    if exact_name is not None:
        return exact_name, None

    identity_ranked = rank_properties_by_score(q, items, property_identity_match_score)
    identity_result = pick_unique_property_from_ranked(
        identity_ranked,
        q,
        label=label,
        not_found_prefix=not_found_prefix,
    )
    top_identity_score = identity_ranked[0][0] if identity_ranked else 0.0

    if identity_result[0] is not None:
        return identity_result

    if identity_result[1] and "Several" in identity_result[1]:
        return identity_result

    if allow_broad_fallback and top_identity_score < STRONG_MATCH_THRESHOLD:
        broad_ranked = rank_properties_by_score(q, items, property_broad_match_score)
        return pick_unique_property_from_ranked(
            broad_ranked,
            q,
            label=label,
            not_found_prefix=not_found_prefix,
        )

    return identity_result


def resolve_investable_property_from_items(
    items: list[dict],
    query: str,
    *,
    is_investable: Callable[[dict], bool],
) -> tuple[dict | None, str | None]:
    q = (query or "").strip()
    if not q:
        return None, "Property name is required."

    investable = [prop for prop in items if is_investable(prop) is None]
    if not investable:
        return None, "No investable properties are available right now."

    id_match = re.fullmatch(r"#?(\d+)", q)
    if id_match:
        target_id = int(id_match.group(1))
        for prop in investable:
            if int(prop.get("id") or 0) == target_id:
                return prop, None
        return None, f"No investable property found with id #{target_id}."

    return resolve_property_query_from_items(
        investable,
        q,
        label="investable properties",
        not_found_prefix="No investable property found matching",
    )


def resolve_rentable_property_from_items(
    items: list[dict],
    query: str,
    *,
    is_rentable: Callable[[dict], bool],
    property_id_from_query: Callable[[str], int | None],
) -> tuple[dict | None, str | None]:
    q = (query or "").strip()
    if not q:
        return None, "Property name is required."

    rentable = [prop for prop in items if is_rentable(prop) is None]
    if not rentable:
        return None, (
            "No rent-enabled properties are available right now. "
            "Ask the owner to set monthly rent on a property first."
        )

    target_id = property_id_from_query(q)
    if target_id is not None:
        for prop in rentable:
            if int(prop.get("id") or 0) == target_id:
                return prop, None
        return None, f"No rent-enabled property found with id #{target_id}."

    return resolve_property_query_from_items(
        rentable,
        q,
        label="rent-enabled properties",
        not_found_prefix="No rent-enabled property found matching",
    )
