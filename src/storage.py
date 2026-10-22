"""Small local audit store for MVP analysis runs."""
import json
import sqlite3
from .schemas import AnalysisResult
from .paths import DATA_DIR

DB_PATH = DATA_DIR / "jobshield.sqlite3"


def save_result(result: AnalysisResult, raw_text: str) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS analysis_runs (
            run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            raw_text TEXT NOT NULL, parsed_json TEXT NOT NULL, evidence_json TEXT NOT NULL,
            category TEXT NOT NULL, summary TEXT NOT NULL, policy_version TEXT NOT NULL
        )""")
        conn.execute("""INSERT INTO analysis_runs
            (run_id, raw_text, parsed_json, evidence_json, category, summary, policy_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)""", (
            result.run_id, raw_text, json.dumps(result.posting.model_dump(), ensure_ascii=False),
            json.dumps([item.model_dump() for item in result.evidence], ensure_ascii=False),
            result.decision.category, result.decision.summary, result.decision.policy_version,
        ))
        conn.execute("""CREATE TABLE IF NOT EXISTS analysis_details (
            run_id TEXT PRIMARY KEY REFERENCES analysis_runs(run_id),
            company_check_json TEXT NOT NULL,
            similar_postings_json TEXT NOT NULL,
            workflow_events_json TEXT NOT NULL,
            duration_seconds REAL NOT NULL DEFAULT 0,
            token_usage_json TEXT NOT NULL DEFAULT '{}'
        )""")
        detail_columns = {row[1] for row in conn.execute("PRAGMA table_info(analysis_details)")}
        if "token_usage_json" not in detail_columns:
            conn.execute("ALTER TABLE analysis_details ADD COLUMN token_usage_json TEXT NOT NULL DEFAULT '{}' ")
        conn.execute("""INSERT OR REPLACE INTO analysis_details
            (run_id, company_check_json, similar_postings_json, workflow_events_json, duration_seconds, token_usage_json)
            VALUES (?, ?, ?, ?, ?, ?)""", (
            result.run_id,
            json.dumps(result.company_check.model_dump(), ensure_ascii=False),
            json.dumps([item.model_dump() if hasattr(item, "model_dump") else item for item in result.similar_postings], ensure_ascii=False),
            json.dumps(result.workflow_events, ensure_ascii=False),
            result.duration_seconds,
            json.dumps(result.token_usage, ensure_ascii=False),
        ))
