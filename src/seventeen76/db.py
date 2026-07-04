from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import secrets
import sqlite3
from pathlib import Path
from typing import Any, Iterator

from .config import settings


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path | str = settings.database_path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self._ensure_user_profile_columns(conn)

    def _ensure_user_profile_columns(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "persona" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN persona TEXT NOT NULL DEFAULT ''")
        if "interests" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN interests TEXT NOT NULL DEFAULT ''")

    def create_or_get_user(self, email: str, name: str, persona: str = "", interests: str = "") -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if row is None:
                user_id = insert(
                    conn,
                    "users",
                    {
                        "email": email,
                        "name": name,
                        "persona": persona,
                        "interests": interests,
                        "created_at": now_iso(),
                    },
                )
                insert(
                    conn,
                    "forecaster_scores",
                    {"user_id": user_id, "brier_score": 0.0, "resolved_count": 0, "reputation": 50.0},
                )
            else:
                user_id = row["id"]
                updates = {"name": name, "persona": persona, "interests": interests}
                for key, value in updates.items():
                    if value:
                        conn.execute(f"UPDATE users SET {key} = ? WHERE id = ?", (value, user_id))
            token = secrets.token_urlsafe(32)
            insert(conn, "sessions", {"token": token, "user_id": user_id, "created_at": now_iso()})
            user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return {
                "token": token,
                "user_id": user_id,
                "name": user["name"],
                "email": user["email"],
                "persona": user["persona"],
                "interests": user["interests"],
            }

    def user_for_token(self, token: str | None) -> sqlite3.Row | None:
        if not token:
            return None
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT users.* FROM users
                JOIN sessions ON sessions.user_id = users.id
                WHERE sessions.token = ?
                """,
                (token,),
            ).fetchone()


def insert(conn: sqlite3.Connection, table: str, values: dict[str, Any]) -> int:
    keys = list(values)
    placeholders = ", ".join(["?"] * len(keys))
    sql = f"INSERT INTO {table} ({', '.join(keys)}) VALUES ({placeholders})"
    cur = conn.execute(sql, [values[k] for k in keys])
    return int(cur.lastrowid)


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    persona TEXT NOT NULL DEFAULT '',
    interests TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_date TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    raw_html TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rule_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER REFERENCES issues(id) ON DELETE SET NULL,
    agency TEXT NOT NULL,
    title TEXT NOT NULL,
    tac_citation TEXT NOT NULL,
    action_type TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT NOT NULL,
    why_matters TEXT NOT NULL,
    heard_signal TEXT NOT NULL,
    source_url TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rule_stages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL REFERENCES rule_actions(id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    preamble TEXT NOT NULL,
    text TEXT NOT NULL,
    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER REFERENCES rule_actions(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    url TEXT NOT NULL,
    snippet TEXT NOT NULL,
    retrieved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS comment_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL REFERENCES rule_actions(id) ON DELETE CASCADE,
    concern TEXT NOT NULL,
    agency_response TEXT NOT NULL,
    disposition TEXT NOT NULL,
    evidence_source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL REFERENCES rule_actions(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    summary TEXT NOT NULL,
    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS briefs (
    rule_id INTEGER PRIMARY KEY REFERENCES rule_actions(id) ON DELETE CASCADE,
    plain_summary TEXT NOT NULL,
    affected_groups TEXT NOT NULL,
    status_text TEXT NOT NULL,
    public_heard_signal TEXT NOT NULL,
    body TEXT NOT NULL,
    source_ids TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS authority_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL REFERENCES rule_actions(id) ON DELETE CASCADE,
    citation TEXT NOT NULL,
    url TEXT NOT NULL,
    summary TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS forecast_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL REFERENCES rule_actions(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    resolution_criteria TEXT NOT NULL,
    source_of_truth TEXT NOT NULL,
    status TEXT NOT NULL,
    aggregate_probability REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS forecast_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    forecast_id INTEGER NOT NULL REFERENCES forecast_questions(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    probability REAL NOT NULL,
    rationale TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS forecast_resolutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    forecast_id INTEGER NOT NULL REFERENCES forecast_questions(id) ON DELETE CASCADE,
    outcome TEXT NOT NULL,
    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,
    resolved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS forecaster_scores (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    brier_score REAL NOT NULL,
    resolved_count INTEGER NOT NULL,
    reputation REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    source_url TEXT NOT NULL,
    read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL REFERENCES rule_actions(id) ON DELETE CASCADE,
    workflow TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS graph_state_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    graph_run_id INTEGER NOT NULL REFERENCES graph_runs(id) ON DELETE CASCADE,
    node TEXT NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""
