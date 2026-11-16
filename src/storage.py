"""Audit store and user authentication for JobShield analysis runs."""
import hashlib
import hmac
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any
from .schemas import AnalysisResult
from .paths import DATA_DIR

DB_PATH = DATA_DIR / "jobshield.sqlite3"


def _hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    pwd_hash = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"{salt}${pwd_hash}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, expected_hash = stored_hash.split("$", 1)
        actual_hash = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        return hmac.compare_digest(actual_hash, expected_hash)
    except Exception:
        return False


def init_db() -> None:
    """Initialize database tables for users, runs, details, and workflow events."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'Analyst',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS analysis_runs (
            run_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            raw_text TEXT NOT NULL,
            parsed_json TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            category TEXT NOT NULL,
            summary TEXT NOT NULL,
            policy_version TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS analysis_details (
            run_id TEXT PRIMARY KEY REFERENCES analysis_runs(run_id),
            company_check_json TEXT NOT NULL,
            similar_postings_json TEXT NOT NULL,
            workflow_events_json TEXT NOT NULL,
            duration_seconds REAL NOT NULL DEFAULT 0,
            token_usage_json TEXT NOT NULL DEFAULT '{}'
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS workflow_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            run_id TEXT NOT NULL,
            component TEXT NOT NULL,
            status TEXT NOT NULL,
            detail TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS adk_eval_runs (
            run_id TEXT PRIMARY KEY,
            added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        # Seed initial 60 benchmark audit runs if empty
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM adk_eval_runs")
        if cur.fetchone()[0] == 0:
            conn.execute("""
                INSERT OR IGNORE INTO adk_eval_runs (run_id)
                SELECT run_id FROM analysis_runs WHERE category IS NOT NULL ORDER BY created_at DESC LIMIT 60
            """)

        # Backfill workflow_events from analysis_details if empty
        cur.execute("SELECT count(*) FROM workflow_events")
        if cur.fetchone()[0] == 0:
            cur.execute("""
                SELECT r.run_id, r.created_at, d.workflow_events_json
                FROM analysis_runs r
                JOIN analysis_details d ON r.run_id = d.run_id
                ORDER BY r.created_at ASC
            """)
            for r_id, c_at, w_json in cur.fetchall():
                try:
                    ev_list = json.loads(w_json) if w_json else []
                    for ev in ev_list:
                        component = "workflow-step"
                        status = "completed"
                        detail = ev
                        if ":" in ev:
                            parts = ev.split(":", 1)
                            component = parts[0].strip()
                            detail = parts[1].strip()
                        conn.execute(
                            "INSERT INTO workflow_events (timestamp, run_id, component, status, detail) VALUES (?, ?, ?, ?, ?)",
                            (c_at, r_id, component, status, detail),
                        )
                except Exception:
                    pass


def register_user(email: str, password: str, name: str = "Lead Analyst", role: str = "Lead Analyst") -> tuple[bool, str]:
    """Register a new user account."""
    init_db()
    clean_email = email.strip().lower()
    if not clean_email or "@" not in clean_email:
        return False, "Please enter a valid email address."
    if len(password) < 4:
        return False, "Password must be at least 4 characters long."

    pwd_hash = _hash_password(password)
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO users (email, name, password_hash, role) VALUES (?, ?, ?, ?)",
                (clean_email, name.strip() or "Analyst", pwd_hash, role)
            )
        return True, "User registered successfully."
    except sqlite3.IntegrityError:
        return False, "An account with this email already exists."
    except Exception as e:
        return False, f"Registration error: {e}"


def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    """Validate credentials and return user profile dict or None."""
    init_db()
    clean_email = email.strip().lower()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT user_id, email, name, password_hash, role FROM users WHERE email = ?", (clean_email,))
        row = cur.fetchone()
        if row and _verify_password(password, row["password_hash"]):
            return {
                "user_id": row["user_id"],
                "email": row["email"],
                "name": row["name"],
                "role": row["role"],
            }
    return None


def save_result(result: AnalysisResult, raw_text: str) -> None:
    """Save full Pydantic analysis output and execution details into SQLite."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""INSERT OR REPLACE INTO analysis_runs
            (run_id, raw_text, parsed_json, evidence_json, category, summary, policy_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)""", (
            result.run_id, raw_text, json.dumps(result.posting.model_dump(), ensure_ascii=False),
            json.dumps([item.model_dump() for item in result.evidence], ensure_ascii=False),
            result.decision.category, result.decision.summary, result.decision.policy_version,
        ))
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
        conn.execute("""INSERT OR REPLACE INTO adk_eval_runs (run_id) VALUES (?)""", (result.run_id,))

        # Ensure workflow events are persisted into workflow_events table
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM workflow_events WHERE run_id = ?", (result.run_id,))
        if cur.fetchone()[0] == 0 and result.workflow_events:
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            for ev in result.workflow_events:
                component = "workflow-step"
                status = "completed"
                detail = ev
                if ":" in ev:
                    parts = ev.split(":", 1)
                    component = parts[0].strip()
                    detail = parts[1].strip()
                conn.execute(
                    "INSERT INTO workflow_events (timestamp, run_id, component, status, detail) VALUES (?, ?, ?, ?, ?)",
                    (now_str, result.run_id, component, status, detail),
                )


def get_recent_runs(limit: int = 15) -> list[dict[str, Any]]:
    """Retrieve historical analysis runs for audit inspection."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT r.run_id, r.created_at, r.category, r.summary, r.policy_version,
                   d.duration_seconds, d.token_usage_json, d.company_check_json
            FROM analysis_runs r
            LEFT JOIN analysis_details d ON r.run_id = d.run_id
            ORDER BY r.created_at DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cur.fetchall()]


