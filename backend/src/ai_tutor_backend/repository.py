from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from .models import ExecutionResult


class ResultNotFoundError(KeyError):
    pass


@dataclass(frozen=True, slots=True)
class StoredCodeSubmission:
    request_id: str
    case_id: str
    student_id: str | None
    filename: str
    source_code: str
    created_at: str


class SQLiteResultRepository:
    """Small persistent store suitable for a single backend instance."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_results (
                request_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                document TEXT NOT NULL
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS code_submissions (
                request_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                student_id TEXT,
                filename TEXT NOT NULL,
                source_code TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_code_submissions_case
            ON code_submissions(case_id, created_at)
            """
        )
        self._connection.commit()

    def save(self, result: ExecutionResult) -> None:
        document = result.model_dump_json()
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO execution_results(request_id, case_id, status, created_at, document)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    case_id = excluded.case_id,
                    status = excluded.status,
                    created_at = excluded.created_at,
                    document = excluded.document
                """,
                (
                    result.request_id,
                    result.case_id,
                    result.status.value,
                    result.created_at.isoformat(),
                    document,
                ),
            )

    def get(self, request_id: str) -> ExecutionResult:
        with self._lock:
            row = self._connection.execute(
                "SELECT document FROM execution_results WHERE request_id = ?", (request_id,)
            ).fetchone()
        if row is None:
            raise ResultNotFoundError(request_id)
        return ExecutionResult.model_validate_json(row[0])

    def save_code_submission(
        self,
        *,
        request_id: str,
        case_id: str,
        student_id: str | None,
        filename: str,
        source_code: str,
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO code_submissions(
                    request_id, case_id, student_id, filename, source_code, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO NOTHING
                """,
                (
                    request_id,
                    case_id,
                    student_id,
                    filename,
                    source_code,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def list_code_submissions(
        self,
        case_id: str,
        *,
        excluding_student_id: str | None = None,
    ) -> list[StoredCodeSubmission]:
        query = (
            "SELECT request_id, case_id, student_id, filename, source_code, created_at "
            "FROM code_submissions WHERE case_id = ?"
        )
        parameters: list[str] = [case_id]
        if excluding_student_id:
            query += " AND (student_id IS NULL OR student_id <> ?)"
            parameters.append(excluding_student_id)
        query += " ORDER BY created_at ASC"
        with self._lock:
            rows = self._connection.execute(query, parameters).fetchall()
        return [StoredCodeSubmission(*row) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._connection.close()
