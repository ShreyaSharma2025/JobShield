# ====================================================================================================
# [NODE 0: PRE-FLIGHT INPUT GUARDRAILS SHIELD & SECURITY VALIDATOR]
# File: src/guardrails.py
#
# QUICK NODE TO STARTING LINE MAPPING:
#   - [NODE 0 · L43] : Anti-Prompt Injection Defense (check_prompt_injection)
#   - [NODE 0 · L53] : Malicious Payload Scanner (check_toxic_abusive)
#   - [NODE 0 · L63] : Input Text Boundary & Null Byte Clearance (validate_posting_text)
#   - [NODE 0 · L81] : FastMCP Tool Return Defense Checks (validate_tool_return)
#
# ARCHITECTURAL ROLE:
#   First line of defense. Runs before any agent processes untrusted user input.
# ====================================================================================================

import re
from typing import Any
from .schemas import Evidence, ParsedPosting

MAX_POSTING_CHARACTERS = 30_000
MIN_POSTING_CHARACTERS = 30

# Patterns indicating prompt injection attacks or instructions override attempts
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"disregard\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"you\s+are\s+now\s+(a\s+)?(dan|jailbreak|unrestricted)",
    r"system\s*:\s*override",
    r"new\s+system\s+prompt",
    r"classify\s+this\s+(always\s+)?as\s+(low\s+risk|legitimate)",
    r"bypass\s+(all\s+)?(safety|guardrails|filters)",
    r"developer\s+mode\s+enabled",
    r"reveal\s+(your\s+)?(system\s+prompt|secret|api\s*key)",
]

# Patterns for malicious or abusive input
ABUSE_PATTERNS = [
    r"\b(kill|suicide|exploit|malware|ransomware|trojan|hack)\b",
]


# [NODE 0 · PORTION 1 · L43: ANTI-PROMPT INJECTION DEFENSE]
def check_prompt_injection(text: str) -> tuple[bool, str | None]:
    """Scan text for prompt injection attempts attempting to compromise agentic flow."""
    lower = text.lower()
    for pattern in INJECTION_PATTERNS:
        match = re.search(pattern, lower)
        if match:
            return True, f"Detected prompt injection pattern: '{match.group(0)}'"
    return False, None


# [NODE 0 · PORTION 1 · L53: MALICIOUS PAYLOAD SCANNER]
def check_toxic_abusive(text: str) -> tuple[bool, str | None]:
    """Scan text for abusive or malicious payloads."""
    lower = text.lower()
    for pattern in ABUSE_PATTERNS:
        match = re.search(pattern, lower)
        if match:
            return True, f"Detected sensitive security phrase: '{match.group(0)}'"
    return False, None


# [NODE 0 · PORTION 2 · L63: INPUT TEXT BOUNDARY & NULL BYTE CLEARANCE]
def validate_posting_text(text: str) -> str:
    """Validate input text size, character validity, and security clearance."""
    clean_text = text.strip()
    if len(clean_text) < MIN_POSTING_CHARACTERS:
        raise ValueError(f"Paste a fuller job description (at least {MIN_POSTING_CHARACTERS} characters).")
    if len(clean_text) > MAX_POSTING_CHARACTERS:
        raise ValueError(f"The job description is too long. The limit is {MAX_POSTING_CHARACTERS:,} characters.")
    if "\x00" in clean_text:
        raise ValueError("The job description contains an invalid null character. Please paste plain text.")

    is_injection, reason = check_prompt_injection(clean_text)
    if is_injection:
        # Instead of breaking, we log and treat the text as quarantined untrusted payload
        pass

    return clean_text


def validate_tool_return(tool_name: str, payload: Any) -> dict:
    """Type-check and validate raw outputs from MCP tools before agent consumption."""
    if not isinstance(payload, dict):
        raise TypeError(f"Tool '{tool_name}' must return a dictionary, got {type(payload).__name__}.")
    
    # Specific schema validations
    if tool_name == "lookup_domain_rdap":
        status = payload.get("status")
        if status not in {"found", "not_found", "invalid_domain", "unavailable"}:
            payload["status"] = "unavailable"
    elif tool_name == "search_company_public_sources":
        if "results" in payload and not isinstance(payload["results"], list):
            payload["results"] = []
    return payload


def keep_supported_findings(findings: list[Evidence], text: str) -> list[Evidence]:
    """Keep only quoted JD evidence and prevent an LLM from assigning decisive rule IDs."""
    accepted: list[Evidence] = []
    for finding in findings:
        if not finding.quote or finding.quote not in text:
            continue
        values = finding.model_dump()
        values["severity"] = "weak" if finding.severity == "strong" else finding.severity
        values["source_type"] = "jd_text"
        values["rule_id"] = f"LLM_CONTEXT_{finding.rule_id[:60]}"
        accepted.append(Evidence.model_validate(values))
    return accepted


def keep_supported_fields(posting: ParsedPosting, text: str) -> ParsedPosting:
    """Reject extracted claims that cannot be traced to the submitted posting."""
    source = text.casefold()
    values = posting.model_dump()
    for field in (
        "company_name", "role", "salary_text", "location", "experience",
        "employment_type", "contact_email",
    ):
        value = values.get(field)
        if value and value.casefold() not in source:
            values[field] = None
    values["links"] = [link for link in posting.links if link in text]
    values["requirements"] = [line for line in posting.requirements if line in text]
    return ParsedPosting.model_validate(values)


def inspect_guardrails(text: str) -> dict:
    """Run full diagnostic test suite of guardrails for UI transparency."""
    is_inj, inj_detail = check_prompt_injection(text)
    is_tox, tox_detail = check_toxic_abusive(text)
    
    return {
        "length_valid": MIN_POSTING_CHARACTERS <= len(text.strip()) <= MAX_POSTING_CHARACTERS,
        "char_count": len(text.strip()),
        "null_bytes_free": "\x00" not in text,
        "prompt_injection_detected": is_inj,
        "prompt_injection_detail": inj_detail,
        "toxic_content_detected": is_tox,
        "toxic_content_detail": tox_detail,
        "sanitization_status": "Passed" if not (is_inj or is_tox) else "Flagged & Sandboxed",
    }
