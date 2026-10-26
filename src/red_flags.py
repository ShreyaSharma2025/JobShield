"""Transparent rule checks that point to exact text from the submitted posting."""
import re
from .schemas import Evidence

RULES = [
    (
        "UPFRONT_PAYMENT",
        "Upfront payment or deposit request",
        "strong",
        re.compile(
            r".{0,60}\b(registration fee|application fee|training (?:fee|charge)|security deposit|"
            r"kit fee|processing (?:fee|charge)|pay (?:a |the )?(?:fee|amount|deposit)|payment required|"
            r"deposit (?:rs\.?|inr)|fee of (?:rs\.?|inr))\b.{0,80}",
            re.I,
        ),
        "The posting requests an upfront payment, fee, or security deposit as part of hiring or training. Legitimate employers rarely ask candidates to pay.",
    ),
    (
        "SENSITIVE_INFO",
        "Sensitive credential / document request",
        "strong",
        re.compile(
            r".{0,60}\b(share|send|provide|submit)\b.{0,60}\b(otp|password|pin|bank login|card details|bank account details|aadhaar|pan card)\b.{0,60}",
            re.I,
        ),
        "The posting requests sensitive personal identity credentials (OTP, PIN, passwords, or direct banking access).",
    ),
    (
        "UNREALISTIC_SALARY",
        "Unrealistic compensation claim",
        "moderate",
        re.compile(
            r".{0,60}\b(earn (?:rs\.?|inr|\$)[\d,]+\s*(?:daily|per day)|"
            r"(?:freshers?|no experience|part[- ]time).{0,40}(?:rs\.?|inr|\$)?(?:[4-9]\d|\d{3}),?000\s*(?:per month|/month|weekly))\b.{0,80}",
            re.I,
        ),
        "The compensation offered appears disproportionately high for entry-level, no-interview, or part-time work.",
    ),
    (
        "SUSPICIOUS_MESSAGING",
        "Informal messaging recruitment channel",
        "moderate",
        re.compile(
            r".{0,60}\b(contact (?:hr )?(?:directly )?on whatsapp|join (?:our )?(?:official )?telegram|t\.me\/[a-z0-9_]+|whatsapp[:\- ]*\+?91[\d\s-]{10,})\b.{0,80}",
            re.I,
        ),
        "Recruitment is being directed exclusively through unverified personal WhatsApp or Telegram messaging channels.",
    ),
    (
        "GUARANTEED_JOB",
        "Guaranteed selection or interview bypass",
        "moderate",
        re.compile(
            r".{0,60}\b(guaranteed job|100% placement|no interview required|job guaranteed|direct joining letter|confirmed selection)\b.{0,80}",
            re.I,
        ),
        "A guaranteed placement or interview bypass claim was found. Real hiring processes require technical or HR evaluation.",
    ),
    (
        "URGENCY",
        "Artificial urgency language",
        "weak",
        re.compile(
            r".{0,60}\b(apply immediately|urgent hiring|only today|limited slots|last chance|seats filling fast)\b.{0,80}",
            re.I,
        ),
        "Pressure tactics and artificial urgency language were found.",
    ),
]


def detect_red_flags(text: str) -> list[Evidence]:
    found: list[Evidence] = []
    for rule_id, title, severity, pattern, explanation in RULES:
        match = pattern.search(text)
        if match:
            found.append(
                Evidence(
                    rule_id=rule_id,
                    title=title,
                    severity=severity,
                    quote=match.group(0).strip(),
                    explanation=explanation,
                )
            )
    email = re.search(r"\b[A-Z0-9._%+-]+@(gmail|yahoo|hotmail|outlook)\.[A-Z]{2,}\b", text, re.I)
    if email:
        found.append(
            Evidence(
                rule_id="PERSONAL_EMAIL",
                title="Personal email contact",
                severity="weak",
                quote=email.group(0),
                explanation="A public/personal email provider was used instead of an official company domain. Check company authenticity.",
            )
        )
    return found

