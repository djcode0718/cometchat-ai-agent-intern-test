"""Deterministic tokenization for lexical search and BM25 indexing."""

import re
from typing import List

# Matches words, hyphenated compounds, alphanumeric identifiers, and monetary amounts ($75)
TOKEN_PATTERN = re.compile(r"\b[a-z0-9]+(?:[-_][a-z0-9]+)*\b|\$[0-9]+(?:\.[0-9]+)?", re.IGNORECASE)


def tokenize_text(text: str) -> List[str]:
    """Tokenize text into lowercased normalized tokens.

    Preserves alphanumeric codes (e.g. RET-2026-01, ORD-1007), hyphenated
    terms (e.g. final-sale, dishwasher-safe), and currency amounts ($75).
    For hyphenated terms, also emits sub-word tokens to ensure both exact compound
    and separated queries match.
    """
    if not text:
        return []

    raw_tokens = TOKEN_PATTERN.findall(text.lower())
    tokens: List[str] = []

    for token in raw_tokens:
        tokens.append(token)
        # If token contains hyphen or underscore, also add individual parts
        if "-" in token or "_" in token:
            subparts = re.split(r"[-_]", token)
            for part in subparts:
                if part and part != token:
                    tokens.append(part)

    return tokens
