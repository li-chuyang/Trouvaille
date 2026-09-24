"""The project's explicit model-tool-observation loop."""

import json
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Callable, Literal, Sequence

from trouvaille.lifecycle import (
    FinishContext,
    LifecycleHookError,
    LifecycleHooks,
    ModelCallContext,
    ToolCallContext,
)
from trouvaille.messages import Message, ToolCall
from trouvaille.model import Model, ModelResponse
from trouvaille.task_state import TaskState
from trouvaille.tools import ToolRegistry, ToolResult
from trouvaille.workspace import Workspace


@dataclass(frozen=True)
class CompletionCheck:
    step: int
    allowed: bool
    reason: str | None = None
    status: str | None = None


RunStatus = Literal[
    "completed",
    "max_steps",
    "provider_error",
    "lifecycle_error",
    "verification_failed",
]


@dataclass(frozen=True)
class RunResult:
    status: RunStatus
    final_answer: str | None
    steps: int
    messages: tuple[Message, ...]  # This Run only: system, current user, then its model/tool messages.
    error: str | None
    state: TaskState
    completion_checks: tuple[CompletionCheck, ...] = ()


@dataclass(frozen=True)
class AgentEvent:
    kind: Literal["step", "model", "tool_call", "tool_result", "finish_check", "final", "error"]
    step: int
    response: ModelResponse | None = None
    call: ToolCall | None = None
    result: ToolResult | None = None
    completion_check: CompletionCheck | None = None
    text: str | None = None


