"""Normalize spoken / typed workflow answers before FILL_FIELD actions are emitted."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

# Spoken quantities common on property-owner voice flows (India / UK / US).
_WORD_NUMBERS: dict[str, int] = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}


def _strip_noise(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _parse_number_word_phrase(text: str) -> int | None:
    """Parse spoken counts like 'twenty five', 'one hundred', 'one hundred twenty five'."""
    t = _strip_noise(text).lower().replace("-", " ")
    if not t:
        return None
    compact = re.sub(r"[\s,]", "", t)
    if re.fullmatch(r"\d+", compact or ""):
        try:
            return int(compact)
        except ValueError:
            return None
    m = re.fullmatch(r"([\d.,]+)", t)
    if m:
        try:
            return int(float(m.group(1).replace(",", "")))
        except (TypeError, ValueError):
            return None

    tokens = [tok for tok in t.split() if tok not in {"and", "a", "an"}]
    if not tokens:
        return None

    total = 0
    current = 0
    for tok in tokens:
        if tok == "hundred":
            current = max(current, 1) * 100
            continue
        val = _WORD_NUMBERS.get(tok)
        if val is None:
            return None
        if val >= 100:
            current = val
        else:
            current += val
    total += current
    return total if total > 0 else None


def _parse_spoken_scale_multiplier(text: str, scale_word: str, multiplier: int) -> int | None:
    """Parse '<amount> million' / 'ten thousand' style phrases."""
    if not re.search(rf"\b{re.escape(scale_word)}\b", text):
        return None
    prefix = re.split(rf"\b{re.escape(scale_word)}\b", text, maxsplit=1)[0].strip()
    if not prefix:
        return multiplier
    if re.fullmatch(r"[\d.,]+", prefix.replace(" ", "")):
        try:
            base = float(prefix.replace(",", ""))
        except (TypeError, ValueError):
            return None
    else:
        parsed = _parse_number_word_phrase(prefix)
        if parsed is None:
            return None
        base = float(parsed)
    if base <= 0:
        return None
    return int(base * multiplier)


def _input_indicates_negative_amount(text: str) -> bool:
    """True when the user supplied a negative number (must be rejected for create-property)."""
    t = _strip_noise(text).lower()
    if not t:
        return False
    if re.search(r"\bnegative\b", t):
        return True
    if re.search(r"\bminus\b", t):
        return True
    # ASCII hyphen, unicode minus, en-dash, em-dash before digits
    if re.search(r"(?<![\d.])[\-\u2212\u2013\u2014]\s*[\d]", t):
        return True
    if re.search(r"^\s*[\-\u2212\u2013\u2014]\s*[\d]", t):
        return True
    return False


def _parse_spoken_integer(text: str) -> int | None:
    """Best-effort integer from phrases like 'one lakh tokens' or '10000'."""
    if _input_indicates_negative_amount(text):
        return None
    t = _strip_noise(text).lower()
    if not t:
        return None

    if re.search(r"\bone\s+lakh\b", t) or re.search(r"\b1\s+lakh\b", t):
        return 100_000
    if re.search(r"\btwo\s+lakh\b", t) or re.search(r"\b2\s+lakh\b", t):
        return 200_000
    m = re.search(r"([\d.,]+)\s*lakh", t)
    if m:
        try:
            return int(float(m.group(1).replace(",", "")) * 100_000)
        except (TypeError, ValueError):
            pass
    if re.search(r"\bone\s+crore\b", t) or re.search(r"\b1\s+crore\b", t):
        return 10_000_000
    m = re.search(r"([\d.,]+)\s*crore", t)
    if m:
        try:
            return int(float(m.group(1).replace(",", "")) * 10_000_000)
        except (TypeError, ValueError):
            pass

    for scale_word, mult in (
        ("billion", 1_000_000_000),
        ("million", 1_000_000),
        ("thousand", 1_000),
    ):
        scaled = _parse_spoken_scale_multiplier(t, scale_word, mult)
        if scaled is not None:
            return scaled

    # Compact suffix: 10k, 1.5m
    m = re.search(r"([\d.,]+)\s*([kKmM])\b", t)
    if m:
        base = float(m.group(1).replace(",", ""))
        mult = {"k": 1_000, "m": 1_000_000}[m.group(2).lower()]
        return int(base * mult)

    digits = re.sub(r"[^\d]", "", t)
    if digits:
        try:
            return int(digits)
        except ValueError:
            return None

    phrase = _parse_number_word_phrase(t)
    if phrase is not None:
        return phrase

    for word, val in _WORD_NUMBERS.items():
        if re.search(rf"\b{word}\b", t):
            return val
    return None


def _parse_decimal_amount(text: str) -> str | None:
    if _input_indicates_negative_amount(text):
        return None
    t = _strip_noise(text).lower()
    if not t or t in {"skip", "none", "no", "n/a", "zero", "0"}:
        return "0"
    m = re.search(r"([\d]+(?:[.,]\d+)?)", t)
    if not m:
        return None
    raw = m.group(1).replace(",", "")
    if "." in raw:
        return raw
    try:
        # Keep whole-number ETH values in plain decimal form (e.g. "20"),
        # never scientific notation (e.g. "2E+1"), because subsequent
        # regex-based normalization passes can truncate exponent strings.
        return str(Decimal(raw))
    except (InvalidOperation, ValueError):
        return None


_CREATE_PROPERTY_INTENT_RE = re.compile(
    r"(?i)(?:help\s+me\s+)?(?:list|create|add|register|tokenize)\s+(?:a\s+)?(?:new\s+)?propert"
)


def is_generic_create_property_intent(text: str) -> bool:
    """True when the user is starting the workflow, not answering \"property name\"."""
    t = _strip_noise(text).lower()
    if not t:
        return False
    if _CREATE_PROPERTY_INTENT_RE.search(t):
        return True
    if "tokenization" in t and "propert" in t:
        return True
    if re.search(r"(?i)^(?:i\s+)?want\s+to\s+(?:list|create|add)\b", t) and "propert" in t:
        return True
    return False


