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


# --- External-Content Choke Point ---

def sanitize_external_content(
    text: str,
    *,
    redact: bool = True,
    max_length: int = 5000,
) -> tuple[str, dict[str, Any]]:
    """Make untrusted external content safe *before* it reaches an LLM prompt.

    This is the single choke point every externally-sourced string (Slack
    messages via RTS, hazard-feed text) must pass through before it is stored as
    evidence or placed in a model prompt. It:

    1. Detects prompt-injection patterns and, if found, prepends an explicit
       neutralization marker so the downstream model reads the span as quoted,
       flagged data rather than as instructions.
    2. Redacts PII (email/phone/SSN/card) so it never reaches the model or logs.
    3. Strips control characters and truncates.

    Returns ``(safe_text, report)`` where ``report`` records what was found, so
    callers can log/surface it. Redaction and neutralization are applied to the
    returned text itself — not merely to a log line — so the protection is on the
    model-bound payload, not cosmetic.
    """
    is_injection, pattern = detect_prompt_injection(text)
    pii = detect_pii(text)
    report: dict[str, Any] = {
        "injection": is_injection,
        "injection_pattern": pattern,
        "pii_types": sorted({f["type"] for f in pii}),
        "pii_count": len(pii),
    }

    safe = sanitize_user_input(text, max_length=max_length)
    if redact:
        safe = redact_pii(safe)
    if is_injection:
        safe = "[FLAGGED: possible prompt-injection neutralized] " + safe

    return safe, report


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
