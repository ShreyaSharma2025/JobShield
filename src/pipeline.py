"""Entry point used by Streamlit to run one posting review."""
from time import perf_counter
from uuid import uuid4
from .parser import parse_posting
from .red_flags import detect_red_flags
from .policy import calculate_decision
from .schemas import AnalysisResult
from .storage import save_result
from .guardrails import validate_posting_text


def analyze_posting(text: str) -> AnalysisResult:
    text = validate_posting_text(text)
    try:
        from .flow import JobReviewFlow
    except ModuleNotFoundError as error:
        if error.name not in {"crewai", "dotenv"}:
            raise
        return _analyze_without_crewai(text)

    review = JobReviewFlow(text)
    return review.kickoff()


def _analyze_without_crewai(text: str) -> AnalysisResult:
    """Keep the basic local demo usable before the agent stack is installed."""
    started_at = perf_counter()
    posting = parse_posting(text)
    evidence = detect_red_flags(text)
    decision = calculate_decision(evidence)
    result = AnalysisResult(
        run_id=str(uuid4()), posting=posting, evidence=evidence, decision=decision,
        duration_seconds=round(perf_counter() - started_at, 2),
    )
    save_result(result, text)
    return result
