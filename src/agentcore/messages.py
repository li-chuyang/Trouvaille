"""Provider-independent conversation records."""

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: Any


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
    output_items: tuple[dict[str, Any], ...] = ()
    model_status: str | None = None
