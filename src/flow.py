"""CrewAI Flow: shared state, checks, conditional company verification, and verdict."""
import os
import time
from uuid import uuid4

from crewai.flow.flow import Flow, listen, router, start
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from .a2a_client import verify_company_with_adk
from .observability import initialize_tracing, record_event, set_current_run_id, usage_summary
from .guardrails import keep_supported_fields, keep_supported_findings, validate_posting_text
from .parser import parse_posting
from .policy import calculate_decision
from .red_flags import detect_red_flags
from .schemas import AnalysisResult, CompanyCheck, Evidence, ParsedPosting, SimilarPosting, SimilarityReview
from .storage import save_result
from .similarity import search_similar_postings

load_dotenv()


class ReviewState(BaseModel):
    """Pydantic state carries each stage's output to the next Flow method."""
    run_id: str = ""
    raw_text: str = ""
    posting: ParsedPosting = Field(default_factory=ParsedPosting)
    evidence: list[Evidence] = Field(default_factory=list)
    similar_postings: list[SimilarPosting] = Field(default_factory=list)
    similarity_review: SimilarityReview | None = None
    company_check: CompanyCheck = Field(default_factory=CompanyCheck)
    workflow_events: list[str] = Field(default_factory=list)


class JobReviewFlow(Flow[ReviewState]):
    def __init__(self, raw_text: str):
        super().__init__()
        self.state.run_id = str(uuid4())
        self._started_at = time.perf_counter()
        set_current_run_id(self.state.run_id)
        initialize_tracing()
        self.state.raw_text = validate_posting_text(raw_text)
        self.state.posting = ParsedPosting()
        self.state.evidence = []
        self.state.similar_postings = []
        self.state.similarity_review = None
        self.state.company_check = CompanyCheck()
        self.state.workflow_events = []

    def _record(self, stage: str, status: str, detail: str = "") -> None:
        event = f"{stage}: {status}"
        self.state.workflow_events.append(event)
        record_event(self.state.run_id, stage, status, detail)

    @start()
    def parse_posting(self):
        self._record("parser", "started")
        parsed = parse_posting(self.state.raw_text)

        if os.getenv("GOOGLE_API_KEY"):
            try:
                from .agent_team import extract_posting
                agent_result = extract_posting(self.state.raw_text, parsed.model_dump())
                parsed = keep_supported_fields(agent_result, self.state.raw_text)
                self._record("crewai-parser-agent", "completed")
            except Exception as error:
                self._record("crewai-parser-agent", "fallback", type(error).__name__)

        self.state.posting = parsed
        self._record("parser", "completed")
        return parsed

    @listen(parse_posting)
    def gather_evidence(self, _parsed):
        self._record("red-flag-rules", "started")
        findings = detect_red_flags(self.state.raw_text)

        if os.getenv("GOOGLE_API_KEY"):
            try:
                from .agent_team import review_red_flags
                additions = review_red_flags(
                    self.state.raw_text,
                    [item.model_dump() for item in findings],
                )
                existing_rule_ids = {finding.rule_id for finding in findings}
                supported_additions = keep_supported_findings(additions.findings, self.state.raw_text)
                findings.extend(item for item in supported_additions if item.rule_id not in existing_rule_ids)
                self._record("crewai-red-flag-agent", "completed")
            except Exception as error:
                self._record("crewai-red-flag-agent", "fallback", type(error).__name__)

        self.state.evidence = findings
        self._record("red-flag-rules", "completed", f"{len(findings)} supported finding(s)")

        try:
            matches = search_similar_postings(self.state.raw_text)
            self.state.similar_postings = [SimilarPosting.model_validate(match) for match in matches]
            if matches:
                self._record("similarity-agent", "retrieved", f"{len(matches)} historical match(es)")
                for match in self.state.similar_postings:
                    if match.label == "fraudulent" and match.similarity >= 0.82:
                        findings.append(Evidence(
                            title="Similar historical posting labeled fraudulent",
                            severity="weak",
                            quote=f"{match.posting_id} · similarity {match.similarity:.2f} · label: fraudulent",
                            explanation="This is a supporting historical example only. Text similarity does not prove that the current posting is fraudulent.",
                            source_type="historical_dataset",
                            rule_id=f"SIMILAR_{match.posting_id}",
                        ))
                if os.getenv("GOOGLE_API_KEY"):
                    from .agent_team import review_similar_postings
                    self.state.similarity_review = review_similar_postings([match.model_dump() for match in self.state.similar_postings])
            else:
                self._record("similarity-agent", "unavailable", "No FAISS index is configured.")
        except Exception as error:
            self._record("similarity-agent", "unavailable", type(error).__name__)

        self.state.evidence = findings
        return bool(self.state.posting.company_name)

    @router(gather_evidence)
    def choose_verification_route(self, has_company: bool):
        enabled = os.getenv("A2A_AGENT_ENABLED", "false").lower() == "true"
        if has_company and enabled:
            return "verify_company"
        return "skip_company_check"

    @listen("verify_company")
    def run_company_verification(self):
        self._record("a2a-company-verification", "started")
        email = self.state.posting.contact_email
        payload = {
            "run_id": self.state.run_id,
            "company_name": self.state.posting.company_name,
            "role": self.state.posting.role,
            "email_domain": email.rsplit("@", 1)[-1] if email and "@" in email else None,
            "website": self.state.posting.links[0] if self.state.posting.links else None,
        }
        for attempt in (1, 2):
            try:
                if attempt == 2:
                    self._record("a2a-company-verification", "retry", "Retrying once after a transient failure.")
                self.state.company_check = CompanyCheck.model_validate(verify_company_with_adk(payload))
                self._record("a2a-company-verification", self.state.company_check.status)
                break
            except Exception as error:
                self._record("a2a-company-verification", "attempt_failed", type(error).__name__)
                if attempt == 2:
                    self.state.company_check = CompanyCheck(
                        status="unavailable",
                        company_name=self.state.posting.company_name,
                        findings=["The public verification service did not return a usable result."],
                    )
                    self._record("a2a-company-verification", "unavailable")
                else:
                    time.sleep(0.5)
        return self._finish()

    @listen("skip_company_check")
    def record_skipped_company_check(self):
        self.state.company_check = CompanyCheck(
            status="unavailable",
            company_name=self.state.posting.company_name,
            findings=["No company name was extracted from the posting."] if not self.state.posting.company_name else ["The ADK verification service is not configured or was not available."],
        )
        self._record("company-verification", "skipped")
        return self._finish()

    def _finish(self) -> AnalysisResult:
        decision = calculate_decision(self.state.evidence, self.state.company_check)
        if os.getenv("GOOGLE_API_KEY"):
            try:
                from .agent_team import explain_decision
                narrative = explain_decision(
                    decision.category,
                    [item.model_dump() for item in self.state.evidence],
                    self.state.company_check.model_dump(),
                )
                decision.summary = narrative.explanation
                self._record("crewai-verdict-agent", "completed")
            except Exception as error:
                self._record("crewai-verdict-agent", "fallback", type(error).__name__)

        result = AnalysisResult(
            run_id=self.state.run_id,
            posting=self.state.posting,
            evidence=self.state.evidence,
            decision=decision,
            similar_postings=self.state.similar_postings,
            similarity_review=self.state.similarity_review,
            company_check=self.state.company_check,
            workflow_events=self.state.workflow_events,
            duration_seconds=round(time.perf_counter() - self._started_at, 2),
            token_usage=usage_summary(),
        )
        save_result(result, self.state.raw_text)
        return result


