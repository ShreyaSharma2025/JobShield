# ====================================================================================================
# [NODE 7 / AGENT 6: DETERMINISTIC POLICY ARBITER & DYNAMIC RISK SCORING ENGINE]
# File: src/policy.py
#
# ARCHITECTURAL ROLE:
#   This module performs final evidence synthesis and mathematical risk scoring across all
#   upstream agent findings (Node 2 Parser, Node 4 Red Flags, Node 5 FAISS, Node 6 FastMCP Verifier).
#
# CODE PORTION BREAKDOWN:
#   - PORTION 1 (Lines 28 to 110): Deterministic Categorical Verdict Engine (`calculate_decision`)
#     Evaluates prioritized decision-tree branches to assign: "High Risk", "Needs Verification", or "Low Risk".
#   - PORTION 2 (Lines 113 to 155): Dynamic 0-100 Numerical Risk Scoring Engine (`calculate_risk_score`)
#     Calculates the weighted risk severity score based on rule severity and external domain verification.
# ====================================================================================================

from .schemas import CompanyCheck, Evidence, RiskDecision


# ====================================================================================================
# [PORTION 1: DETERMINISTIC CATEGORICAL VERDICT ENGINE (Lines 28 to 110)]
# Function: calculate_decision(evidence, company_check) -> RiskDecision
#
# Purpose:
#   Synthesizes all gathered evidence and external company verification status into an authoritative
#   final verdict category ("High Risk" | "Needs Verification" | "Low Risk") with plain-English rationales.
# ====================================================================================================
def calculate_decision(evidence: list[Evidence], company_check: CompanyCheck | None = None) -> RiskDecision:
    # ------------------------------------------------------------------------------------------------
    # PORTION 1.1: Signal Extraction & Severity Filtering
    # Filters out soft LLM contextual signals so LLM suggestions alone can never trigger a "High Risk" verdict.
    # ------------------------------------------------------------------------------------------------
    deterministic = [item for item in evidence if not item.rule_id.startswith("LLM_CONTEXT_")]
    strong = [item for item in deterministic if item.severity == "strong"]
    moderate = [item for item in deterministic if item.severity == "moderate"]
    weak = [item for item in evidence if item.severity == "weak"]
    credential_request = any(item.rule_id == "SENSITIVE_INFO" for item in strong)
    payment_request = any(item.rule_id == "UPFRONT_PAYMENT" for item in strong)
    repeated_strong = len(strong) >= 2
    repeated_moderate = len(moderate) >= 2

    # ------------------------------------------------------------------------------------------------
    # PORTION 1.2: External Company Verification Modifiers (From Node 6 / Agent 5)
    # ------------------------------------------------------------------------------------------------
    company_not_found = company_check and company_check.status == "not_found"
    company_verified = company_check and company_check.status == "verified_match"
    company_ambiguous = company_check and company_check.status == "ambiguous"
    free_email_flag = any(item.rule_id == "PERSONAL_EMAIL" for item in evidence)

    # ------------------------------------------------------------------------------------------------
    # PORTION 1.3: Decision Tree Evaluation Branches
    # ------------------------------------------------------------------------------------------------
    
    # BRANCH A: Severe Critical Scam Indicators -> High Risk
    # Triggers on: Advance-fee demands, credential/OTP theft, multiple strong signals, or mixed strong+moderate.
    if credential_request or payment_request or repeated_strong or (strong and moderate) or repeated_moderate:
        category = "High Risk"
        summary = (
            "High-risk scam indicators detected: "
            + ", ".join(sorted({item.title for item in strong + moderate}))
            + ". Legitimate employers never ask candidates to pay fees or share OTPs/passwords. "
            "Do not proceed with this posting."
        )

    # BRANCH B: Isolated Strong Scam Indicator -> High Risk
    # Even a single strong signal (e.g. asking for bank details or deposit) warrants immediate High Risk.
    elif strong and not moderate:
        category = "High Risk"
        summary = (
            f"A critical scam indicator was detected: {strong[0].title}. "
            "Even a single strong signal like an upfront fee demand or credential request "
            "is characteristic of fraudulent postings. Verify through official channels before proceeding."
        )

    # BRANCH C: Moderate Indicators + Domain Not Found -> High Risk
    # Moderate red flags combined with an unresolvable or fictitious company domain escalates to High Risk.
    elif moderate and company_not_found:
        category = "High Risk"
        summary = (
            "Multiple warning signs were found and the claimed company/domain could not be verified "
            "through public registries. This combination is strongly indicative of a scam."
        )

    # BRANCH D: Moderate Warning Patterns -> Needs Verification
    # Triggers on WhatsApp recruiters, unrealistic pay, high urgency, or vague job specifications.
    elif moderate:
        category = "Needs Verification"
        detail_list = ", ".join(sorted({item.title for item in moderate}))
        summary = (
            f"Warning signs detected: {detail_list}. "
            "These patterns are commonly seen in scam postings but may occasionally appear in legitimate ones. "
            "Verify this opening directly on the company's official careers page before sharing any personal information."
        )

    # BRANCH E: Minor Contextual Patterns Only -> Needs Verification
    # Triggers on Gmail/free webmail or poor grammar without explicit financial extortion phrases.
    elif weak and not strong and not moderate:
        category = "Needs Verification"
        detail_list = ", ".join(sorted({item.title for item in weak}))
        summary = (
            f"Minor contextual signals noted: {detail_list}. "
            "No direct scam evidence was found, but these patterns warrant caution. "
            "Verify the opening through official employer channels before proceeding."
        )

    # BRANCH F: Clean Text & Verified Corporate Domain -> Low Risk
    # Zero red flags detected AND the company domain is verified via ICANN RDAP / DNS with active enterprise footprint.
    elif not evidence and company_verified:
        category = "Low Risk"
        summary = (
            "No scam indicators were detected, and public sources returned a verified company/domain match. "
            "Continue to exercise normal care before sharing personal information."
        )

    # BRANCH G: Ambiguous Company Context -> Needs Verification
    elif not evidence and company_ambiguous:
        category = "Needs Verification"
        summary = (
            "No direct scam phrases were found in the text, but the company's legitimacy could not be "
            "fully confirmed. Cross-check this opening on the official company careers portal."
        )

    # BRANCH H: Claimed Domain Not Found in Registries -> Needs Verification
    elif not evidence and company_not_found:
        category = "Needs Verification"
        summary = (
            "No explicit scam language was detected, but the claimed company or domain could not be found "
            "in public registries. This could indicate a fictitious entity. Verify independently."
        )

    # BRANCH I: Default Baseline Fallback -> Needs Verification
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


