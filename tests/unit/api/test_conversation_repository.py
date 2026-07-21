import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from vietnamese_labor_law_assistant.api.conversation_repository import (
    ConversationRepository,
    ConversationRepositoryError,
)


@pytest.fixture
def repository(tmp_path: Path) -> ConversationRepository:
    item = ConversationRepository(tmp_path / "runtime" / "app.sqlite3")
    item.initialize()
    item.initialize()
    return item


def test_schema_crud_order_messages_feedback_and_cascade(
    repository: ConversationRepository,
) -> None:
    first = repository.create_conversation("First")
    second = repository.create_conversation("Second")
    user = repository.add_message(first["id"], "user", "question", {})
    assistant = repository.add_message(
        first["id"], "assistant", "answer", {"route": "RETRIEVAL_ONLY"}
    )
    assert repository.list_conversations()[0]["id"] == first["id"]
    rows = repository.messages(first["id"])
    assert [item["role"] for item in rows] == ["user", "assistant"]
    assert rows[1]["metadata"]["route"] == "RETRIEVAL_ONLY"
    assert repository.set_feedback(assistant["id"], "up", "good")
    assert repository.set_feedback(assistant["id"], "down", None)
    assert repository.messages(first["id"])[1]["feedback"] == "down"
    assert repository.delete_conversation(first["id"])
    with pytest.raises(KeyError):
        repository.messages(first["id"])
    assert repository.ensure_conversation(second["id"], "ignored")["title"] == "Second"
    assert user["feedback"] is None


def test_repository_validates_inputs_and_unknown_ids(repository: ConversationRepository) -> None:
    with pytest.raises(ValueError):
        repository.create_conversation(" ")
    with pytest.raises(ValueError):
        repository.create_conversation("x" * 121)
    with pytest.raises(KeyError):
        repository.ensure_conversation("missing", "title")
    assert not repository.delete_conversation("missing")
    assert not repository.set_feedback("missing", "up", None)
    conversation = repository.create_conversation("safe ? quote")
    with pytest.raises(ValueError):
        repository.set_feedback(conversation["id"], "bad", None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        repository.set_feedback(conversation["id"], "up", "x" * 1001)


def test_runtime_directory_timestamps_and_foreign_keys(repository: ConversationRepository) -> None:
    conversation = repository.create_conversation("UTC")
    assert repository.database_path.is_file()
    assert datetime.fromisoformat(conversation["created_at"]).tzinfo == UTC
    with pytest.raises(sqlite3.IntegrityError):
        repository.add_message("not-a-conversation", "user", "x", {})


def test_unwritable_database_path_is_safe_error(tmp_path: Path) -> None:
    path = tmp_path / "file-parent"
    path.write_text("not a directory", encoding="utf-8")
    with pytest.raises(ConversationRepositoryError):
        ConversationRepository(path / "app.sqlite3").initialize()