class Agent:
    def __init__(
        self,
        model: Model,
        tools: ToolRegistry,
        workspace: Workspace,
        *,
        max_steps: int = 10,
        hooks: LifecycleHooks | None = None,
    ):
        if max_steps <= 0:
            raise ValueError("max_steps must be positive")
        self.model = model
        self.tools = tools
        self.workspace = workspace
        self.max_steps = max_steps
        self.hooks = hooks if hooks is not None else LifecycleHooks()

    def run(
        self,
        task: str,
        on_event: Callable[[AgentEvent], None] | None = None,
        *,
        history: Sequence[Message] = (),
    ) -> RunResult:
        if not task.strip():
            raise ValueError("task must not be empty")

        def emit(event: AgentEvent) -> None:
            if on_event is not None:
                on_event(event)

        system = Message(
            role="system",
            content=(
                f"You are a coding agent working in {self.workspace.root}. Use available tools when needed. "
                "After modifying project files, run an appropriate command with the verify tool after the "
                "latest change before giving a final answer. If verification fails, fix the problem and "
                "verify again. A repository map may be provided as structural navigation data; use it to "
                "locate relevant code, but read exact source files before editing or relying on details."
            ),
        )
        user = Message(role="user", content=task)
        messages = [system, *history, user]
        run_messages = [system, user]
        completion_checks: list[CompletionCheck] = []

        def append(message: Message) -> None:
            messages.append(message)
            run_messages.append(message)

        def finish(
            status: RunStatus,
            steps: int,
            state: TaskState,
            *,
            answer: str | None = None,
            error: str | None = None,
        ) -> RunResult:
            result = RunResult(
                status,
                answer,
                steps,
                tuple(run_messages),
                error,
                state.finish(status, error),
                tuple(completion_checks),
            )
            try:
                self.hooks.run_after_run(result)
            except LifecycleHookError as exc:
                hook_error = str(exc)
                emit(AgentEvent("error", steps, text=hook_error))
                return RunResult(
                    "lifecycle_error",
                    None,
                    steps,
                    tuple(run_messages),
                    hook_error,
                    result.state.finish("lifecycle_error", hook_error),
                    tuple(completion_checks),
                )
            return result

        state = TaskState(goal=task)
        for step in range(1, self.max_steps + 1):
            state = state.at_step(step)
            emit(AgentEvent("step", step))
            try:
                model_context = ModelCallContext(
                    task=task,
                    step=step,
                    messages=deepcopy(tuple(messages)),
                    tool_schemas=deepcopy(tuple(self.tools.schemas())),
                    current_run_start=len(history) + 1,
                )
                model_context = self.hooks.run_before_model(model_context)
                response = self.model.complete(list(model_context.messages), list(model_context.tool_schemas))
            except Exception as exc:
                if isinstance(exc, LifecycleHookError):
                    error = str(exc)
                    status = "lifecycle_error"
                else:
                    error = f"{type(exc).__name__}: {exc}"
                    status = "provider_error"
                emit(AgentEvent("error", step, text=error))
                return finish(status, step, state, error=error)

            emit(AgentEvent("model", step, response=response))
            assistant_message = Message(
                role="assistant",
                content=response.text,
                tool_calls=response.tool_calls,
                output_items=response.output_items,
                model_status=response.status,
            )
            try:
                self.hooks.run_after_model(model_context, response)
            except LifecycleHookError as exc:
                error = str(exc)
                emit(AgentEvent("error", step, text=error))
                return finish("lifecycle_error", step, state, error=error)
            if response.status != "completed":
                append(assistant_message)
                error = f"Model response status: {response.status}"
                emit(AgentEvent("error", step, text=error))
                return finish("provider_error", step, state, error=error)
            if not response.tool_calls:
                if response.text.strip():
                    try:
                        decision = self.hooks.run_before_finish(FinishContext(
                            task=task,
                            step=step,
                            candidate_answer=response.text,
                            state=state,
                        ))
                    except LifecycleHookError as exc:
                        error = str(exc)
                        emit(AgentEvent("error", step, text=error))
                        return finish("lifecycle_error", step, state, error=error)
                    check = CompletionCheck(
                        step=step,
                        allowed=decision.allowed,
                        reason=decision.reason,
                        status=decision.status,
                    )
                    completion_checks.append(check)
                    emit(AgentEvent("finish_check", step, completion_check=check))
                    if decision.allowed:
                        append(assistant_message)
                        emit(AgentEvent("final", step, text=response.text))
                        return finish("completed", step, state, answer=response.text)

                    messages.append(assistant_message)
                    messages.append(Message(
                        role="system",
                        content=(
                            "[Verification feedback from Trouvaille runtime]\n\n"
                            "Completion was not accepted.\n\n"
                            f"Reason:\n{decision.reason}\n\n"
                            "Run an appropriate check using the verify tool. If it fails, diagnose and "
                            "fix the problem, then verify again after the latest change."
                        ),
                    ))
                    if step == self.max_steps:
                        error = decision.reason or "Completion was blocked by a finish hook"
                        emit(AgentEvent("error", step, text=error))
                        return finish("verification_failed", step, state, error=error)
                    continue
                append(assistant_message)
                error = "Model returned no answer or tool calls"
                emit(AgentEvent("error", step, text=error))
                return finish("provider_error", step, state, error=error)

            append(assistant_message)
            for call in response.tool_calls:
                emit(AgentEvent("tool_call", step, call=call))
                tool_context = ToolCallContext(task=task, step=step, call=call)
                try:
                    decision = self.hooks.run_before_tool(tool_context)
                except LifecycleHookError as exc:
                    error = str(exc)
                    emit(AgentEvent("error", step, text=error))
                    return finish("lifecycle_error", step, state, error=error)
                if decision.allowed:
                    result = self.tools.dispatch(call.name, call.arguments)
                else:
                    result = ToolResult(
                        name=call.name,
                        ok=False,
                        error=f"Blocked by lifecycle hook: {decision.reason}",
                    )
                state = state.after_tool(call, result)
                emit(AgentEvent("tool_result", step, call=call, result=result))
                append(Message(
                    role="tool",
                    content=json.dumps(asdict(result), ensure_ascii=False),
                    tool_call_id=call.call_id,
                ))
                try:
                    self.hooks.run_after_tool(tool_context, result)
                except LifecycleHookError as exc:
                    error = str(exc)
                    emit(AgentEvent("error", step, text=error))
                    return finish("lifecycle_error", step, state, error=error)

        error = "Maximum model steps reached"
        emit(AgentEvent("error", self.max_steps, text=error))
        return finish("max_steps", self.max_steps, state, error=error)
