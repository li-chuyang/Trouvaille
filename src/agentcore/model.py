"""Single-call model interface and OpenAI Responses adapter."""

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol

from openai import OpenAI

from agentcore.messages import Message, ToolCall


@dataclass(frozen=True)
class ModelConfig:
    model: str
    api_key: str | None = None

    @classmethod
    def from_env(cls) -> "ModelConfig":
        model = os.getenv("OPENAI_MODEL")
        if not model:
            raise ValueError("OPENAI_MODEL is required")
        return cls(model=model, api_key=os.getenv("OPENAI_API_KEY"))


@dataclass(frozen=True)
class ModelResponse:
    text: str
    tool_calls: tuple[ToolCall, ...]
    status: str
    output_items: tuple[dict[str, Any], ...]


class Model(Protocol):
    def complete(self, messages: list[Message], tool_schemas: list[dict[str, Any]]) -> ModelResponse: ...


class OpenAIModel:
    def __init__(self, config: ModelConfig, client: Any = None):
        self.config = config
        self.client = client if client is not None else OpenAI(api_key=config.api_key)

    def complete(self, messages: list[Message], tool_schemas: list[dict[str, Any]]) -> ModelResponse:
        input_items: list[dict[str, Any]] = []
        for message in messages:
            if message.role in ("system", "user"):
                input_items.append({"role": message.role, "content": message.content})
            elif message.role == "assistant":
                input_items.extend(message.output_items)
            elif message.role == "tool":
                input_items.append({
                    "type": "function_call_output",
                    "call_id": message.tool_call_id,
                    "output": message.content,
                })
        tools = [
            {
                "type": "function",
                "name": schema["name"],
                "description": schema["description"],
                "parameters": schema["input_schema"],
                "strict": False,
            }
            for schema in tool_schemas
        ]
        response = self.client.responses.create(
            model=self.config.model,
            input=input_items,
            tools=tools,
            store=False,
        )
        calls = []
        for item in response.output:
            if item.type == "function_call":
                try:
                    arguments = json.loads(item.arguments)
                except json.JSONDecodeError:
                    arguments = item.arguments
                calls.append(ToolCall(call_id=item.call_id, name=item.name, arguments=arguments))
        return ModelResponse(
            text=response.output_text or "",
            tool_calls=tuple(calls),
            status=response.status,
            output_items=tuple(item.model_dump(mode="json", exclude_none=True) for item in response.output),
        )