# ====================================================================================================
# [PORTION 2: DYNAMIC 0–100 RISK SCORE & WEIGHTAGE ENGINE (Lines 113 to 155)]
# Function: calculate_risk_score(evidence, company_check) -> int (0 to 100)
#
# POINT WEIGHTAGE ALLOCATION SYSTEM:
#   1. Evidence Severity Scoring:
#      - Strong Flag    : +30 points each (UPFRONT_PAYMENT, SENSITIVE_INFO)
#      - Moderate Flag  : +15 points each (SUSPICIOUS_MESSAGING, UNREALISTIC_COMP, URGENCY, etc.)
#      - Weak Flag      : +5 points each  (PERSONAL_EMAIL, POOR_WRITING, PHONE_ONLY_CONTACT)
#      - LLM Context    : +3 points each  (Soft contextual guidance)
#   2. External Verification Modifiers (Node 6 / Agent 5 FastMCP Tools):
#      - Company Not Found    : +15 points penalty (Fictitious or NXDOMAIN domain)
#      - Company Ambiguous    : +5 points penalty  (Unclear corporate provenance)
#      - Verified Match       : -10 points credit  (Authentic corporate registrar match)
#   3. Normalization:
#      - Strict clamping between minimum 0 and maximum 100.
# ====================================================================================================
def calculate_risk_score(evidence: list[Evidence], company_check: CompanyCheck | None = None) -> int:
    """Compute a dynamic 0–100 risk score based on evidence severity and company verification."""
    score = 0

    # ------------------------------------------------------------------------------------------------
    # PORTION 2.1: Evidence-Based Severity Points Accumulation
    # ------------------------------------------------------------------------------------------------
    for item in evidence:
        if item.rule_id.startswith("LLM_CONTEXT_"):
            score += 3  # LLM contextual signals contribute minimally (+3 pts)
        elif item.severity == "strong":
            score += 30  # Critical threats: fee demands, credential theft (+30 pts)
        elif item.severity == "moderate":
            score += 15  # Serious warning signs: WhatsApp recruiter, extreme pay (+15 pts)
        elif item.severity == "weak":
            score += 5   # Mild signals: free webmail, typos (+5 pts)

    # ------------------------------------------------------------------------------------------------
    # PORTION 2.2: Company & Domain Verification Modifiers
    # ------------------------------------------------------------------------------------------------
    if company_check:
        if company_check.status == "not_found":
            score += 15  # Unregistered / fictitious domain penalty (+15 pts)
        elif company_check.status == "verified_match":
            score = max(0, score - 10)  # Trusted verified domain bonus (-10 pts)
        elif company_check.status == "ambiguous":
            score += 5   # Ambiguous registry match (+5 pts)

    # ------------------------------------------------------------------------------------------------
    # PORTION 2.3: Boundary Normalization & Clamping
    # ------------------------------------------------------------------------------------------------
    return max(0, min(100, score))

