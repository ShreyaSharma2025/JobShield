"""Extract common job-posting fields without guessing missing information."""
import re

from .schemas import ParsedPosting

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
URL_RE = re.compile(r"https?://[^\s)\]>]+", re.I)
SALARY_RE = re.compile(
    r"(?:₹|INR\s?|Rs\.?\s?|\$|USD\s?|CTC\s*[:\-]?\s*)"
    r"[\d,]+(?:\s*(?:-|–|to)\s*(?:₹|INR\s?|Rs\.?\s?|\$|USD\s?)?[\d,]+)?"
    r"(?:\s*(?:/|per\s+)(?:month|year|annum|hour|hr|day)"
    r"|(?:\s+(?:LPA|lpa|lakhs?|lacs?|crore|k|K)))?"
    r"|[\d,]+\s*(?:LPA|lpa|lakhs?\s*(?:per\s+annum)?)",
    re.I,
)
EXPERIENCE_RE = re.compile(
    r"(?:(?:min\s*[-–]\s*max\s*)?experience\s*[:\-]?\s*)?"
    r"(\d+(?:\.\d+)?\s*(?:-|–|to)\s*\d+(?:\.\d+)?\s*years?"
    r"|\d+(?:\.\d+)?\+?\s*years?"
    r"|fresher|freshers|entry[- ]level"
    r"|0\s*(?:-|–|to)\s*\d+\s*years?)",
    re.I,
)


def _label_value(text: str, labels: str) -> str | None:
    match = re.search(rf"(?:^|\n)\s*(?:{labels})\s*[:\-]\s*([^\n]+)", text, re.I)
    return match.group(1).strip(" \t.,;|") if match else None


def _company_name(text: str) -> str | None:
    # 1. Explicit labeled fields (strongest signal)
    labeled = _label_value(text, r"company(?:\s+name)?|organization|employer|hired?\s*by")
    if labeled and len(labeled) > 1:
        # Clean common noise from labeled values
        cleaned = re.sub(r"^(the|a|an)\s+", "", labeled, flags=re.I).strip()
        if cleaned and cleaned.lower() not in {"us", "our company", "the company", "confidential", "n/a", "na"}:
            return cleaned

    # 2. "About <CompanyName>" header pattern
    about = re.search(r"(?:^|\n)\s*about\s+([^:\n]{2,70})\s*:?", text, re.I)
    if about and about.group(1).strip().lower() not in {"us", "the company", "our company", "the role", "the job", "the position"}:
        return about.group(1).strip()

    # 3. "<Company> is hiring" pattern (case-insensitive for company name)
    hiring = re.search(r"\b([A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,4})\s+(?:is|are)\s+(?:hiring|recruiting|looking)\b", text, re.I)
    if hiring:
        candidate = hiring.group(1).strip()
        if candidate.lower() not in {"we", "they", "the", "a", "an", "our", "freshers", "remote", "immediate", "this"}:
            return candidate

    # 4. "at <Company>" pattern
    at_comp = re.search(
        r"\b(?:engineer|developer|intern|analyst|job|role|position|opening|work|careers?"
        r"|designer|manager|executive|consultant|associate|trainee|officer"
        r"|shortlisted|selected|opportunity|vacancy|vacancies)\s+"
        r"(?:at|for|in|with)\s+"
        r"([A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,4})",
        text,
        re.I,
    )
    if at_comp:
        candidate = at_comp.group(1).strip(" .,;")
        if candidate.lower() not in {"the", "a", "an", "our", "freshers", "remote", "immediate", "home", "this", "your"}:
            return candidate

    # 5. Email domain heuristic: If the contact email uses a corporate domain, derive company name
    email_match = EMAIL_RE.search(text)
    if email_match:
        domain = email_match.group(0).rsplit("@", 1)[-1].lower()
        free_providers = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "rediffmail.com", "icloud.com", "protonmail.com", "mail.com", "ymail.com"}
        if domain not in free_providers:
            # Use domain as company name hint (e.g., "tcs.com" → "tcs")
            corp_name = domain.split(".")[0]
            if len(corp_name) > 2:
                return corp_name.upper() if len(corp_name) <= 4 else corp_name.capitalize()

    return None


def _role_name(text: str, lines: list[str]) -> str | None:
    labeled = _label_value(text, r"job\s*title|position|role|designation|job\s*opening|vacancy|post")
    if labeled:
        return labeled

    hiring = re.search(r"\bhiring\s+(.{3,100}?)(?:\s*[.!\n]|\s+for\s+)", text, re.I)
    if hiring:
        candidate = hiring.group(1).strip(" -:")
        # Reject if it looks like a company name rather than a role
        if re.search(r"\b(intern|analyst|engineer|developer|manager|designer|executive|consultant|trainee|associate|officer|lead|architect|scientist|specialist)\b", candidate, re.I):
            return candidate

    # Scan first 12 lines for role-like titles, filtering noise
    noise_patterns = re.compile(
        r"^(about|location|salary|experience|min\b|job description|disclaimer|note|important|dear|hi|hello|greetings|apply|click|visit|contact|www\.|http)",
        re.I,
    )
    for line in lines[:12]:
        stripped = line.strip(" -:")
        if len(stripped) <= 90 and len(stripped) >= 5 and not noise_patterns.match(stripped):
            if re.search(r"\b(intern|analyst|engineer|developer|manager|designer|executive|consultant|trainee|associate|officer|lead|architect|scientist|specialist)\b", stripped, re.I):
                # Extra filter: reject lines that are clearly not job titles
                if not re.search(r"\b(please|you|we|our|will|shall|must|can|should|would|your|click|visit|send|apply|register|pay)\b", stripped, re.I):
                    return stripped
    return None


PHONE_RE = re.compile(r"(?:whatsapp[:\- ]*)?(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}\b", re.I)
PAYMENT_TERMS_RE = re.compile(r".{0,40}\b(?:registration fee|application fee|training fee|security deposit|processing fee|kit fee|fees?\b|stipend).{0,60}", re.I)


def parse_posting(text: str) -> ParsedPosting:
    lines = [line.strip(" \t•-*\r") for line in text.splitlines() if line.strip()]
    email = EMAIL_RE.search(text)
    url = URL_RE.findall(text)
    salary = SALARY_RE.search(text)
    experience = EXPERIENCE_RE.search(text)
    location = _label_value(text, r"work\s+location|job\s+location|location|based\s+in|city")
    employment_type = _label_value(text, r"employment\s+type|job\s+type|work\s+type|work\s+mode")
    phone = PHONE_RE.search(text)
    payment = PAYMENT_TERMS_RE.search(text)

    # Extract experience: try group(1), but fall back to group(0) for standalone matches
    exp_text = None
    if experience:
        try:
            exp_text = experience.group(1).strip() if experience.group(1) else experience.group(0).strip()
        except (IndexError, AttributeError):
            exp_text = experience.group(0).strip()

    return ParsedPosting(
        company_name=_company_name(text),
        role=_role_name(text, lines),
        salary_text=salary.group(0).strip() if salary else None,
        location=location,
        experience=exp_text,
        employment_type=employment_type,
        contact_email=email.group(0) if email else None,
        contact_phone=phone.group(0).strip() if phone else None,
        payment_terms=payment.group(0).strip() if payment else None,
        links=[u.rstrip(".,;:)\"'>") for u in url if u.rstrip(".,;:)\"'>")],
        requirements=[
            line for line in lines
            if re.search(r"\b(requirement|experience|degree|skills|qualification|education|responsibilit|must have|preferred)\b", line, re.I)
        ],
    )
