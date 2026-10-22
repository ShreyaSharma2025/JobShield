"""Deterministic, conservative MVP risk policy; tune using a held-out validation set."""
from .schemas import CompanyCheck, Evidence, RiskDecision


def calculate_decision(evidence: list[Evidence], company_check: CompanyCheck | None = None) -> RiskDecision:
    # LLM-suggested contextual signals can raise uncertainty, but cannot trigger High Risk.
    deterministic = [item for item in evidence if not item.rule_id.startswith("LLM_CONTEXT_")]
    strong = [item for item in deterministic if item.severity == "strong"]
    moderate = [item for item in deterministic if item.severity == "moderate"]
    weak = [item for item in evidence if item.severity == "weak"]
    credential_request = any(item.rule_id == "SENSITIVE_INFO" for item in strong)
    repeated_strong = len(strong) >= 2
    if credential_request or repeated_strong or (strong and moderate):
        category = "High Risk"
        summary = "A sensitive credential request, repeated strong signals, or a strong signal combined with another concern was found. Verify the role through an independent, official channel before taking action."
    elif not evidence and company_check and company_check.status == "verified_match":
        category = "Low Risk"
        summary = "No configured warning signs were found, and public sources returned a company and role match. Continue to use normal care before sharing personal information."
    elif evidence:
        category = "Needs Verification"
        summary = "One or more warning signs were found, but this evidence is not enough to call the posting fraudulent. Verify it through the company's official channel."
    else:
        category = "Needs Verification"
        summary = "The current text checks found no listed warning phrases. The company and posting have not been independently verified."
    return RiskDecision(category=category, summary=summary, reason_codes=[item.rule_id for item in evidence])