def get_workflow_events(run_id: str | None = None, limit: int = 40) -> list[dict[str, Any]]:
    """Retrieve event callback log entries from SQLite with automatic self-healing sync."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        if run_id:
            cur.execute("""
                SELECT timestamp, run_id, component, status, detail
                FROM workflow_events
                WHERE run_id = ?
                ORDER BY event_id ASC
                LIMIT ?
            """, (run_id, limit))
            results = [dict(row) for row in cur.fetchall()]
            if results:
                return results

            # Self-healing fallback: extract and sync from analysis_details if missing
            cur.execute("""
                SELECT r.run_id, r.created_at, d.workflow_events_json
                FROM analysis_runs r
                JOIN analysis_details d ON r.run_id = d.run_id
                WHERE r.run_id = ?
            """, (run_id,))
            row = cur.fetchone()
            if row:
                r_id, c_at, w_json = row
                try:
                    ev_list = json.loads(w_json) if w_json else []
                    for ev in ev_list:
                        component = "workflow-step"
                        status = "completed"
                        detail = ev
                        if ":" in ev:
                            parts = ev.split(":", 1)
                            component = parts[0].strip()
                            detail = parts[1].strip()
                        conn.execute(
                            "INSERT INTO workflow_events (timestamp, run_id, component, status, detail) VALUES (?, ?, ?, ?, ?)",
                            (c_at, r_id, component, status, detail),
                        )
                    conn.commit()
                    cur.execute("""
                        SELECT timestamp, run_id, component, status, detail
                        FROM workflow_events
                        WHERE run_id = ?
                        ORDER BY event_id ASC
                        LIMIT ?
                    """, (run_id, limit))
                    return [dict(r) for r in cur.fetchall()]
                except Exception:
                    pass
            return []
        else:
            # Sync any recent analysis_runs missing from workflow_events
            try:
                cur.execute("""
                    SELECT r.run_id, r.created_at, d.workflow_events_json
                    FROM analysis_runs r
                    JOIN analysis_details d ON r.run_id = d.run_id
                    WHERE r.run_id NOT IN (SELECT DISTINCT run_id FROM workflow_events)
                    ORDER BY r.created_at DESC
                    LIMIT 20
                """)
                missing_runs = cur.fetchall()
                if missing_runs:
                    for r_id, c_at, w_json in missing_runs:
                        ev_list = json.loads(w_json) if w_json else []
                        for ev in ev_list:
                            component = "workflow-step"
                            status = "completed"
                            detail = ev
                            if ":" in ev:
                                parts = ev.split(":", 1)
                                component = parts[0].strip()
                                detail = parts[1].strip()
                            conn.execute(
                                "INSERT INTO workflow_events (timestamp, run_id, component, status, detail) VALUES (?, ?, ?, ?, ?)",
                                (c_at, r_id, component, status, detail),
                            )
                    conn.commit()
            except Exception:
                pass

            cur.execute("""
                SELECT timestamp, run_id, component, status, detail
                FROM workflow_events
                ORDER BY event_id DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cur.fetchall()]