def assistant_prompted_for_create_field(assistant_text: str, field: str) -> bool:
    """True when the latest assistant turn explicitly asked for ``field``."""
    t = _strip_noise(assistant_text).lower()
    if not t:
        return False
    prompts: dict[str, tuple[str, ...]] = {
        "name": (
            "name of the property",
            "property name",
            "what's the name",
            "what is the name",
            "whats the name",
        ),
        "location": (
            "where is it located",
            "where is the property",
            "location of the property",
            "what's the location",
            "what is the location",
            "whats the location",
        ),
        "total_value": (
            "total property value",
            "total value",
            "value in eth",
            "wallet can support",
            "up to",
            "maximum",
        ),
        "token_supply": (
            "how many ownership tokens",
            "how many tokens",
            "token supply",
            "tokens should we mint",
        ),
        "token_symbol": (
            "ticker symbol",
            "token symbol",
            "symbol do you want",
            "short ticker",
            "ticker for the token",
            "provide a short ticker",
            "provide a ticker",
            "what ticker",
        ),
        "monthly_rent_eth": (
            "monthly rent must be less than 100 eth",
            "what's the monthly rent",
            "what is the monthly rent",
            "whats the monthly rent",
            "open the rent",
            "no rent yet",
        ),
    }
    return any(phrase in t for phrase in prompts.get(field, ()))


def assistant_prompted_for_edit_property(assistant_text: str) -> bool:
    """True when the assistant is in an edit-existing-property turn (not create)."""
    t = _strip_noise(assistant_text).lower()
    if not t:
        return False
    return (
        "what would you like to change" in t
        or "opened the edit form" in t
        or "edit form for" in t
        or "i've opened the edit form" in t
    )


