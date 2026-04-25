import json
import sqlite3
from datetime import datetime
from pathlib import Path


DB_PATH = Path(__file__).resolve().parents[1] / "data" / "pader_platform.db"


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                report_type TEXT NOT NULL DEFAULT 'PADER',
                product_name TEXT,
                assigned_reviewer TEXT NOT NULL DEFAULT '',
                assigned_approver TEXT NOT NULL DEFAULT '',
                workflow_status TEXT NOT NULL DEFAULT 'Author Draft',
                context_json TEXT NOT NULL DEFAULT '{}',
                approval_context_json TEXT NOT NULL DEFAULT '{}',
                drafts_json TEXT NOT NULL DEFAULT '{}',
                review_comments_json TEXT NOT NULL DEFAULT '[]',
                full_report_text TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(reports)").fetchall()
        }
        if "assigned_reviewer" not in existing_columns:
            conn.execute(
                "ALTER TABLE reports ADD COLUMN assigned_reviewer TEXT NOT NULL DEFAULT ''"
            )
        if "assigned_approver" not in existing_columns:
            conn.execute(
                "ALTER TABLE reports ADD COLUMN assigned_approver TEXT NOT NULL DEFAULT ''"
            )
        if "review_comments_json" not in existing_columns:
            conn.execute(
                "ALTER TABLE reports ADD COLUMN review_comments_json TEXT NOT NULL DEFAULT '[]'"
            )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                role TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                comment TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS report_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                version_label TEXT NOT NULL,
                major_number INTEGER NOT NULL,
                minor_number INTEGER NOT NULL,
                version_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                actor_name TEXT NOT NULL,
                action TEXT NOT NULL,
                workflow_status TEXT NOT NULL,
                context_json TEXT NOT NULL DEFAULT '{}',
                approval_context_json TEXT NOT NULL DEFAULT '{}',
                drafts_json TEXT NOT NULL DEFAULT '{}',
                review_comments_json TEXT NOT NULL DEFAULT '[]',
                full_report_text TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE
            )
            """
        )


def _to_json(data: dict) -> str:
    return json.dumps(data, default=str)


def _from_json(value: str) -> dict:
    if not value:
        return {}
    return json.loads(value)


def list_reports() -> list[dict]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                title,
                product_name,
                assigned_reviewer,
                assigned_approver,
                workflow_status,
                updated_at
            FROM reports
            ORDER BY updated_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def create_report(title: str, product_name: str = "") -> int:
    init_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO reports (
                title, product_name, workflow_status, created_at, updated_at
            )
            VALUES (?, ?, 'Author Draft', ?, ?)
            """,
            (title, product_name, now, now),
        )
    return int(cursor.lastrowid)


def get_report(report_id: int) -> dict | None:
    init_db()
    with get_connection() as conn:
        report = conn.execute(
            "SELECT * FROM reports WHERE id = ?",
            (report_id,),
        ).fetchone()
        if report is None:
            return None

        events = conn.execute(
            """
            SELECT timestamp, role, actor, action, comment
            FROM workflow_events
            WHERE report_id = ?
            ORDER BY id ASC
            """,
            (report_id,),
        ).fetchall()

    result = dict(report)
    result["context"] = _from_json(result.pop("context_json"))
    result["approval_context"] = _from_json(result.pop("approval_context_json"))
    result["drafts"] = _from_json(result.pop("drafts_json"))
    result["review_comments"] = json.loads(result.pop("review_comments_json") or "[]")
    result["workflow_history"] = [dict(row) for row in events]
    return result


def _next_version(conn, report_id: int, version_type: str) -> tuple[int, int, str]:
    latest = conn.execute(
        """
        SELECT major_number, minor_number
        FROM report_versions
        WHERE report_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (report_id,),
    ).fetchone()

    if latest is None:
        if version_type == "major":
            return 1, 0, "1.0"
        return 0, 1, "0.1"

    major = int(latest["major_number"])
    minor = int(latest["minor_number"])

    if version_type == "major":
        next_major = major + 1 if major > 0 or minor == 0 else 1
        return next_major, 0, f"{next_major}.0"

    next_minor = minor + 1
    return major, next_minor, f"{major}.{next_minor}"


def create_version_snapshot(
    report_id: int,
    version_type: str,
    actor_role: str,
    actor_name: str,
    action: str,
    workflow_status: str,
    context: dict,
    approval_context: dict,
    drafts: dict[str, str],
    review_comments: list[dict],
    full_report_text: str,
) -> str:
    init_db()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        major, minor, label = _next_version(conn, report_id, version_type)
        conn.execute(
            """
            INSERT INTO report_versions (
                report_id,
                version_label,
                major_number,
                minor_number,
                version_type,
                timestamp,
                actor_role,
                actor_name,
                action,
                workflow_status,
                context_json,
                approval_context_json,
                drafts_json,
                review_comments_json,
                full_report_text
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                label,
                major,
                minor,
                version_type,
                timestamp,
                actor_role,
                actor_name,
                action,
                workflow_status,
                _to_json(context),
                _to_json(approval_context),
                _to_json(drafts),
                json.dumps(review_comments, default=str),
                full_report_text,
            ),
        )
    return label


def list_report_versions(report_id: int) -> list[dict]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                version_label,
                version_type,
                timestamp,
                actor_role,
                actor_name,
                action,
                workflow_status
            FROM report_versions
            WHERE report_id = ?
            ORDER BY id DESC
            """,
            (report_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_report_version(version_id: int) -> dict | None:
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM report_versions WHERE id = ?",
            (version_id,),
        ).fetchone()

    if row is None:
        return None

    version = dict(row)
    version["context"] = _from_json(version.pop("context_json"))
    version["approval_context"] = _from_json(version.pop("approval_context_json"))
    version["drafts"] = _from_json(version.pop("drafts_json"))
    version["review_comments"] = json.loads(version.pop("review_comments_json") or "[]")
    return version


def save_report(
    report_id: int,
    title: str,
    product_name: str,
    assigned_reviewer: str,
    assigned_approver: str,
    context: dict,
    approval_context: dict,
    drafts: dict[str, str],
    review_comments: list[dict],
    full_report_text: str,
    workflow_status: str,
    workflow_history: list[dict],
):
    init_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE reports
            SET title = ?,
                product_name = ?,
                assigned_reviewer = ?,
                assigned_approver = ?,
                context_json = ?,
                approval_context_json = ?,
                drafts_json = ?,
                review_comments_json = ?,
                full_report_text = ?,
                workflow_status = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                title,
                product_name,
                assigned_reviewer,
                assigned_approver,
                _to_json(context),
                _to_json(approval_context),
                _to_json(drafts),
                json.dumps(review_comments, default=str),
                full_report_text,
                workflow_status,
                now,
                report_id,
            ),
        )
        conn.execute("DELETE FROM workflow_events WHERE report_id = ?", (report_id,))
        conn.executemany(
            """
            INSERT INTO workflow_events (
                report_id, timestamp, role, actor, action, comment
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    report_id,
                    event.get("timestamp", ""),
                    event.get("role", ""),
                    event.get("actor", ""),
                    event.get("action", ""),
                    event.get("comment", ""),
                )
                for event in workflow_history
            ],
        )
