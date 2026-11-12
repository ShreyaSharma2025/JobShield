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
            r"deposit (?:rs\.?|inr)|fee of (?:rs\.?|inr)|advance payment|refundable deposit|"
            r"non[- ]?refundable (?:fee|deposit)|pay (?:rs\.?|inr|₹)[\d,]+)\b.{0,80}",
            re.I,
        ),
        "The posting requests an upfront payment, fee, or security deposit as part of hiring or training. Legitimate employers rarely ask candidates to pay.",
    ),
    (
        "SENSITIVE_INFO",
        "Sensitive credential / document request",
        "strong",
        re.compile(
            r".{0,60}\b(share|send|provide|submit|enter|give)\b.{0,60}\b(otp|password|pin|bank login|"
            r"card details|bank account details|aadhaar|pan card|credit card|debit card|cvv|"
            r"net banking|upi pin|atm pin)\b.{0,60}",
            re.I,
        ),
        "The posting requests sensitive personal identity credentials (OTP, PIN, passwords, or direct banking access).",
    ),
    (
        "UNREALISTIC_SALARY",
        "Unrealistic compensation claim",
        "moderate",
        re.compile(
            r".{0,60}\b(earn (?:rs\.?|inr|₹|\$)[\d,]+\s*(?:daily|per day)|"
            r"(?:freshers?|no experience|part[- ]time).{0,40}(?:rs\.?|inr|₹|\$)?(?:[4-9]\d|\d{3}),?000\s*(?:per month|/month|weekly)|"
            r"earn\s+(?:upto?|up to)\s*(?:rs\.?|inr|₹|\$)?\s*[\d,]+\s*(?:daily|per day|per hour)|"
            r"(?:guaranteed|assured|fixed)\s+(?:income|earning|salary)\s+(?:of\s+)?(?:rs\.?|inr|₹|\$)[\d,]+)\b.{0,80}",
            re.I,
        ),
        "The compensation offered appears disproportionately high for entry-level, no-interview, or part-time work.",
    ),
    (
        "SUSPICIOUS_MESSAGING",
        "Informal messaging recruitment channel",
        "moderate",
        re.compile(
            r".{0,60}\b(contact (?:hr )?(?:directly )?on whatsapp|join (?:our )?(?:official )?telegram|"
            r"t\.me\/[a-z0-9_]+|whatsapp[:\- ]*\+?91[\d\s-]{10,}|"
            r"message (?:us )?on whatsapp|dm (?:us )?on|"
            r"reach (?:us )?on whatsapp|send (?:your )?(?:resume|cv) (?:on|to|via) whatsapp)\b.{0,80}",
            re.I,
        ),
        "Recruitment is being directed exclusively through unverified personal WhatsApp or Telegram messaging channels.",
    ),
    (
        "GUARANTEED_JOB",
        "Guaranteed selection or interview bypass",
        "moderate",
        re.compile(
            r".{0,60}\b(guaranteed job|100% placement|no interview required|job guaranteed|"
            r"direct joining letter|confirmed selection|sure shot|guaranteed offer|"
            r"direct hiring without interview|no selection process)\b.{0,80}",
            re.I,
        ),
        "A guaranteed placement or interview bypass claim was found. Real hiring processes require technical or HR evaluation.",
    ),
    (
        "URGENCY",
        "Artificial urgency language",
        "weak",
        re.compile(
            r".{0,60}\b(apply immediately|urgent hiring|only today|limited slots|last chance|"
            r"seats filling fast|hurry up|act now|don'?t miss|limited period|"
            r"offer valid (?:till|until|for)|today only|expires? (?:today|soon)|"
            r"first come first serve)\b.{0,80}",
            re.I,
        ),
        "Pressure tactics and artificial urgency language were found.",
    ),
    (
        "VAGUE_DESCRIPTION",
        "Vague or non-specific job description",
        "weak",
        re.compile(
            r".{0,60}\b(work from (?:home|mobile)|(?:simple|easy) (?:typing|data entry|copy paste) (?:job|work)|"
            r"earn (?:from|at|sitting at) home|no (?:skills?|experience|qualification) (?:required|needed)|"
            r"(?:anyone|everybody|everyone) can (?:do|apply|join)|just (?:need|have) (?:a )?(?:phone|mobile|laptop))\b.{0,80}",
            re.I,
        ),
        "The posting describes an unusually vague or simplistic job requiring no skills, often a hallmark of task-based scams.",
    ),
    (
        "IMPERSONATION_CUES",
        "Potential brand impersonation",
        "moderate",
        re.compile(
            r".{0,60}\b((?:tcs|wipro|infosys|google|amazon|microsoft|deloitte|accenture|ibm|apple|meta|flipkart)"
            r"(?:\s+(?:ltd|limited|pvt|private|inc|india|global))?"
            r"\s+(?:is\s+)?(?:hiring|recruitment|job opening|career|vacancy))\b.{0,80}",
            re.I,
        ),
        "A major enterprise brand name was mentioned with recruitment language. Verify this opening directly on the company's official careers page.",
    ),
]