def normalize_create_property_field(field: str, raw: str) -> str:
    """Map a single user answer onto a form-ready string for CREATE_PROPERTY."""
    text = _strip_noise(raw)
    if not text:
        return text

    if field == "token_supply":
        return _normalize_create_property_token_supply(text)

    if field == "token_symbol":
        return _normalize_create_property_token_symbol(text)

    if field == "total_value":
        return _normalize_create_property_total_value(text)

    if field == "monthly_rent_eth":
        return _normalize_create_property_monthly_rent(text)

    if field == "name":
        if is_generic_create_property_intent(text):
            return ""
        # Drop leading filler: "the name is SpaceX" → SpaceX
        m = re.search(
            r"(?:name\s+is|called|property\s+is|it's|its)\s+(.+)$",
            text,
            re.IGNORECASE,
        )
        return _strip_noise(m.group(1)) if m else text

    if field == "location":
        m = re.search(
            r"(?:located\s+in|location\s+is|in|at)\s+(.+)$",
            text,
            re.IGNORECASE,
        )
        return _strip_noise(m.group(1)) if m else text

    return text


CREATE_PROPERTY_NUMERIC_FIELDS = frozenset({"total_value", "token_supply", "monthly_rent_eth"})
CREATE_PROPERTY_TOKEN_SYMBOL_MIN_LEN = 2
CREATE_PROPERTY_TOKEN_SYMBOL_MAX_LEN = 10

# Strict collection order for the admin create-property copilot.
CREATE_PROPERTY_FIELD_ORDER: tuple[str, ...] = (
    "name",
    "location",
    "total_value",
    "token_supply",
    "token_symbol",
    "monthly_rent_eth",
)


def _normalize_create_property_token_supply(text: str) -> str:
    """Positive whole-number token supply only (no letters or stray symbols)."""
    if _input_indicates_negative_amount(text):
        return ""
    n = _parse_spoken_integer(text)
    if n is not None and n > 0:
        return str(n)
    compact = re.sub(r"[\s,]", "", text)
    if re.fullmatch(r"\d+", compact or ""):
        value = int(compact)
        return str(value) if value > 0 else ""
    return ""


def _normalize_create_property_total_value(text: str) -> str:
    """Positive ETH amount only."""
    if _input_indicates_negative_amount(text):
        return ""
    t = _strip_noise(text).lower()
    if re.search(r"\b(million|billion|thousand|lakh|crore)\b", t):
        spoken = _parse_spoken_integer(text)
        if spoken is not None and spoken > 0:
            return str(spoken)
    amt = _parse_decimal_amount(text)
    if amt is None:
        spoken = _parse_spoken_integer(text)
        if spoken is not None and spoken > 0:
            return str(spoken)
        return ""
    try:
        return amt if Decimal(amt) > 0 else ""
    except (InvalidOperation, ValueError, TypeError):
        return ""


def _normalize_create_property_monthly_rent(text: str) -> str:
    """Monthly rent: skip words → 0, otherwise a non-negative ETH number."""
    if create_property_monthly_rent_is_skip(text):
        return "0"
    amt = _parse_decimal_amount(text)
    if amt is None:
        return ""
    try:
        return amt if Decimal(amt) >= 0 else ""
    except (InvalidOperation, ValueError, TypeError):
        return ""


def create_property_monthly_rent_is_skip(value: str) -> bool:
    return (value or "").strip().lower() in {
        "0",
        "skip",
        "none",
        "no",
        "n/a",
        "ok",
        "okay",
    }


def _normalize_create_property_token_symbol(text: str) -> str:
    """Ticker: 2–10 alphanumeric characters (e.g. ETH, GP, OCEAN)."""
    upper = text.upper()
    stop = {
        "A", "AN", "THE", "I", "TO", "FOR", "IS", "IT", "MY", "WE", "AS",
        "AT", "IN", "ON", "OR", "OF", "AND", "WANT", "GIVE", "USE", "TOKEN",
        "SYMBOL", "TICKER", "PLEASE", "YES", "NO", "OK", "SKIP",
    }
    m = re.search(r"\b(?:SYMBOL|TICKER)\s+(?:IS\s+)?([A-Z0-9]{2,10})\b", upper)
    if m and m.group(1) not in stop:
        return m.group(1)
    for sym in re.findall(r"\b([A-Z0-9]{2,10})\b", upper):
        if sym not in stop:
            return sym
    cleaned = re.sub(r"[^A-Z0-9]", "", upper)
    if CREATE_PROPERTY_TOKEN_SYMBOL_MIN_LEN <= len(cleaned) <= CREATE_PROPERTY_TOKEN_SYMBOL_MAX_LEN:
        return cleaned
    return ""


