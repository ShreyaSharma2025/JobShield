"""Validated data contracts shared across workflow components."""
from typing import Literal
from pydantic import BaseModel, Field


class ParsedPosting(BaseModel):
    company_name: str | None = None
    role: str | None = None
    salary_text: str | None = None
    location: str | None = None
    experience: str | None = None
    employment_type: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    payment_terms: str | None = None
    links: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)


class Evidence(BaseModel):
    title: str
    severity: Literal["weak", "moderate", "strong"]
    quote: str
    explanation: str
    source_type: Literal["jd_text", "historical_dataset", "public_web"] = "jd_text"
    rule_id: str


class EvidenceCollection(BaseModel):
    findings: list["Evidence"] = Field(default_factory=list)


class SimilarPosting(BaseModel):
    posting_id: str
    similarity: float
    label: Literal["fraudulent", "legitimate", "unknown"]
    title: str | None = None
    excerpt: str | None = None


class SimilarityReview(BaseModel):
    summary: str
    limitation: str


class CompanyCheck(BaseModel):
    status: Literal["verified_match", "ambiguous", "not_found", "unavailable"] = "unavailable"
    company_name: str | None = None
    domain: str | None = None
    dns_status: str | None = None
    website_url: str | None = None
    website_status: str | None = None
    website_title: str | None = None
    rdap_reg_date: str | None = None
    rdap_exp_date: str | None = None
    findings: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    queried_sites: list[dict] = Field(default_factory=list)
    checked_at: str | None = None



class VerdictExplanation(BaseModel):
    explanation: str
    recommended_actions: list[str] = Field(default_factory=list)


class BaselineClassification(BaseModel):
    label: Literal["fraudulent", "legitimate", "uncertain"]
    reason: str


class RiskDecision(BaseModel):
    category: Literal["Low Risk", "Needs Verification", "High Risk"]
    summary: str
    reason_codes: list[str] = Field(default_factory=list)
    policy_version: str = "mvp-0.1"


class AnalysisResult(BaseModel):
    run_id: str
    posting: ParsedPosting
    evidence: list[Evidence]
    decision: RiskDecision
    similar_postings: list[SimilarPosting] = Field(default_factory=list)
    similarity_review: SimilarityReview | None = None
    company_check: CompanyCheck = Field(default_factory=CompanyCheck)
    workflow_events: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0
    token_usage: dict[str, int] = Field(default_factory=dict)
