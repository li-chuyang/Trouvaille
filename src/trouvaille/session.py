"""Workspace-scoped persistent conversation Sessions."""

import json
import os
import re
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

from trouvaille.messages import Message, message_from_dict, message_to_dict
from trouvaille.workspace import Workspace


SCHEMA_VERSION = 1
TITLE_MAX_LENGTH = 80
_SESSION_ID = re.compile(r"[0-9a-f]{32}")


class SessionError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise SessionError(f"Session {field} must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SessionError(f"Session {field} is not a valid timestamp") from exc
    if parsed.tzinfo is None:
        raise SessionError(f"Session {field} must include a timezone")
    return parsed


def title_from_first_user_message(messages: Sequence[Message]) -> str:
    first_user = next((message.content for message in messages if message.role == "user"), "")
    normalized = " ".join(first_user.split())
    if not normalized:
        raise SessionError("Session history has no non-empty user message for its title")
    if len(normalized) <= TITLE_MAX_LENGTH:
        return normalized
    return normalized[: TITLE_MAX_LENGTH - 3].rstrip() + "..."


@dataclass(frozen=True)
class Session:
    schema_version: int
    session_id: str
    title: str
    created_at: str
    updated_at: str
    run_count: int
    messages: tuple[Message, ...]

    @classmethod
    def new(cls) -> "Session":
        now = _utc_now()
        return cls(SCHEMA_VERSION, uuid4().hex, "", now, now, 0, ())

    def after_run(self, messages: Sequence[Message]) -> "Session":
        history = tuple(messages)
        _validate_history(history)
        title = self.title or title_from_first_user_message(history)
        return replace(
            self,
            title=title,
            updated_at=_utc_now(),
            run_count=self.run_count + 1,
            messages=history,
        )

    def info(self) -> "SessionInfo":
        return SessionInfo(
            session_id=self.session_id,
            title=self.title,
            created_at=self.created_at,
            updated_at=self.updated_at,
            run_count=self.run_count,
        )


@dataclass(frozen=True)
class SessionInfo:
    session_id: str
    title: str
    created_at: str
    updated_at: str
    run_count: int


class SessionStore:
    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.directory = workspace.internal_path("sessions")

    def create(self) -> Session:
        return Session.new()

    def save(self, session: Session) -> Path:
        document = _session_to_dict(session)
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self._path(session.session_id)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.directory,
            prefix=f".{session.session_id}-",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(document, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        except (OSError, TypeError, ValueError) as exc:
            temporary.unlink(missing_ok=True)
            raise SessionError(f"Could not save session {session.session_id}: {exc}") from exc
        return target

    def load(self, session_id: str) -> Session:
        path = self._path(session_id)
        if not path.is_file():
            raise SessionError(f"Session not found: {session_id}")
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            return _session_from_dict(document)
        except SessionError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise SessionError(f"Could not load session {session_id}: {exc}") from exc

    def list_sessions(self) -> tuple[SessionInfo, ...]:
        if not self.directory.exists():
            return ()
        sessions = []
        for path in self.directory.glob("*.json"):
            try:
                sessions.append(self.load(path.stem).info())
            except SessionError as exc:
                raise SessionError(f"Invalid session file {path.name}: {exc}") from exc
        sessions.sort(
            key=lambda item: _parse_timestamp(item.updated_at, "updated_at"),
            reverse=True,
        )
        return tuple(sessions)

    def latest(self) -> Session | None:
        sessions = self.list_sessions()
        return self.load(sessions[0].session_id) if sessions else None

    def _path(self, session_id: str) -> Path:
        if not isinstance(session_id, str) or _SESSION_ID.fullmatch(session_id) is None:
            raise SessionError(f"Invalid session id: {session_id!r}")
        return self.workspace.internal_path("sessions", f"{session_id}.json")


def _validate_history(messages: Sequence[Message]) -> None:
    if not all(isinstance(message, Message) for message in messages):
        raise SessionError("Session history must contain Message values")
    if any(message.role == "system" for message in messages):
        raise SessionError("Session history must not contain system messages")


def _session_to_dict(session: Session) -> dict[str, Any]:
    _validate_session(session)
    return {
        "schema_version": session.schema_version,
        "session_id": session.session_id,
        "title": session.title,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "run_count": session.run_count,
        "messages": [message_to_dict(message) for message in session.messages],
    }


def _session_from_dict(data: Any) -> Session:
    if not isinstance(data, dict):
        raise SessionError("Session document must be a JSON object")
    required = {
        "schema_version",
        "session_id",
        "title",
        "created_at",
        "updated_at",
        "run_count",
        "messages",
    }
    if set(data) != required:
        missing = sorted(required - set(data))
        unknown = sorted(set(data) - required)
        raise SessionError(f"Invalid Session fields: missing={missing}, unknown={unknown}")
    if (
        not isinstance(data["schema_version"], int)
        or isinstance(data["schema_version"], bool)
        or data["schema_version"] != SCHEMA_VERSION
    ):
        raise SessionError(f"Unsupported Session schema version: {data['schema_version']!r}")
    raw_messages = data["messages"]
    if not isinstance(raw_messages, list):
        raise SessionError("Session messages must be a list")
    try:
        messages = tuple(message_from_dict(message) for message in raw_messages)
    except (TypeError, ValueError) as exc:
        raise SessionError(f"Invalid Session message: {exc}") from exc
    session = Session(
        schema_version=data["schema_version"],
        session_id=data["session_id"],
        title=data["title"],
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        run_count=data["run_count"],
        messages=messages,
    )
    _validate_session(session)
    return session


def _validate_session(session: Session) -> None:
    if (
        not isinstance(session.schema_version, int)
        or isinstance(session.schema_version, bool)
        or session.schema_version != SCHEMA_VERSION
    ):
        raise SessionError(f"Unsupported Session schema version: {session.schema_version!r}")
    if not isinstance(session.session_id, str) or _SESSION_ID.fullmatch(session.session_id) is None:
        raise SessionError(f"Invalid session id: {session.session_id!r}")
    if not isinstance(session.title, str) or not session.title.strip():
        raise SessionError("Persisted Session title must not be empty")
    if not isinstance(session.run_count, int) or isinstance(session.run_count, bool) or session.run_count < 1:
        raise SessionError("Persisted Session run_count must be a positive integer")
    created = _parse_timestamp(session.created_at, "created_at")
    updated = _parse_timestamp(session.updated_at, "updated_at")
    if updated < created:
        raise SessionError("Session updated_at must not precede created_at")
    _validate_history(session.messages)