def create_property_token_symbol_is_valid(value: str) -> bool:
    normalized = normalize_create_property_field("token_symbol", str(value or ""))
    return (
        CREATE_PROPERTY_TOKEN_SYMBOL_MIN_LEN
        <= len(normalized)
        <= CREATE_PROPERTY_TOKEN_SYMBOL_MAX_LEN
    )


def create_property_numeric_field_is_valid(field: str, value: str) -> bool:
    """True when a numeric create-property field normalized to an acceptable value."""
    if field not in CREATE_PROPERTY_NUMERIC_FIELDS:
        return True
    raw = str(value or "").strip()
    if not raw:
        return False
    normalized = normalize_create_property_field(field, raw)
    if not normalized:
        return False
    if field == "token_supply":
        try:
            return int(normalized) > 0
        except (TypeError, ValueError):
            return False
    if field == "total_value":
        try:
            return Decimal(normalized) > 0
        except (InvalidOperation, TypeError, ValueError):
            return False
    if field == "monthly_rent_eth":
        try:
            return Decimal(normalized) >= 0
        except (InvalidOperation, TypeError, ValueError):
            return False
    return True


def create_property_invalid_field_message(field: str, rejected_value: str = "") -> str:
    """User-facing prompt when a numeric answer could not be parsed."""
    shown = f'"{_strip_noise(rejected_value)}"' if _strip_noise(rejected_value) else "that answer"
    if field == "total_value":
        return (
            f"{shown} isn't a valid total property value. "
            "Please enter positive values only — a number greater than zero in ETH "
            "(negative amounts are not accepted). For example 10000 or 2500.5."
        )
    if field == "token_supply":
        return (
            f"{shown} isn't a valid token count. "
            "Please enter positive values only — a whole number greater than zero "
            "(negative amounts are not accepted). For example 100000."
        )
    if field == "monthly_rent_eth":
        return (
            f"{shown} isn't a valid monthly rent amount. "
            "Enter a non-negative number in ETH below 100 (for example 0.1 or 12), "
            "or say skip or no for no rent."
        )
    if field == "token_symbol":
        return (
            f"{shown} isn't a valid token symbol. "
            f"Use {CREATE_PROPERTY_TOKEN_SYMBOL_MIN_LEN}–{CREATE_PROPERTY_TOKEN_SYMBOL_MAX_LEN} "
            "letters or numbers only — for example ETH, GP, or OCEAN."
        )
    return "Please enter a valid number."


def sanitize_create_property_numeric_fields(
    accumulated: dict[str, str],
) -> tuple[dict[str, str], str | None]:
    """Remove invalid numeric entries; return the first rejected field key."""
    cleaned = dict(accumulated)
    for field in ("total_value", "token_supply", "monthly_rent_eth"):
        if field not in cleaned:
            continue
        if not create_property_numeric_field_is_valid(field, str(cleaned[field])):
            cleaned.pop(field, None)
            return cleaned, field
    return cleaned, None


def sanitize_create_property_fields(
    accumulated: dict[str, str],
) -> tuple[dict[str, str], str | None]:
    """Drop invalid numeric or token-symbol values; return first rejected field."""
    cleaned, invalid = sanitize_create_property_numeric_fields(accumulated)
    if invalid:
        return cleaned, invalid
    if "token_symbol" in cleaned and not create_property_token_symbol_is_valid(
        str(cleaned["token_symbol"])
    ):
        cleaned.pop("token_symbol", None)
        return cleaned, "token_symbol"
    return cleaned, None


