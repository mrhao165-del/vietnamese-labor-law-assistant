"""Small SQLite repository for local, non-authenticated browser history."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal


class ConversationRepositoryError(RuntimeError):
    """Raised when the configured runtime database cannot be used safely."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ConversationRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS conversations (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 120),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS messages (
                        id TEXT PRIMARY KEY,
                        conversation_id TEXT NOT NULL REFERENCES conversations(id)
                            ON DELETE CASCADE,
                        role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                        content TEXT NOT NULL,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS feedback (
                        message_id TEXT PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
                        value TEXT NOT NULL CHECK(value IN ('up', 'down')),
                        note TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
                    ON messages(conversation_id, created_at);
                    """
                )
        except (OSError, sqlite3.Error) as exc:
            raise ConversationRepositoryError("runtime database is unavailable") from exc

    def list_conversations(self, limit: int = 50) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, title, created_at, updated_at FROM conversations "
                "ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_conversation(self, title: str) -> dict[str, str]:
        if not title.strip() or len(title) > 120:
            raise ValueError("conversation title is invalid")
        now, identifier = _now(), str(uuid.uuid4())
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO conversations(id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (identifier, title, now, now),
            )
        return {"id": identifier, "title": title, "created_at": now, "updated_at": now}

    def ensure_conversation(self, conversation_id: str | None, title: str) -> dict[str, str]:
        if conversation_id is None:
            return self.create_conversation(title)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
        if row is None:
            raise KeyError("conversation not found")
        return dict(row)

    def messages(self, conversation_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
            if exists is None:
                raise KeyError("conversation not found")
            rows = connection.execute(
                "SELECT m.id, m.conversation_id, m.role, m.content, m.metadata_json, "
                "m.created_at, f.value "
                "AS feedback FROM messages m LEFT JOIN feedback f ON f.message_id = m.id "
                "WHERE m.conversation_id = ? ORDER BY m.created_at ASC",
                (conversation_id,),
            ).fetchall()
        return [
            {
                **dict(row),
                "metadata": json.loads(str(row["metadata_json"])),
                "feedback": row["feedback"],
            }
            for row in rows
        ]

    def add_message(
        self,
        conversation_id: str,
        role: Literal["user", "assistant"],
        content: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        now, identifier = _now(), str(uuid.uuid4())
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO messages(id, conversation_id, role, content, metadata_json, "
                "created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    identifier,
                    conversation_id,
                    role,
                    content,
                    json.dumps(metadata, ensure_ascii=False),
                    now,
                ),
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id)
            )
        return {
            "id": identifier,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "metadata": metadata,
            "created_at": now,
            "feedback": None,
        }

    def delete_conversation(self, conversation_id: str) -> bool:
        with self._connect() as connection:
            deleted = connection.execute(
                "DELETE FROM conversations WHERE id = ?", (conversation_id,)
            ).rowcount
        return bool(deleted)

    def set_feedback(self, message_id: str, value: Literal["up", "down"], note: str | None) -> bool:
        if value not in {"up", "down"}:
            raise ValueError("feedback value is invalid")
        if note is not None and len(note) > 1000:
            raise ValueError("feedback note is too long")
        now = _now()
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM messages WHERE id = ?", (message_id,)
            ).fetchone()
            if exists is None:
                return False
            connection.execute(
                "INSERT INTO feedback(message_id, value, note, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(message_id) DO UPDATE SET "
                "value=excluded.value, note=excluded.note, "
                "updated_at=excluded.updated_at",
                (message_id, value, note, now, now),
            )
        return True

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
