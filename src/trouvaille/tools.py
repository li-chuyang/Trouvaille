"""Minimal tool registry and workspace-bound tools."""

from dataclasses import dataclass
from subprocess import TimeoutExpired
from typing import Any, Callable

from trouvaille.execution import ExecutionBackend, LocalExecutionBackend
from trouvaille.workspace import AgentWorkspaceView, Workspace


@dataclass(frozen=True)
class ToolResult:
    name: str
    ok: bool
    output: str = ""
    error: str | None = None
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    run: Callable[..., ToolResult]

    def schema(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.parameters}


class ToolRegistry:
    def __init__(self, tools: list[Tool]):
        self._tools = {tool.name: tool for tool in tools}
        if len(self._tools) != len(tools):
            raise ValueError("Duplicate tool name")

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    def dispatch(self, name: str, arguments: Any) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(name=name, ok=False, error=f"Unknown tool: {name}")
        try:
            _validate(arguments, tool.parameters)
            return tool.run(**arguments)
        except (OSError, ValueError, TypeError, UnicodeError, TimeoutExpired) as exc:
            return ToolResult(name=name, ok=False, error=f"{type(exc).__name__}: {exc}")


def _validate(arguments: Any, schema: dict[str, Any]) -> None:
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be an object")
    properties = schema["properties"]
    missing = set(schema.get("required", [])) - arguments.keys()
    unknown = arguments.keys() - properties.keys()
    if missing or unknown:
        raise ValueError(f"Invalid arguments: missing={sorted(missing)}, unknown={sorted(unknown)}")
    for key, value in arguments.items():
        expected = schema["properties"][key]["type"]
        if expected != "string" or not isinstance(value, str):
            raise ValueError(f"Argument {key} must be a string")


def _parameters(required: tuple[str, ...], optional: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {name: {"type": "string"} for name in (*required, *optional)},
        "required": list(required),
        "additionalProperties": False,
    }


def default_tools(
    workspace: Workspace,
    *,
    shell_timeout: int = 30,
    execution_backend: ExecutionBackend | None = None,
) -> ToolRegistry:
    if shell_timeout <= 0:
        raise ValueError("shell_timeout must be positive")
    agent_workspace = AgentWorkspaceView(workspace)
    backend = execution_backend if execution_backend is not None else LocalExecutionBackend()

    def list_files(path: str = ".") -> ToolResult:
        names = [entry.name + ("/" if entry.is_dir() else "") for entry in agent_workspace.iterdir(path)]
        return ToolResult(name="list_files", ok=True, output="\n".join(sorted(names)))

    def read_file(path: str) -> ToolResult:
        target = agent_workspace.resolve(path)
        return ToolResult(name="read_file", ok=True, output=target.read_text(encoding="utf-8"))

    def write_file(path: str, content: str) -> ToolResult:
        target = agent_workspace.resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return ToolResult(name="write_file", ok=True, output=f"Wrote {path}")

    def edit_file(path: str, old_text: str, new_text: str) -> ToolResult:
        target = agent_workspace.resolve(path)
        content = target.read_text(encoding="utf-8")
        count = content.count(old_text)
        if not old_text or count != 1:
            raise ValueError(f"Expected exactly one non-empty match in {path}; found {count}")
        target.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
        return ToolResult(name="edit_file", ok=True, output=f"Edited {path}")

    def search(pattern: str, path: str = ".") -> ToolResult:
        matches: list[str] = []
        for file in agent_workspace.iter_files(
            path,
            excluded_directories=frozenset({".git", ".venv"}),
        ):
            try:
                lines = file.read_text(encoding="utf-8").splitlines()
            except (UnicodeError, OSError):
                continue
            for number, line in enumerate(lines, 1):
                if pattern in line:
                    matches.append(f"{file.relative_to(agent_workspace.root)}:{number}:{line}")
        return ToolResult(name="search", ok=True, output="\n".join(matches))

    def shell(command: str) -> ToolResult:
        completed = backend.run(
            command,
            cwd=workspace.root,
            timeout=shell_timeout,
            shell=True,
        )
        return ToolResult(
            name="shell",
            ok=completed.exit_code == 0,
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.exit_code,
            output=completed.stdout + completed.stderr,
            error=None if completed.exit_code == 0 else f"Exit code: {completed.exit_code}",
        )

    def git_diff(path: str = ".") -> ToolResult:
        target = agent_workspace.resolve(path)
        relative = target.relative_to(workspace.root)
        completed = backend.run(
            ["git", "diff", "--no-ext-diff", "--", str(relative)],
            cwd=workspace.root,
            timeout=shell_timeout,
            shell=False,
        )
        return ToolResult(
            name="git_diff",
            ok=completed.exit_code == 0,
            output=completed.stdout + completed.stderr,
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.exit_code,
            error=None if completed.exit_code == 0 else f"Exit code: {completed.exit_code}",
        )

    return ToolRegistry([
        Tool("list_files", "List entries in a workspace directory.", _parameters((), ("path",)), list_files),
        Tool("read_file", "Read a UTF-8 workspace file.", _parameters(("path",)), read_file),
        Tool("write_file", "Write a UTF-8 workspace file.", _parameters(("path", "content")), write_file),
        Tool("edit_file", "Replace one exact text match in a UTF-8 workspace file.", _parameters(("path", "old_text", "new_text")), edit_file),
        Tool("search", "Find a literal string in workspace files.", _parameters(("pattern",), ("path",)), search),
        Tool("shell", "Run a shell command in the workspace.", _parameters(("command",)), shell),
        Tool("git_diff", "Show unstaged Git changes in the workspace.", _parameters((), ("path",)), git_diff),
    ])