def normalize_create_property_accumulated(accumulated: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in accumulated.items():
        if value in (None, ""):
            continue
        normalized = normalize_create_property_field(key, str(value))
        if not normalized:
            continue
        if key in CREATE_PROPERTY_NUMERIC_FIELDS and not create_property_numeric_field_is_valid(
            key, normalized
        ):
            continue
        if key == "token_symbol" and not create_property_token_symbol_is_valid(normalized):
            continue
        out[key] = normalized
    return out


def assistant_showed_create_property_summary(assistant_text: str) -> bool:
    """True when the assistant presented a create-property confirmation summary."""
    t = _strip_noise(assistant_text).lower()
    if not t:
        return False
    if "here are the property details i have" in t:
        return True
    if "summary of the property details" in t or "summary of the property" in t:
        return True
    if "shall i go ahead" in t and "propert" in t:
        return True
    if "shall i create" in t and "propert" in t:
        return True
    markers = (
        "token symbol:",
        "token supply:",
        "total value:",
        "monthly rent:",
    )
    hits = sum(1 for marker in markers if marker in t)
    return hits >= 2 and ("name:" in t or "location:" in t)


def parse_create_property_fields_from_summary(assistant_text: str) -> dict[str, str]:
    """Recover field values from canonical or LLM-paraphrased confirmation summaries."""
    text = assistant_text or ""
    if not text.strip():
        return {}

    patterns: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("name", re.compile(r"(?im)(?:^|\n)\s*[-*]?\s*(?:name|property name)\s*:\s*(.+?)\s*(?:\n|$)")),
        ("location", re.compile(r"(?im)(?:^|\n)\s*[-*]?\s*location\s*:\s*(.+?)\s*(?:\n|$)")),
        (
            "total_value",
            re.compile(
                r"(?im)(?:^|\n)\s*[-*]?\s*(?:total value|total property value)"
                r"(?:\s*\(eth\))?\s*:\s*([\d.,]+)"
            ),
        ),
        (
            "token_supply",
            re.compile(
                r"(?im)(?:^|\n)\s*[-*]?\s*(?:token supply|ownership tokens?)\s*:\s*([\d.,]+)"
            ),
        ),
        (
            "token_symbol",
            re.compile(
                r"(?im)(?:^|\n)\s*[-*]?\s*(?:token symbol|ticker(?:\s+symbol)?)\s*:\s*([A-Za-z0-9]{2,10})"
            ),
        ),
        (
            "monthly_rent_eth",
            re.compile(
                r"(?im)(?:^|\n)\s*[-*]?\s*monthly rent(?:\s*\(eth\))?\s*:\s*([\d.,]+)"
            ),
        ),
    )

    fields: dict[str, str] = {}
    for key, pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue
        raw = match.group(1).strip()
        if key == "total_value" and "eth" in raw.lower():
            raw = re.sub(r"(?i)\s*eth\s*$", "", raw).strip()
        normalized = normalize_create_property_field(key, raw)
        if normalized:
            fields[key] = normalized
    return fields


CREATE_PROPERTY_MAX_MONTHLY_RENT_ETH = Decimal("100")


def _suggest_token_symbol_from_property_name(property_name: str) -> str:
    """Short uppercase hint from the property name (e.g. Sunset Villas → SV)."""
    parts = re.findall(r"[A-Za-z0-9]+", (property_name or "").strip())
    if len(parts) >= 2:
        return "".join(p[0] for p in parts[:4]).upper()[:8]
    if parts:
        return parts[0][:6].upper()
    return ""


def create_property_token_symbol_prompt(property_name: str = "") -> str:
    """Ask for token ticker with examples so admins understand the field."""
    suggested = _suggest_token_symbol_from_property_name(property_name)
    if suggested and len(suggested) >= 2:
        examples = f"{suggested}, OCEAN, or VILLA"
        from_name = f" ({suggested} is a short code from the property name)"
    else:
        examples = "OCEAN, VILLA, or ETH"
        from_name = ""
    return (
        "What ticker symbol do you want for the token? "
        f"A ticker is a short trading-style code (2–10 letters) for this property's "
        f"token on your dashboard — for example {examples}{from_name}. "
        "You can use a well-known style like ETH or USD, or a custom code based on "
        "the property name."
    )


