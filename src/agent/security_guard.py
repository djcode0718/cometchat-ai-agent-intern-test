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
        r"\bmaintenance\s+mode\b|"
        r"\b(sudo\s+mode|emergency\s+protocol|unrestricted\s+ai|new\s+directive|core\s+persona|devbot|dan\s+mode|jailbreak)\b",
        re.IGNORECASE,
    ),
    "role_play": re.compile(
        r"\b(you are now|roleplay as|pretend you are|pretend my manager|act as an unrestricted|dan mode|developer mode)\b|"
        r"\bunrestricted\s+administrator\b",
        re.IGNORECASE,
    ),
    "prompt_exfiltration": re.compile(
        r"\b(reveal|print|display|output|show|what is|give me|echo|tell me)\b.*?(system\s+prompt|system\s+instruction|environment\s+variables|api\s+keys?|api\s+tokens?|database\s+payloads|internal\s+prompt|reviewer_keys|\.env|connection\s+string|admin\s+password|bearer\s+tokens?|authorization\s+header)|"
        r"\b(primary\s+instruction|system\s+prompt\s+verbatim)\b|"
        r"\b(reviewer_keys|sentry_dsn|webhook\s+secret|ssh\s+keys|authorization\s+header)\b|"
        r"\.env|"
        r"\bcall\s+every\s+available\s+tool\b|"
        r"\bbase64\s+decode\b",
        re.IGNORECASE,
    ),
    "pii_exfiltration": re.compile(
        r"\b(list\s+all\s+customers?|dump\s+all\s+customers?|credit\s+card\s+numbers?|customer\s+transaction\s+logs|export\s+user\s+profile|fraud\s+risk\s+scores?|internal\s+warehouse\s+notes?|billing\s+details\s+for\s+order|customer\s+email\s+addresses?)\b|"
        r"\blist\s+of\s+all\s+customer\b",
        re.IGNORECASE,
    ),
    "sql_injection": re.compile(
        r"\b(drop\s+table|truncate\s+table|union\s+select|insert\s+into|update\s+orders\s+set|or\s+['\"]?1['\"]?\s*=\s*['\"]?1)\b|;\s*(drop|select|update|delete|insert|truncate)\b|--\s*$",
        re.IGNORECASE,
    ),
    "approval_spoofing": re.compile(
        r"\b(pretend\s+my\s+manager\s+approved|mark\s+proposal\s+approved|admin\s+override\s+approval|bypass\s+reviewer\s+check|fake\s+reviewer\s+header|spoof\s+approval)\b|"
        r"\{\s*\"action\"\s*:\s*\"approve\"|"
        r"/reviewer/proposals/|"
        r"x-reviewer-key|"
        r"\b(call\s+approval_service|auto-approve\s+proposal|force\s+execute\s+proposal|override\s+reviewer)\b",
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
