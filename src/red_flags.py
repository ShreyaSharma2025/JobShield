"""Transparent rule checks that point to exact text from the submitted posting."""
import re
from .schemas import Evidence

RULES = [
    ("UPFRONT_PAYMENT", "Upfront payment language", "strong", re.compile(r".{0,60}\b(registration fee|application fee|training fee|security deposit|pay (?:a |the )?(?:fee|amount)|payment required)\b.{0,80}", re.I), "The posting appears to request an upfront payment as part of the hiring process."),
    ("SENSITIVE_INFO", "Sensitive information request", "strong", re.compile(r".{0,60}\b(share|send|provide|submit)\b.{0,60}\b(otp|password|pin|bank login|card details)\b.{0,60}", re.I), "The posting appears to request sensitive account credentials."),
    ("GUARANTEED_JOB", "Guaranteed selection claim", "moderate", re.compile(r".{0,60}\b(guaranteed job|100% placement|no interview required|job guaranteed)\b.{0,80}", re.I), "A guaranteed-job or interview-bypass claim was found."),
    ("URGENCY", "Urgency language", "weak", re.compile(r".{0,60}\b(apply immediately|urgent hiring|only today|limited slots|last chance)\b.{0,80}", re.I), "Urgency language was found. This is a weak signal on its own, not proof of fraud."),
]


def detect_red_flags(text: str) -> list[Evidence]:
    found: list[Evidence] = []
    for rule_id, title, severity, pattern, explanation in RULES:
        match = pattern.search(text)
        if match:
            found.append(Evidence(rule_id=rule_id, title=title, severity=severity, quote=match.group(0).strip(), explanation=explanation))
    email = re.search(r"\b[A-Z0-9._%+-]+@(gmail|yahoo|hotmail|outlook)\.[A-Z]{2,}\b", text, re.I)
    if email:
        found.append(Evidence(rule_id="PERSONAL_EMAIL", title="Personal email contact", severity="weak", quote=email.group(0), explanation="A personal email provider was used. Check the company's official domain; this alone is not proof of fraud."))
    return found
