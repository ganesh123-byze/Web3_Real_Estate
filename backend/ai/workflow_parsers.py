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


def _parse_spoken_integer(text: str) -> int | None:
    """Best-effort integer from phrases like 'one lakh tokens' or '10000'."""
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
    if re.search(r"\bthousand\b", t):
        m = re.search(r"([\d.,]+)\s*thousand", t)
        if m:
            try:
                return int(float(m.group(1).replace(",", "")) * 1_000)
            except (TypeError, ValueError):
                pass
        if re.search(r"\bone\s+thousand\b", t):
            return 1_000

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

    for word, val in _WORD_NUMBERS.items():
        if re.search(rf"\b{word}\b", t):
            return val
    return None


def _parse_decimal_amount(text: str) -> str | None:
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
        ),
        "monthly_rent_eth": (
            "monthly rent",
            "rent in eth",
            "open the rent",
            "no rent yet",
        ),
    }
    return any(phrase in t for phrase in prompts.get(field, ()))


def normalize_create_property_field(field: str, raw: str) -> str:
    """Map a single user answer onto a form-ready string for CREATE_PROPERTY."""
    text = _strip_noise(raw)
    if not text:
        return text

    if field == "token_supply":
        n = _parse_spoken_integer(text)
        return str(n) if n is not None else re.sub(r"[^\d]", "", text) or text

    if field == "token_symbol":
        upper = text.upper()
        stop = {
            "A", "AN", "THE", "I", "TO", "FOR", "IS", "IT", "MY", "WE", "AS",
            "AT", "IN", "ON", "OR", "OF", "AND", "WANT", "GIVE", "USE", "TOKEN",
            "SYMBOL", "TICKER", "PLEASE",
        }
        m = re.search(
            r"\b(?:SYMBOL|TICKER)\s+(?:IS\s+)?([A-Z]{2,10})\b",
            upper,
        )
        if m and m.group(1) not in stop:
            return m.group(1)
        for sym in re.findall(r"\b([A-Z]{2,10})\b", upper):
            if sym not in stop:
                return sym
        cleaned = re.sub(r"[^A-Z0-9]", "", upper)
        return cleaned[:10] if cleaned else text

    if field in ("total_value", "monthly_rent_eth"):
        amt = _parse_decimal_amount(text)
        return amt if amt is not None else text

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


def normalize_create_property_accumulated(accumulated: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in accumulated.items():
        if value in (None, ""):
            continue
        out[key] = normalize_create_property_field(key, str(value))
    return out


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
    if field == "token_symbol":
        return create_property_token_symbol_prompt(
            str((filled or {}).get("name") or "")
        )
    return None


def create_property_monthly_rent_collection_prompt() -> str:
    """Shown before collecting optional monthly rent during create-property."""
    return (
        "Monthly rent must be less than 100 ETH (on-chain limit). "
        "What's the monthly rent in ETH? Say 0 or skip if you don't want rent yet."
    )


def create_property_monthly_rent_is_skip(value: str) -> bool:
    return (value or "").strip().lower() in {"0", "skip", "none", "no", "n/a"}


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
    r"(?:set|change|update)\s+(?:the\s+)?(?:monthly\s+)?rent\s+(?:to\s+)?([\d.,]+(?:\s*(?:eth))?)"
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


def utterance_opens_new_edit_property_flow(text: str) -> bool:
    """True when the user is starting a new edit, not a field-only follow-up."""
    if parse_edit_property_fields_from_utterance(text):
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
