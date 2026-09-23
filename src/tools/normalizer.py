"""Order ID normalization and candidate extraction."""

import re
from typing import Optional

# Matches canonical or case-insensitive order ID: ORD-1001, ord-1001, etc.
ORDER_ID_PATTERN = re.compile(r"\bORD-(\d{4,})\b", re.IGNORECASE)


def extract_candidate_order_id(text: Optional[str]) -> Optional[str]:
    """Extract and normalize canonical order ID (ORD-XXXX) from arbitrary text.

    Returns normalized uppercase string (e.g. 'ORD-1001') or None if no valid ID found.
    Arbitrary numbers without the ORD prefix are strictly ignored.
    """
    if not text:
        return None

    match = ORDER_ID_PATTERN.search(text)
    if not match:
        return None

    digits = match.group(1)
    return f"ORD-{digits}"


def normalize_order_id(raw_input: Optional[str]) -> Optional[str]:
    """Normalize a candidate order ID string.

    Tolerates lowercase characters, quotes, whitespace, and light surrounding punctuation.
    Returns canonical 'ORD-XXXX' format or None if invalid.
    """
    if not raw_input:
        return None

    cleaned = raw_input.strip().strip("'\"").strip(".,;:!?")
    return extract_candidate_order_id(cleaned)
