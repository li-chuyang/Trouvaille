"""Small operational state for one agent run."""

from dataclasses import dataclass, replace
from typing import Literal

from agentcore.messages import ToolCall
from agentcore.tools import ToolResult


TaskStatus = Literal["running", "completed", "max_steps", "provider_error"]


@dataclass(frozen=True)
class CommandOutcome:
    tool: Literal["shell", "git_diff"]
    command: str
    ok: bool
    exit_code: int | None


@dataclass(frozen=True)
class TaskState:
    goal: str
    status: TaskStatus = "running"
    current_step: int = 0
    files_inspected: tuple[str, ...] = ()
    files_modified: tuple[str, ...] = ()
    commands: tuple[CommandOutcome, ...] = ()
    errors: tuple[str, ...] = ()

    def at_step(self, step: int) -> "TaskState":
        return replace(self, current_step=step)

    def after_tool(self, call: ToolCall, result: ToolResult) -> "TaskState":
        arguments = call.arguments if isinstance(call.arguments, dict) else {}
        path = arguments.get("path")
        inspected = self.files_inspected
        modified = self.files_modified
        commands = self.commands
        errors = self.errors

        if result.ok and isinstance(path, str):
            if call.name == "read_file" and path not in inspected:
                inspected += (path,)
            elif call.name in {"write_file", "edit_file"} and path not in modified:
                modified += (path,)

        if call.name in {"shell", "git_diff"}:
            command = arguments.get("command", "") if call.name == "shell" else f"git diff -- {arguments.get('path', '.')}"
            commands += (CommandOutcome(call.name, str(command), result.ok, result.exit_code),)

        if not result.ok:
            errors += (f"{call.name}: {result.error or 'Tool failed'}",)

        return replace(self, files_inspected=inspected, files_modified=modified, commands=commands, errors=errors)

    def finish(self, status: TaskStatus, error: str | None = None) -> "TaskState":
        errors = self.errors + ((error,) if error else ())
        return replace(self, status=status, errors=errors)
