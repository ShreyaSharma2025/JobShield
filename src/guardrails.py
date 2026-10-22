"""Input and evidence checks that run before results are stored or shown."""
from .schemas import Evidence, ParsedPosting

MAX_POSTING_CHARACTERS = 30_000
MIN_POSTING_CHARACTERS = 30


def validate_posting_text(text: str) -> str:
    clean_text = text.strip()
    if len(clean_text) < MIN_POSTING_CHARACTERS:
        raise ValueError(f"Paste a fuller job description (at least {MIN_POSTING_CHARACTERS} characters).")
    if len(clean_text) > MAX_POSTING_CHARACTERS:
        raise ValueError(f"The job description is too long. The limit is {MAX_POSTING_CHARACTERS:,} characters.")
    if "\x00" in clean_text:
        raise ValueError("The job description contains an invalid character. Please paste it again as plain text.")
    return clean_text


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