def create_property_field_collection_speak(
    field: str, filled: dict[str, str] | None = None
) -> str | None:
    """Authoritative question text for the next create-property field (when set)."""
    prompts: dict[str, str] = {
        "name": "What's the name of the property?",
        "location": "Where is it located?",
        "total_value": (
            "What's the total property value in ETH? "
            "Enter positive values only (greater than zero) — digits or spoken amounts like "
            "ten million or one hundred thousand (for example 10000 or 12345678)."
        ),
        "token_supply": (
            "How many ownership tokens should we mint? "
            "Enter positive values only (greater than zero) — digits or spoken amounts like "
            "five million (for example 100000 or 5000000)."
        ),
    }
    if field == "token_symbol":
        return create_property_token_symbol_prompt(str((filled or {}).get("name") or ""))
    if field == "monthly_rent_eth":
        return create_property_monthly_rent_collection_prompt()
    return prompts.get(field)


def create_property_monthly_rent_collection_prompt() -> str:
    """Shown before collecting optional monthly rent during create-property."""
    return (
        "Monthly rent must be less than 100 ETH (on-chain limit). "
        "What's the monthly rent in ETH? Say 0 or skip if you don't want rent yet."
    )


def create_property_monthly_rent_over_limit(value: str) -> bool:
    """True when rent exceeds the create-property chatbot / on-chain cap."""
    if create_property_monthly_rent_is_skip(value):
        return False
    try:
        return Decimal(str(value).strip()) >= CREATE_PROPERTY_MAX_MONTHLY_RENT_ETH
    except (InvalidOperation, ValueError, TypeError):
        return False


def create_property_monthly_rent_rejection_message(value: str) -> str:
    return (
        f"{value} ETH is too high — monthly rent must be less than 100 ETH. "
        f"{create_property_monthly_rent_collection_prompt()}"
    )


_CREATE_PROPERTY_CONFIRMATION_ORDER: tuple[tuple[str, str], ...] = (
    ("name", "Name"),
    ("location", "Location"),
    ("total_value", "Total value (ETH)"),
    ("token_supply", "Token supply"),
    ("token_symbol", "Token symbol"),
    ("monthly_rent_eth", "Monthly rent (ETH)"),
)


def create_property_confirmation_footer() -> str:
    """Actions the property owner can take after the create-property summary."""
    return (
        "Reply Yes to create and deploy the listing.\n"
        "To edit, say which field to change (for example, \"edit location to Dubai\" "
        "or \"change token symbol to OCN\").\n"
        "To delete all of these details and start over, say Delete or No."
    )


def format_create_property_confirmation_summary(filled: dict[str, str]) -> str:
    """Human-readable summary shown before the admin confirms create-property submit."""
    lines: list[str] = []
    for key, label in _CREATE_PROPERTY_CONFIRMATION_ORDER:
        raw = filled.get(key)
        if key == "monthly_rent_eth":
            display = str(raw).strip() if raw not in (None, "") else "0"
        elif raw in (None, ""):
            continue
        else:
            display = str(raw).strip()
        lines.append(f"- {label}: {display}")
    body = "\n".join(lines)
    return (
        "Here are the property details I have:\n"
        f"{body}\n\n"
        f"{create_property_confirmation_footer()}"
    )


_CREATE_PROPERTY_SUBMIT_RE = re.compile(
    r"(?:"
    r"\b(?:please\s+)?(?:go\s+ahead\s+and\s+)?create\s+(?:this\s+)?(?:property|listing)\b"
    r"|\b(?:ok|okay)[,.]?\s*(?:please\s+)?create\b"
    r"|\b(?:submit|deploy)\s+(?:this\s+)?(?:property|listing)\b"
    r"|\bcreate\s+and\s+deploy\b"
    r"|\b(?:please\s+)?create\s+it\b"
    r"|\blet'?s\s+create\b"
    r")",
    re.IGNORECASE,
)


