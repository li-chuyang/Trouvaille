"""Small operational state for one agent run."""

from dataclasses import dataclass, replace
from typing import Literal

from trouvaille.messages import ToolCall
from trouvaille.tools import ToolResult


TaskStatus = Literal[
    "running",
    "completed",
    "max_steps",
    "provider_error",
    "lifecycle_error",
    "verification_failed",
]


@dataclass(frozen=True)
class CommandOutcome:
    tool: Literal["shell", "git_diff", "verify"]
    command: str
    ok: bool
    exit_code: int | None
    operation_index: int


@dataclass(frozen=True)
class TaskState:
    goal: str
    status: TaskStatus = "running"
    current_step: int = 0
    files_inspected: tuple[str, ...] = ()
    files_modified: tuple[str, ...] = ()
    commands: tuple[CommandOutcome, ...] = ()
    errors: tuple[str, ...] = ()
    operation_index: int = 0
    last_modification_index: int | None = None

    def at_step(self, step: int) -> "TaskState":
        return replace(self, current_step=step)

    def after_tool(self, call: ToolCall, result: ToolResult) -> "TaskState":
        arguments = call.arguments if isinstance(call.arguments, dict) else {}
        path = arguments.get("path")
        inspected = self.files_inspected
        modified = self.files_modified
        commands = self.commands
        errors = self.errors
        operation_index = self.operation_index + 1
        last_modification_index = self.last_modification_index

        if result.ok and isinstance(path, str):
            if call.name == "read_file" and path not in inspected:
                inspected += (path,)
            elif call.name in {"write_file", "edit_file"}:
                if path not in modified:
                    modified += (path,)
                last_modification_index = operation_index

        if call.name in {"shell", "verify", "git_diff"}:
            command = (
                arguments.get("command", "")
                if call.name in {"shell", "verify"}
                else f"git diff -- {arguments.get('path', '.')}"
            )
            commands += (
                CommandOutcome(
                    call.name,
                    str(command),
                    result.ok,
                    result.exit_code,
                    operation_index,
                ),
            )

        if not result.ok:
            errors += (f"{call.name}: {result.error or 'Tool failed'}",)

        return replace(
            self,
            files_inspected=inspected,
            files_modified=modified,
            commands=commands,
            errors=errors,
            operation_index=operation_index,
            last_modification_index=last_modification_index,
        )

    def finish(self, status: TaskStatus, error: str | None = None) -> "TaskState":
        errors = self.errors + ((error,) if error else ())
        return replace(self, status=status, errors=errors)
