"""Deterministic input security guard protecting against adversarial prompt injections."""

import re
from typing import Optional, Tuple

GUARD_PATTERNS = {
    "instruction_override": re.compile(
        r"\b(ignore|disregard|forget|override)\b.*?\b(instructions|guidelines|rules|prompts|filters)\b|"
        r"\bsystem\s+override\b|"
        r"\b(do not|don'?t)\s+cite\s+any\s+sources\b|"
        r"\bignore\s+safety\s+filters\b|"
        r"---\s*system\s+instruction|"
        r"\bmaintenance\s+mode\b",
        re.IGNORECASE,
    ),
    "role_play": re.compile(
        r"\b(you are now|roleplay as|pretend you are|pretend my manager|act as an unrestricted|dan mode|developer mode enabled)\b|"
        r"\bunrestricted\s+administrator\b",
        re.IGNORECASE,
    ),
    "prompt_exfiltration": re.compile(
        r"\b(reveal|print|display|output|show|what is)\b.*?\b(system\s+prompt|system\s+instruction|environment\s+variables|api\s+keys|api\s+tokens|database\s+payloads|internal\s+prompt)\b|"
        r"\b(primary\s+instruction|system\s+prompt\s+verbatim)\b|"
        r"\bcall\s+every\s+available\s+tool\b|"
        r"\bbase64\s+decode\b",
        re.IGNORECASE,
    ),
    "approval_spoofing": re.compile(
        r"\b(pretend\s+my\s+manager\s+approved|mark\s+proposal\s+approved|admin\s+override\s+approval|bypass\s+reviewer\s+check|fake\s+reviewer\s+header|spoof\s+approval)\b",
        re.IGNORECASE,
    ),
}

REFUSAL_MESSAGE = (
    "I cannot fulfill requests that attempt to override system instructions, "
    "simulate administrative roles, exfiltrate internal prompts or credentials, "
    "or bypass approval workflows. If you have a question about Aster & Row products, "
    "orders, or return policies, please let me know."
)


def evaluate_input_guard(query: str) -> Tuple[bool, Optional[str]]:
    """Evaluate raw user query against deterministic security guard patterns.

    Returns:
        (is_violation, matched_category)
    """
    cleaned = query.strip()
    for category, pattern in GUARD_PATTERNS.items():
        if pattern.search(cleaned):
            return True, category
    return False, None
