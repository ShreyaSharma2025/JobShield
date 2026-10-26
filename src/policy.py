"""Deterministic, conservative MVP risk policy; tune using a held-out validation set."""
from .schemas import CompanyCheck, Evidence, RiskDecision


def calculate_decision(evidence: list[Evidence], company_check: CompanyCheck | None = None) -> RiskDecision:
    # LLM-suggested contextual signals can raise uncertainty, but cannot trigger High Risk.
    deterministic = [item for item in evidence if not item.rule_id.startswith("LLM_CONTEXT_")]
    strong = [item for item in deterministic if item.severity == "strong"]
    moderate = [item for item in deterministic if item.severity == "moderate"]
    weak = [item for item in evidence if item.severity == "weak"]
    credential_request = any(item.rule_id == "SENSITIVE_INFO" for item in strong)
    payment_request = any(item.rule_id == "UPFRONT_PAYMENT" for item in strong)
    repeated_strong = len(strong) >= 2
    repeated_moderate = len(moderate) >= 2

    if credential_request or payment_request or repeated_strong or (strong and moderate) or repeated_moderate:
        category = "High Risk"
        summary = "High-risk scam indicators detected: upfront fee/deposit demands, credential/OTP requests, or multiple compounded suspicious patterns were identified. Never pay fees or share private credentials."
    elif not evidence and company_check and company_check.status == "verified_match":
        category = "Low Risk"
        summary = "No configured warning signs were found, and public sources returned a verified company/role match. Continue to use normal care before sharing personal information."
    elif not evidence and any(item.severity == "weak" for item in evidence):
        category = "Needs Verification"
        summary = "Minor contextual signals were noted (e.g. urgency or personal email), but no direct scam evidence. Verify through official employer channels."
    elif evidence:
        category = "Needs Verification"
        summary = "One or more warning signs were found, but this evidence alone is insufficient to definitively classify as fraud. Verify independently before proceeding."
    else:
        category = "Needs Verification"
        summary = "The current text checks found no overt scam phrases. However, the company and posting have not been independently verified."
    return RiskDecision(category=category, summary=summary, reason_codes=[item.rule_id for item in evidence])
