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
    pk = os.getenv("LANGFUSE_PUBLIC_KEY")
    sk = os.getenv("LANGFUSE_SECRET_KEY")
    if not (pk and sk):
        return
    try:
        import base64
        host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com").rstrip("/")
        auth = base64.b64encode(f"{pk}:{sk}".encode()).decode()
        if not os.getenv("OTEL_EXPORTER_OTLP_HEADERS"):
            os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization=Basic {auth}"
        if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
            os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = f"{host}/api/public/otel"

        from openinference.instrumentation.crewai import CrewAIInstrumentor
        CrewAIInstrumentor().instrument(skip_dep_check=True)
        logger.info("Langfuse OpenTelemetry tracing active for CrewAI at %s", host)
    except ImportError:
        logger.warning("Langfuse keys are set, but CrewAI tracing dependencies are missing.")
    except Exception as exc:
        logger.warning("Failed to initialize Langfuse tracing: %s", exc)


def record_event(run_id: str, component: str, status: str, detail: str = "") -> None:
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "component": component,
        "status": status,
        "detail": str(detail)[:1000],
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
    logger.info("%s %s: %s", component, status, event["detail"][:160])


def crew_step_callback(step_output) -> None:
    """Log an agent step and capture intermediate reasoning/action for auditability."""
    thought_or_action = ""
    if hasattr(step_output, "thought") and step_output.thought:
        thought_or_action = str(step_output.thought).strip()
    elif hasattr(step_output, "text") and step_output.text:
        thought_or_action = str(step_output.text).strip()
    elif isinstance(step_output, tuple) and len(step_output) > 0:
        thought_or_action = str(step_output[0]).strip()
    else:
        thought_or_action = str(step_output).strip()

    detail = f"Step Output: {thought_or_action[:300]}" if thought_or_action else f"Completed: {type(step_output).__name__}"
    record_event(_current_run_id.get(), "crewai-agent-step", "intermediate_step", detail)


def crew_task_callback(task_output) -> None:
    """Log task completion with structured intermediate output for auditability and transparency."""
    agent_name = getattr(task_output, "agent", "Specialist Agent")
    raw_content = ""
    if hasattr(task_output, "pydantic") and task_output.pydantic:
        raw_content = task_output.pydantic.model_dump_json()
    elif hasattr(task_output, "raw") and task_output.raw:
        raw_content = str(task_output.raw).strip()
    else:
        raw_content = str(task_output)

    detail = f"Agent Output [{agent_name}]: {raw_content[:400]}"
    record_event(_current_run_id.get(), f"crewai-task:{agent_name}", "intermediate_output", detail)


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
    inv_id = getattr(callback_context, "invocation_id", None) or _current_run_id.get()
    record_event(inv_id, "adk-company-verifier", "started", "A2A request received by Google ADK verifier")
    return None


def adk_after_agent_callback(callback_context):
    inv_id = getattr(callback_context, "invocation_id", None) or _current_run_id.get()
    output_summary = ""
    if hasattr(callback_context, "output"):
        output_summary = str(callback_context.output)[:300]
    elif hasattr(callback_context, "result"):
        output_summary = str(callback_context.result)[:300]
    detail = f"ADK Verification Result: {output_summary}" if output_summary else "ADK verification finished"
    record_event(inv_id, "adk-company-verifier", "completed", detail)
    return None
