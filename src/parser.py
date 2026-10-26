"""Extract common job-posting fields without guessing missing information."""
import re

from .schemas import ParsedPosting

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
URL_RE = re.compile(r"https?://[^\s)\]>]+", re.I)
SALARY_RE = re.compile(
    r"(?:₹|INR\s?|Rs\.?\s?|\$|USD\s?)[\d,]+(?:\s*(?:-|to)\s*(?:₹|INR\s?|Rs\.?\s?|\$|USD\s?)?[\d,]+)?"
    r"(?:\s*(?:/|per\s+)(?:month|year|annum|hour|hr))?",
    re.I,
)
EXPERIENCE_RE = re.compile(
    r"(?:min\s*[-–]\s*max\s*)?experience\s*[:\-]?\s*"
    r"(\d+(?:\.\d+)?\s*(?:-|–|to)\s*\d+(?:\.\d+)?\s*years?|"
    r"\d+(?:\.\d+)?\+?\s*years?|fresher|entry[- ]level)",
    re.I,
)


def _label_value(text: str, labels: str) -> str | None:
    match = re.search(rf"(?:^|\n)\s*(?:{labels})\s*[:\-]\s*([^\n]+)", text, re.I)
    return match.group(1).strip(" \t.,;|") if match else None


def _company_name(text: str) -> str | None:
    labeled = _label_value(text, r"company(?:\s+name)?|organization|employer")
    if labeled:
        return labeled

    about = re.search(r"(?:^|\n)\s*about\s+([^:\n]{2,70})\s*:?", text, re.I)
    if about and about.group(1).strip().lower() not in {"us", "the company", "our company"}:
        return about.group(1).strip()

    hiring = re.search(r"\b([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,4})\s+(?:is|are)\s+hiring\b", text)
    if hiring:
        return hiring.group(1).strip()

    shortlisted = re.search(r"\b(?:shortlisted|selected|opening|career|opportunity)\s+(?:at|for|in)\s+([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,3})", text, re.I)
    if shortlisted:
        candidate = shortlisted.group(1).strip()
        if candidate.lower() not in {"the", "a", "an", "our", "freshers", "remote", "immediate"}:
            return candidate

    role_at = re.search(r"\b(?:engineer|developer|intern|analyst|job|role|position|opening|work|careers?)\s+at\s+([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,4})", text, re.I)
    if role_at:
        candidate = role_at.group(1).strip(" .,;")
        if candidate.lower() not in {"the", "a", "an", "our", "freshers", "remote", "immediate"}:
            return candidate

    return None



def _role_name(text: str, lines: list[str]) -> str | None:
    labeled = _label_value(text, r"job\s*title|position|role|designation|job\s*opening")
    if labeled:
        return labeled

    hiring = re.search(r"\bhiring\s+(.{3,100}?)(?:\s*[.!\n]|\s+for\s+)", text, re.I)
    if hiring:
        return hiring.group(1).strip(" -:")

    for line in lines[:12]:
        if len(line) <= 90 and not re.match(r"^(about|location|salary|experience|min\b|job description)\b", line, re.I):
            if re.search(r"\b(intern|analyst|engineer|developer|manager|designer|executive|consultant)\b", line, re.I):
                return line.strip(" -:")
    return None


PHONE_RE = re.compile(r"(?:whatsapp[:\- ]*)?(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}\b", re.I)
PAYMENT_TERMS_RE = re.compile(r".{0,40}\b(?:registration fee|application fee|training fee|security deposit|processing fee|kit fee|fees?|stipend)\b.{0,60}", re.I)


def parse_posting(text: str) -> ParsedPosting:
    lines = [line.strip(" \t•-*\r") for line in text.splitlines() if line.strip()]
    email = EMAIL_RE.search(text)
    url = URL_RE.findall(text)
    salary = SALARY_RE.search(text)
    experience = EXPERIENCE_RE.search(text)
    location = _label_value(text, r"work\s+location|job\s+location|location|based\s+in")
    employment_type = _label_value(text, r"employment\s+type|job\s+type|work\s+type")
    phone = PHONE_RE.search(text)
    payment = PAYMENT_TERMS_RE.search(text)

    return ParsedPosting(
        company_name=_company_name(text),
        role=_role_name(text, lines),
        salary_text=salary.group(0).strip() if salary else None,
        location=location,
        experience=experience.group(1).strip() if experience else None,
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
