"""Small synchronous lifecycle extension points for the Agent Loop."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from trouvaille.messages import Message, ToolCall
from trouvaille.model import ModelResponse
from trouvaille.tools import ToolResult

if TYPE_CHECKING:
    from trouvaille.agent import RunResult
    from trouvaille.task_state import TaskState


@dataclass(frozen=True)
class ModelCallContext:
    task: str
    step: int
    messages: tuple[Message, ...]
    tool_schemas: tuple[dict[str, Any], ...]
    current_run_start: int = 1


@dataclass(frozen=True)
class ToolCallContext:
    task: str
    step: int
    call: ToolCall


@dataclass(frozen=True)
class ToolDecision:
    allowed: bool
    reason: str | None = None

    @classmethod
    def allow(cls) -> "ToolDecision":
        return cls(allowed=True)

    @classmethod
    def block(cls, reason: str) -> "ToolDecision":
        if not reason.strip():
            raise ValueError("A blocked tool decision requires a reason")
        return cls(allowed=False, reason=reason)


@dataclass(frozen=True)
class FinishContext:
    task: str
    step: int
    candidate_answer: str
    state: "TaskState"


@dataclass(frozen=True)
class FinishDecision:
    allowed: bool
    reason: str | None = None
    status: str | None = None

    @classmethod
    def allow(cls, reason: str | None = None, *, status: str | None = None) -> "FinishDecision":
        return cls(allowed=True, reason=reason, status=status)

    @classmethod
    def block(cls, reason: str, *, status: str | None = None) -> "FinishDecision":
        if not reason.strip():
            raise ValueError("A blocked finish decision requires a reason")
        return cls(allowed=False, reason=reason, status=status)


class LifecycleHookError(RuntimeError):
    def __init__(self, phase: str, position: int, error: Exception) -> None:
        self.phase = phase
        self.position = position
        self.original_error = error
        super().__init__(f"{phase} hook #{position} failed: {type(error).__name__}: {error}")


BeforeModelHook = Callable[[ModelCallContext], ModelCallContext]
AfterModelHook = Callable[[ModelCallContext, ModelResponse], None]
BeforeToolHook = Callable[[ToolCallContext], ToolDecision | None]
AfterToolHook = Callable[[ToolCallContext, ToolResult], None]
BeforeFinishHook = Callable[[FinishContext], FinishDecision | None]
AfterRunHook = Callable[["RunResult"], None]


class LifecycleHooks:
    """Ordered synchronous hooks injected into one Agent instance."""

    def __init__(self) -> None:
        self._before_model: list[BeforeModelHook] = []
        self._after_model: list[AfterModelHook] = []
        self._before_tool: list[BeforeToolHook] = []
        self._after_tool: list[AfterToolHook] = []
        self._before_finish: list[BeforeFinishHook] = []
        self._after_run: list[AfterRunHook] = []

    def add_before_model(self, hook: BeforeModelHook) -> None:
        self._before_model.append(hook)

    def add_after_model(self, hook: AfterModelHook) -> None:
        self._after_model.append(hook)

    def add_before_tool(self, hook: BeforeToolHook) -> None:
        self._before_tool.append(hook)

    def add_after_tool(self, hook: AfterToolHook) -> None:
        self._after_tool.append(hook)

    def add_before_finish(self, hook: BeforeFinishHook) -> None:
        self._before_finish.append(hook)

    def add_after_run(self, hook: AfterRunHook) -> None:
        self._after_run.append(hook)

    def run_before_model(self, context: ModelCallContext) -> ModelCallContext:
        current = context
        for position, hook in enumerate(self._before_model, 1):
            try:
                current = hook(current)
                if not isinstance(current, ModelCallContext):
                    raise TypeError("before_model must return ModelCallContext")
            except Exception as exc:
                self._raise("before_model", position, exc)
        return current

    def run_after_model(self, context: ModelCallContext, response: ModelResponse) -> None:
        self._run_observers("after_model", self._after_model, context, response)

    def run_before_tool(self, context: ToolCallContext) -> ToolDecision:
        for position, hook in enumerate(self._before_tool, 1):
            try:
                decision = hook(context)
                if decision is None or decision.allowed:
                    continue
                return decision
            except Exception as exc:
                self._raise("before_tool", position, exc)
        return ToolDecision.allow()

    def run_after_tool(self, context: ToolCallContext, result: ToolResult) -> None:
        self._run_observers("after_tool", self._after_tool, context, result)

    def run_before_finish(self, context: FinishContext) -> FinishDecision:
        outcome = FinishDecision.allow()
        for position, hook in enumerate(self._before_finish, 1):
            try:
                decision = hook(context)
                if decision is None:
                    continue
                if not isinstance(decision, FinishDecision):
                    raise TypeError("before_finish must return FinishDecision or None")
                if not decision.allowed:
                    return decision
                if decision.reason is not None or decision.status is not None:
                    outcome = decision
            except Exception as exc:
                self._raise("before_finish", position, exc)
        return outcome

    def run_after_run(self, result: "RunResult") -> None:
        self._run_observers("after_run", self._after_run, result)

    def _run_observers(self, phase: str, hooks: list[Callable[..., None]], *args: Any) -> None:
        for position, hook in enumerate(hooks, 1):
            try:
                hook(*args)
            except Exception as exc:
                self._raise(phase, position, exc)

    @staticmethod
    def _raise(phase: str, position: int, error: Exception) -> None:
        if isinstance(error, LifecycleHookError):
            raise error
        raise LifecycleHookError(phase, position, error) from error