def is_negated_disclaimer(quote: str) -> bool:
    """Check if the matched text is actually a legitimate company safety warning or no-fee disclaimer."""
    lower_q = quote.lower()
    negation_signals = [
        "never request", "never ask", "never require", "never charge", "never collect", "never demand",
        "does not request", "does not ask", "does not require", "does not charge", "does not collect",
        "do not pay", "do not send any money", "do not transfer", "no registration fee", "no application fee",
        "no fee", "no hidden fee", "no charges", "free of cost", "free of charge", "without any fee",
        "without any charge", "zero fee", "strictly prohibits charging", "scam alert", "fraud alert",
        "beware of fraudulent", "caution:", "disclaimer:", "never share your otp", "never ask for otp",
    ]
    return any(signal in lower_q for signal in negation_signals)


def detect_red_flags(text: str) -> list[Evidence]:
    found: list[Evidence] = []
    for rule_id, title, severity, pattern, explanation in RULES:
        # BUG FIX: Use findall-style to capture ALL occurrences, not just the first
        all_matches = list(pattern.finditer(text))
        if all_matches:
            # Combine all matched quotes for comprehensive evidence, filtering out legitimate negative disclaimers
            quotes = []
            for m in all_matches:
                q = m.group(0).strip()
                if (rule_id in {"UPFRONT_PAYMENT", "SENSITIVE_INFO"}) and is_negated_disclaimer(q):
                    continue
                if q and q not in quotes:
                    quotes.append(q)
                if len(quotes) >= 3:
                    break

            if not quotes:
                continue

            combined_quote = " [...] ".join(quotes) if len(quotes) > 1 else quotes[0]

            found.append(
                Evidence(
                    rule_id=rule_id,
                    title=title,
                    severity=severity,
                    quote=combined_quote,
                    explanation=explanation + (f" ({len(quotes)} occurrence(s) found.)" if len(quotes) > 1 else ""),
                )
            )

    # Personal email check
    email = re.search(r"\b[A-Z0-9._%+-]+@(gmail|yahoo|hotmail|outlook|rediffmail|protonmail)\.[A-Z]{2,}\b", text, re.I)
    if email:
        found.append(
            Evidence(
                rule_id="PERSONAL_EMAIL",
                title="Personal email contact",
                severity="weak",
                quote=email.group(0),
                explanation="A public/personal email provider was used instead of an official company domain. Legitimate corporate recruiters from established firms use company email addresses.",
            )
        )

    # Phone-only contact (no email, no website)
    phone = re.search(r"(?:whatsapp[:\- ]*)?(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}\b", text, re.I)
    email_present = re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, re.I)
    url_present = re.search(r"https?://[^\s)\]>]+", text, re.I)
    if phone and not email_present and not url_present:
        found.append(
            Evidence(
                rule_id="PHONE_ONLY_CONTACT",
                title="Phone-only contact with no official channels",
                severity="weak",
                quote=phone.group(0),
                explanation="The posting provides only a phone/WhatsApp number with no company email or website. Legitimate job postings typically include official company contact channels.",
            )
        )

    return found
