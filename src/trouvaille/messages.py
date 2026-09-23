"""Provider-independent conversation records."""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal, Mapping


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


def message_to_dict(message: Message) -> dict[str, Any]:
    """Encode every provider-independent field needed to replay a Message."""

    return {
        "role": message.role,
        "content": message.content,
        "tool_calls": [
            {
                "call_id": call.call_id,
                "name": call.name,
                "arguments": deepcopy(call.arguments),
            }
            for call in message.tool_calls
        ],
        "tool_call_id": message.tool_call_id,
        "output_items": deepcopy(list(message.output_items)),
        "model_status": message.model_status,
    }


def message_from_dict(data: Any) -> Message:
    """Decode a Session message and reject malformed field structures."""

    if not isinstance(data, Mapping):
        raise ValueError("Message must be a JSON object")
    required = {
        "role",
        "content",
        "tool_calls",
        "tool_call_id",
        "output_items",
        "model_status",
    }
    if set(data) != required:
        missing = sorted(required - set(data))
        unknown = sorted(set(data) - required)
        raise ValueError(f"Invalid Message fields: missing={missing}, unknown={unknown}")

    role = data["role"]
    if role not in {"system", "user", "assistant", "tool"}:
        raise ValueError(f"Invalid Message role: {role!r}")
    content = data["content"]
    if not isinstance(content, str):
        raise ValueError("Message content must be a string")

    raw_calls = data["tool_calls"]
    if not isinstance(raw_calls, list):
        raise ValueError("Message tool_calls must be a list")
    calls: list[ToolCall] = []
    for raw_call in raw_calls:
        if not isinstance(raw_call, Mapping) or set(raw_call) != {"call_id", "name", "arguments"}:
            raise ValueError("Invalid ToolCall fields")
        call_id = raw_call["call_id"]
        name = raw_call["name"]
        if not isinstance(call_id, str) or not call_id:
            raise ValueError("ToolCall call_id must be a non-empty string")
        if not isinstance(name, str) or not name:
            raise ValueError("ToolCall name must be a non-empty string")
        calls.append(ToolCall(call_id, name, deepcopy(raw_call["arguments"])))

    tool_call_id = data["tool_call_id"]
    if tool_call_id is not None and not isinstance(tool_call_id, str):
        raise ValueError("Message tool_call_id must be a string or null")
    raw_output_items = data["output_items"]
    if not isinstance(raw_output_items, list) or not all(
        isinstance(item, dict) for item in raw_output_items
    ):
        raise ValueError("Message output_items must be a list of objects")
    model_status = data["model_status"]
    if model_status is not None and not isinstance(model_status, str):
        raise ValueError("Message model_status must be a string or null")

    return Message(
        role=role,
        content=content,
        tool_calls=tuple(calls),
        tool_call_id=tool_call_id,
        output_items=tuple(deepcopy(raw_output_items)),
        model_status=model_status,
    )