def parse_create_property_submit_intent(text: str) -> bool | None:
    """True when the user confirms create-property after the summary (voice-friendly).

    Only treats explicit create/submit phrases as Yes — not \"create a new property\"
  at workflow start (callers must gate on ``awaiting_create_confirmation``).
    """
    yn = parse_yes_no_confirmation(text)
    if yn is not None:
        return yn
    t = _strip_noise(text).lower()
    if not t:
        return None
    if _CREATE_PROPERTY_SUBMIT_RE.search(t):
        return True
    return None


_EDIT_RENT_RE = re.compile(
    r"(?:"
    r"(?:edit|set|change|update)\s+(?:the\s+)?(?:monthly\s+)?rent\s+(?:to\s+)?([\d.,]+(?:\s*(?:eth))?)"
    r"|(?:also\s+)?(?:set\s+)?rent\s+(?:to\s+)?([\d.,]+)"
    r"|monthly\s+rent\s+(?:to\s+)?([\d.,]+)"
    r")",
    re.IGNORECASE,
)
_EDIT_LOCATION_RE = re.compile(
    r"(?:location|located)\s+(?:as|to|in)\s+(.+?)(?:\.|$)",
    re.IGNORECASE,
)
_EDIT_NAME_RE = re.compile(
    r"(?:name|rename)\s+(?:to|as)\s+(.+?)(?:\.|$)",
    re.IGNORECASE,
)


def parse_edit_property_fields_from_utterance(text: str) -> dict[str, str]:
    """Extract edit-property field updates from a follow-up line in the same chat."""
    raw = (text or "").strip()
    if not raw:
        return {}
    fields: dict[str, str] = {}
    rent_match = _EDIT_RENT_RE.search(raw)
    if rent_match:
        token = next((g for g in rent_match.groups() if g), "")
        rent = normalize_create_property_field("monthly_rent_eth", token)
        if rent:
            fields["monthly_rent_eth"] = rent
    loc_match = _EDIT_LOCATION_RE.search(raw)
    if loc_match:
        loc = normalize_create_property_field("location", loc_match.group(1).strip())
        if loc:
            fields["location"] = loc
    name_match = _EDIT_NAME_RE.search(raw)
    if name_match:
        name = normalize_create_property_field("name", name_match.group(1).strip())
        if name:
            fields["name"] = name
    return fields


def utterance_is_edit_property_field_update(text: str) -> bool:
    """True when the user is updating a field on an open edit, not starting a new edit."""
    if parse_edit_property_fields_from_utterance(text):
        return True
    t = _strip_noise(text).lower()
    if re.search(
        r"\b(?:edit|change|update)\s+(?:the\s+)?(?:monthly\s+)?rent\b",
        t,
    ):
        return True
    if re.search(r"\b(?:edit|change|update)\s+(?:the\s+)?(?:location|name)\b", t):
        return True
    return False


def utterance_opens_new_edit_property_flow(text: str) -> bool:
    """True when the user is starting a new edit, not a field-only follow-up."""
    if utterance_is_edit_property_field_update(text):
        return False
    t = _strip_noise(text).lower()
    if re.search(r"\b(edit|update|change)\b", t) and re.search(
        r"\b(property|listing|name|location|rent)\b", t
    ):
        return True
    if re.match(r"^edit\s+\S", t):
        return True
    return False


def parse_yes_no_confirmation(text: str) -> bool | None:
    """Parse explicit yes/no answers (e.g. skip accidental yes/no as field values)."""
    t = _strip_noise(text).lower().strip("'\".,!? ")
    if not t:
        return None
    if t in {
        "yes",
        "y",
        "yeah",
        "yep",
        "sure",
        "ok",
        "okay",
        "proceed",
        "go ahead",
        "continue",
        "confirm",
        "do it",
    }:
        return True
    if t in {
        "no",
        "n",
        "nope",
        "cancel",
        "stop",
        "abort",
        "don't",
        "do not",
        "dont",
        "delete",
    }:
        return False
    if re.search(r"\b(yes|proceed|go ahead|continue)\b", t):
        return True
    if re.search(r"\b(no|cancel|abort|stop)\b", t):
        return False
    if re.search(r"\bdelete\b", t):
        return False
    return None


