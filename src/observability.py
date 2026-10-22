"""Small local event log used to follow an analysis from start to finish."""
import json
import logging
import os
from contextvars import ContextVar
from datetime import datetime, timezone
from threading import Lock
import sqlite3

from .paths import DATA_DIR

LOG_PATH = DATA_DIR / "agent_events.jsonl"
_lock = Lock()
_current_run_id = ContextVar("jobshield_run_id", default="unknown")
_usage = ContextVar("jobshield_usage", default=None)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("jobshield")


def set_current_run_id(run_id: str) -> None:
    _current_run_id.set(run_id)
    _usage.set({"prompt_tokens": 0, "completion_tokens": 0, "calls": 0})


def usage_summary() -> dict:
    return dict(_usage.get() or {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0})


def initialize_tracing() -> None:
    """Send CrewAI OpenTelemetry spans to Langfuse when credentials are configured."""
    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        return
    try:
        from openinference.instrumentation.crewai import CrewAIInstrumentor
        CrewAIInstrumentor().instrument(skip_dep_check=True)
    except ImportError:
        logger.warning("Langfuse keys are set, but CrewAI tracing dependencies are missing.")


def record_event(run_id: str, component: str, status: str, detail: str = "") -> None:
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "component": component,
        "status": status,
        "detail": detail[:300],
    }
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock, LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(event, ensure_ascii=False) + "\n")
    try:
        with sqlite3.connect(DATA_DIR / "jobshield.sqlite3") as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS workflow_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL, run_id TEXT NOT NULL,
                component TEXT NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL
            )""")
            connection.execute(
                "INSERT INTO workflow_events (timestamp, run_id, component, status, detail) VALUES (?, ?, ?, ?, ?)",
                (event["timestamp"], run_id, component, status, event["detail"]),
            )
    except sqlite3.Error:
        logger.exception("Could not save the workflow event to SQLite.")
    logger.info("%s %s: %s", component, status, detail[:160])


def crew_step_callback(step_output) -> None:
    """Log that an agent step ran without copying its prompt or JD into logs."""
    record_event(_current_run_id.get(), "crewai-agent-step", "completed", type(step_output).__name__)


def crew_task_callback(task_output) -> None:
    record_event(_current_run_id.get(), "crewai-task", "completed", type(task_output).__name__)


def record_crew_usage(crew_output) -> None:
    """Collect usage from CrewOutput once per completed Crew, when the provider exposes it."""
    usage = getattr(crew_output, "token_usage", None)
    if usage:
        totals = _usage.get() or {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}
        if isinstance(usage, dict):
            prompt = usage.get("prompt_tokens", usage.get("total_prompt_tokens", 0))
            completion = usage.get("completion_tokens", usage.get("total_completion_tokens", 0))
        else:
            prompt = getattr(usage, "prompt_tokens", getattr(usage, "total_prompt_tokens", 0))
            completion = getattr(usage, "completion_tokens", getattr(usage, "total_completion_tokens", 0))
        totals["prompt_tokens"] += int(prompt or 0)
        totals["completion_tokens"] += int(completion or 0)
        totals["calls"] += 1
        _usage.set(totals)
        detail = f"prompt={totals['prompt_tokens']} completion={totals['completion_tokens']} calls={totals['calls']}"
    else:
        detail = "Provider usage was not exposed for this crew run."
    record_event(_current_run_id.get(), "crewai-token-usage", "recorded" if usage else "unavailable", detail)


def adk_before_agent_callback(callback_context):
    record_event(callback_context.invocation_id or "adk-run", "adk-company-verifier", "started")
    return None


def adk_after_agent_callback(callback_context):
    record_event(callback_context.invocation_id or "adk-run", "adk-company-verifier", "completed")
    return None
