"""Beacon Command — Security Utilities.

Prompt injection defense, content security, and redaction.
"""

from __future__ import annotations

import re
from typing import Any

from beacon.logging import get_logger

logger = get_logger(__name__)


# --- Prompt Injection Defense ---

_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(all\s+)?previous",
    r"forget\s+(all\s+)?previous",
    r"you\s+are\s+now\s+a",
    r"pretend\s+you\s+are",
    r"act\s+as\s+if",
    r"system\s*:\s*",
    r"\[INST\]",
    r"<\|im_start\|>",
    r"<\|system\|>",
    r"USER:\s*override",
]

_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


def detect_prompt_injection(text: str) -> tuple[bool, str]:
    """Check text for potential prompt injection patterns.

    Args:
        text: Text to check.

    Returns:
        Tuple of (is_suspicious, matched_pattern).
    """
    match = _INJECTION_RE.search(text)
    if match:
        return True, match.group()
    return False, ""


def sanitize_user_input(text: str, max_length: int = 10000) -> str:
    """Sanitize user input for safe inclusion in prompts.

    Args:
        text: Raw user input.
        max_length: Maximum allowed length.

    Returns:
        Sanitized text.
    """
    # Truncate
    text = text[:max_length]

    # Remove control characters except newlines and tabs
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    return text


# --- Content Security ---

_PII_PATTERNS = {
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    "phone": r"\b(?:\+?1[-.]?)?\(?[0-9]{3}\)?[-. ]?[0-9]{3}[-. ]?[0-9]{4}\b",
    "ssn": r"\b\d{3}[-]?\d{2}[-]?\d{4}\b",
    "credit_card": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
}


def detect_pii(text: str) -> list[dict[str, str]]:
    """Detect potential PII in text.

    Returns list of {type, match} dicts.
    """
    findings = []
    for pii_type, pattern in _PII_PATTERNS.items():
        for match in re.finditer(pattern, text):
            findings.append({"type": pii_type, "match": match.group()})
    return findings


def redact_pii(text: str) -> str:
    """Redact detected PII from text."""
    for pii_type, pattern in _PII_PATTERNS.items():
        text = re.sub(pattern, f"[REDACTED_{pii_type.upper()}]", text)
    return text


# --- Access Control ---

def check_authority_level(
    required: str,
    granted: str,
) -> bool:
    """Check if the granted authority level meets the requirement.

    Authority levels are ordered:
    L0_OBSERVE < L1_RECOMMEND < L2_PREPARE < L3_EXECUTE_REVERSIBLE < L4_EXECUTE_OPERATIONAL

    L5_PROHIBITED is always denied.
    """
    levels = {
        "L0_OBSERVE": 0,
        "L1_RECOMMEND": 1,
        "L2_PREPARE": 2,
        "L3_EXECUTE_REVERSIBLE": 3,
        "L4_EXECUTE_OPERATIONAL": 4,
        "L5_PROHIBITED": 99,
    }

    required_level = levels.get(required, 99)
    granted_level = levels.get(granted, 0)

    if required_level == 99:
        return False  # L5_PROHIBITED is always denied

    return granted_level >= required_level
