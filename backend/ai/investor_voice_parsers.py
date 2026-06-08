"""Voice/STT normalization for investor invest copilot flows.

Duplex voice transcribes utterances that often include trailing punctuation,
parenthetical noise tags, hedge words, and spoken number phrases. These helpers
normalize that input and detect fractional or negative token counts before the
guided invest workflow proceeds.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from backend.ai.workflow_parsers import (
    _input_indicates_negative_amount,
    _parse_spoken_decimal_amount,
    _strip_noise,
    _strip_voice_hedge_words,
)

_INVEST_SPOKEN_COUNT_WORDS = (
    r"one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|"
    r"a|an|single"
)

_STT_ARTIFACT_RE = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_TRAILING_PUNCT_RE = re.compile(r"[.!?,;:]+$")

_INVEST_TOKEN_CONTEXT_RE = re.compile(
    r"(?i)\b(?:tokens?|buy|invest|purchase)\b"
)

_SPOKEN_NEGATIVE_WITH_COUNT_RE = re.compile(
    rf"(?i)\b(?:minus|negative)\s+(?:\d+|{_INVEST_SPOKEN_COUNT_WORDS})(?:\s*tokens?)?\b"
)

_INVEST_SPOKEN_AMOUNT_IN_ORDER_RE = re.compile(
    r"(?i)(?:buy|invest|purchase)\s+(.+?)\s+tokens?\s+(?:in|into|of)\b"
)


def normalize_invest_voice_utterance(text: str) -> str:
    """Collapse whitespace, drop STT noise, and trim trailing punctuation."""
    t = _strip_noise(text)
    if not t:
        return ""
    t = _STT_ARTIFACT_RE.sub(" ", t)
    t = _strip_voice_hedge_words(t)
    t = _TRAILING_PUNCT_RE.sub("", t).strip()
    return " ".join(t.split())


def _prepare_spoken_token_amount_phrase(utterance: str) -> str:
    """Isolate the numeric phrase from STT invest lines before decimal parsing."""
    normalized = normalize_invest_voice_utterance(utterance)
    if not normalized:
        return ""
    order_match = _INVEST_SPOKEN_AMOUNT_IN_ORDER_RE.search(normalized)
    if order_match:
        return order_match.group(1).strip()
    return re.sub(r"(?i)\s*tokens?\s*$", "", normalized).strip()


def _spoken_decimal_fraction(utterance: str) -> Decimal | None:
    """Return a fractional Decimal when the utterance is a spoken decimal amount."""
    amount_phrase = _prepare_spoken_token_amount_phrase(utterance)
    parsed = _parse_spoken_decimal_amount(amount_phrase or utterance)
    if parsed is None:
        return None
    try:
        value = Decimal(parsed)
    except (InvalidOperation, ValueError, TypeError):
        return None
    if value < 0:
        return None
    lower = (amount_phrase or utterance).lower()
    if re.search(r"\bpoint\b", lower):
        return value
    if value != value.to_integral_value():
        return value
    return None


def invest_spoken_decimal_token_amount(utterance: str) -> str | None:
    """Return a decimal string when the utterance is a spoken fractional token count."""
    normalized = normalize_invest_voice_utterance(utterance)
    if not normalized:
        return None
    frac = _spoken_decimal_fraction(normalized)
    if frac is None:
        return None
    return format(frac.normalize(), "f")


def invest_spoken_negative_token_amount(utterance: str) -> bool:
    """True when STT produced a spoken negative token count (e.g. 'minus one token')."""
    normalized = normalize_invest_voice_utterance(utterance)
    if not normalized:
        return False
    if re.fullmatch(r"-\d+", normalized):
        return True
    if re.search(r"(?i)-\d+\s*tokens?\b", normalized):
        return True
    if _SPOKEN_NEGATIVE_WITH_COUNT_RE.search(normalized):
        return True
    if _input_indicates_negative_amount(normalized) and re.search(
        rf"(?i)\b(?:{_INVEST_SPOKEN_COUNT_WORDS})\b",
        normalized,
    ):
        return True
    if _input_indicates_negative_amount(normalized) and re.search(r"\d", normalized):
        return True
    return False


def invest_utterance_looks_like_token_amount_answer(utterance: str) -> bool:
    """True when the line is answering the token-count step (not naming a property)."""
    normalized = normalize_invest_voice_utterance(utterance)
    if not normalized:
        return False
    if invest_spoken_decimal_token_amount(normalized):
        return True
    if invest_spoken_negative_token_amount(normalized):
        return True
    if re.fullmatch(r"(?i)\d*\.\d+", normalized):
        return True
    if re.fullmatch(r"-\d+", normalized):
        return True
    if re.fullmatch(r"(?i)\d+", normalized):
        return True
    if re.fullmatch(rf"(?i)(?:{_INVEST_SPOKEN_COUNT_WORDS})(?:\s*tokens?)?", normalized):
        return True
    if re.fullmatch(rf"(?i)\d+\s*tokens?", normalized):
        return True
    return False


def invest_spoken_decimal_in_token_context(utterance: str) -> bool:
    """True when a spoken fractional amount appears in a buy/invest utterance."""
    if not invest_spoken_decimal_token_amount(utterance):
        return False
    normalized = normalize_invest_voice_utterance(utterance)
    return bool(_INVEST_TOKEN_CONTEXT_RE.search(normalized))
