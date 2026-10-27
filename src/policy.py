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

    # --- Company verification context ---
    company_not_found = company_check and company_check.status == "not_found"
    company_verified = company_check and company_check.status == "verified_match"
    company_ambiguous = company_check and company_check.status == "ambiguous"
    free_email_flag = any(item.rule_id == "PERSONAL_EMAIL" for item in evidence)

    if credential_request or payment_request or repeated_strong or (strong and moderate) or repeated_moderate:
        category = "High Risk"
        summary = (
            "High-risk scam indicators detected: "
            + ", ".join(sorted({item.title for item in strong + moderate}))
            + ". Legitimate employers never ask candidates to pay fees or share OTPs/passwords. "
            "Do not proceed with this posting."
        )
    elif strong and not moderate:
        # Single strong signal without moderate backup — still dangerous
        category = "High Risk"
        summary = (
            f"A critical scam indicator was detected: {strong[0].title}. "
            "Even a single strong signal like an upfront fee demand or credential request "
            "is characteristic of fraudulent postings. Verify through official channels before proceeding."
        )
    elif moderate and company_not_found:
        # Moderate flags + company doesn't exist = High Risk
        category = "High Risk"
        summary = (
            "Multiple warning signs were found and the claimed company/domain could not be verified "
            "through public registries. This combination is strongly indicative of a scam."
        )
    elif moderate:
        category = "Needs Verification"
        detail_list = ", ".join(sorted({item.title for item in moderate}))
        summary = (
            f"Warning signs detected: {detail_list}. "
            "These patterns are commonly seen in scam postings but may occasionally appear in legitimate ones. "
            "Verify this opening directly on the company's official careers page before sharing any personal information."
        )
    elif weak and not strong and not moderate:
        # BUG FIX: This was previously a dead branch (`not evidence and any(...)` was always False)
        category = "Needs Verification"
        detail_list = ", ".join(sorted({item.title for item in weak}))
        summary = (
            f"Minor contextual signals noted: {detail_list}. "
            "No direct scam evidence was found, but these patterns warrant caution. "
            "Verify the opening through official employer channels before proceeding."
        )
    elif not evidence and company_verified:
        category = "Low Risk"
        summary = (
            "No scam indicators were detected, and public sources returned a verified company/domain match. "
            "Continue to exercise normal care before sharing personal information."
        )
    elif not evidence and company_ambiguous:
        category = "Needs Verification"
        summary = (
            "No direct scam phrases were found in the text, but the company's legitimacy could not be "
            "fully confirmed. Cross-check this opening on the official company careers portal."
        )
    elif not evidence and company_not_found:
        category = "Needs Verification"
        summary = (
            "No explicit scam language was detected, but the claimed company or domain could not be found "
            "in public registries. This could indicate a fictitious entity. Verify independently."
        )
    else:
        category = "Needs Verification"
        summary = (
            "The text checks found no overt scam phrases. However, the company and posting have not been "
            "independently verified. Always confirm job openings through the employer's official website."
        )

    return RiskDecision(
        category=category,
        summary=summary,
        reason_codes=[item.rule_id for item in evidence],
    )


def calculate_risk_score(evidence: list[Evidence], company_check: CompanyCheck | None = None) -> int:
    """Compute a dynamic 0–100 risk score based on evidence severity and company verification."""
    score = 0

    # Evidence-based scoring
    for item in evidence:
        if item.rule_id.startswith("LLM_CONTEXT_"):
            score += 3  # LLM contextual signals contribute minimally
        elif item.severity == "strong":
            score += 30
        elif item.severity == "moderate":
            score += 15
        elif item.severity == "weak":
            score += 5

    # Company verification modifiers
    if company_check:
        if company_check.status == "not_found":
            score += 15
        elif company_check.status == "verified_match":
            score = max(0, score - 10)
        elif company_check.status == "ambiguous":
            score += 5

    # Clamp to 0-100
    return max(0, min(100, score))
