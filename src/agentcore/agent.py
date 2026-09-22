"""The project's explicit model-tool-observation loop."""

import json
from dataclasses import asdict, dataclass
from typing import Callable, Literal

from agentcore.messages import Message, ToolCall
from agentcore.model import Model, ModelResponse
from agentcore.task_state import TaskState
from agentcore.tools import ToolRegistry, ToolResult
from agentcore.workspace import Workspace


@dataclass(frozen=True)
class RunResult:
    status: Literal["completed", "max_steps", "provider_error"]
    final_answer: str | None
    steps: int
    messages: tuple[Message, ...]
    error: str | None
    state: TaskState


@dataclass(frozen=True)
class AgentEvent:
    kind: Literal["step", "model", "tool_call", "tool_result", "final", "error"]
    step: int
    response: ModelResponse | None = None
    call: ToolCall | None = None
    result: ToolResult | None = None
    text: str | None = None


class Agent:
    def __init__(self, model: Model, tools: ToolRegistry, workspace: Workspace, *, max_steps: int = 10):
        if max_steps <= 0:
            raise ValueError("max_steps must be positive")
        self.model = model
        self.tools = tools
        self.workspace = workspace
        self.max_steps = max_steps

    def run(self, task: str, on_event: Callable[[AgentEvent], None] | None = None) -> RunResult:
        if not task.strip():
            raise ValueError("task must not be empty")

        def emit(event: AgentEvent) -> None:
            if on_event is not None:
                on_event(event)

        messages = [
            Message(role="system", content=f"You are a coding agent working in {self.workspace.root}. Use available tools when needed."),
            Message(role="user", content=task),
        ]
        state = TaskState(goal=task)
        for step in range(1, self.max_steps + 1):
            state = state.at_step(step)
            emit(AgentEvent("step", step))
            try:
                response = self.model.complete(messages.copy(), self.tools.schemas())
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                emit(AgentEvent("error", step, text=error))
                return RunResult("provider_error", None, step, tuple(messages), error, state.finish("provider_error", error))

            emit(AgentEvent("model", step, response=response))
            messages.append(Message(
                role="assistant",
                content=response.text,
                tool_calls=response.tool_calls,
                output_items=response.output_items,
                model_status=response.status,
            ))
            if response.status != "completed":
                error = f"Model response status: {response.status}"
                emit(AgentEvent("error", step, text=error))
                return RunResult("provider_error", None, step, tuple(messages), error, state.finish("provider_error", error))
            if not response.tool_calls:
                if response.text.strip():
                    emit(AgentEvent("final", step, text=response.text))
                    return RunResult("completed", response.text, step, tuple(messages), None, state.finish("completed"))
                error = "Model returned no answer or tool calls"
                emit(AgentEvent("error", step, text=error))
                return RunResult("provider_error", None, step, tuple(messages), error, state.finish("provider_error", error))

            for call in response.tool_calls:
                emit(AgentEvent("tool_call", step, call=call))
                result = self.tools.dispatch(call.name, call.arguments)
                state = state.after_tool(call, result)
                emit(AgentEvent("tool_result", step, call=call, result=result))
                messages.append(Message(
                    role="tool",
                    content=json.dumps(asdict(result), ensure_ascii=False),
                    tool_call_id=call.call_id,
                ))

        error = "Maximum model steps reached"
        emit(AgentEvent("error", self.max_steps, text=error))
        return RunResult("max_steps", None, self.max_steps, tuple(messages), error, state.finish("max_steps", error))