_DELETE_PROPERTY_OPEN_RE = re.compile(
    r"\b(?:delete|remove|archive)\b(?:\s+\w+){0,4}\s*(?:property|listing)\b",
    re.IGNORECASE,
)


def utterance_opens_delete_property_flow(text: str) -> bool:
    """True when the user is starting a delete-property workflow."""
    t = _strip_noise(text).lower()
    if not t:
        return False
    if _DELETE_PROPERTY_OPEN_RE.search(t):
        return True
    if re.search(r"\b(?:delete|remove|archive)\s+\S", t):
        return True
    return False


def parse_delete_property_id_from_utterance(text: str) -> int | None:
    """Extract a numeric property id from a delete-identification utterance."""
    raw = _strip_noise(text).strip()
    if not raw:
        return None
    if re.fullmatch(r"\d+", raw):
        return int(raw)
    match = re.fullmatch(
        r"(?:property\s+)?(?:id\s*)?#?(\d+)",
        raw,
        flags=re.IGNORECASE,
    )
    if match:
        return int(match.group(1))
    match = re.search(r"\b(?:property|id)\s*#?(\d+)\b", raw, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def parse_delete_property_hint_from_utterance(text: str) -> str:
    """Property name or id hint after delete/remove/archive phrasing."""
    raw = _strip_noise(text).strip()
    if not raw:
        return ""
    pid = parse_delete_property_id_from_utterance(raw)
    if pid is not None and re.fullmatch(
        r"(?:property\s+)?(?:id\s*)?#?\d+",
        raw,
        flags=re.IGNORECASE,
    ):
        return str(pid)
    stripped = re.sub(
        r"^(?:please\s+)?(?:i\s+want\s+to\s+)?"
        r"(?:delete|remove|archive)\s+(?:the\s+)?(?:property\s+)?",
        "",
        raw,
        flags=re.IGNORECASE,
    ).strip()
    stripped = re.sub(r"\s+(?:property|listing)\.?$", "", stripped, flags=re.IGNORECASE).strip(
        "'\" "
    )
    if stripped:
        pid = parse_delete_property_id_from_utterance(stripped)
        if pid is not None and re.fullmatch(
            r"(?:property\s+)?(?:id\s*)?#?\d+",
            stripped,
            flags=re.IGNORECASE,
        ):
            return str(pid)
        return stripped
    return raw


def delete_property_identification_prompt() -> str:
    return (
        "Which property should I remove? Please give the exact property name "
        "or property ID (for example, Skyzone or 7)."
    )


def delete_property_confirmation_message(
    name: str,
    property_id: int,
    *,
    will_archive: bool,
) -> str:
    action = "archive" if will_archive else "permanently delete"
    label = name.strip() or f"Property {property_id}"
    return (
        f"You asked to remove {label!r} (property #{property_id}). "
        f"This will {action} the listing. Reply Yes to confirm or No to cancel."
    )


def parse_delete_property_confirm_intent(text: str) -> bool | None:
    """Yes/no for delete confirmation (delete/remove here means proceed, not cancel)."""
    raw = _strip_noise(text)
    t = raw.lower().strip("'\".,!? ")
    if not t:
        return None
    if re.search(r"\b(no|nope|cancel|stop|abort|don'?t|do not)\b", t):
        return False
    if re.search(
        r"\b(?:yes|yeah|yep|sure|ok|okay|confirm|proceed|go ahead|do it)\b",
        t,
    ):
        return True
    if re.search(r"\b(?:delete|remove)\s+(?:it|this|the property|that property)\b", t):
        return True
    if t in {"delete", "remove", "yes delete", "yes remove"}:
        return True
    return None
