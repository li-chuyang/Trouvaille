"""Plain-text CLI for the coding agent."""

import argparse
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import readline  # Enables Unicode-aware editing for input() on macOS/libedit.
except ImportError:
    pass  # readline is optional on some platforms.

from dotenv import load_dotenv

from trouvaille.agent import Agent, AgentEvent
from trouvaille.config import AppConfig
from trouvaille.context import ContextManager, ModelContextSummarizer
from trouvaille.conversation import Conversation
from trouvaille.lifecycle import LifecycleHooks
from trouvaille.model import ModelConfig, OpenAIModel
from trouvaille.session import Session, SessionError, SessionInfo, SessionStore
from trouvaille.tools import default_tools
from trouvaille.trajectory import save_trajectory
from trouvaille.workspace import Workspace


def _short(value: Any, limit: int = 120) -> str:
    text = str(value).replace("\n", "\\n")
    return text if len(text) <= limit else text[:limit] + "..."


def _arguments(arguments: Any) -> str:
    if not isinstance(arguments, dict):
        return "invalid arguments"
    fields = []
    for key, value in arguments.items():
        if key in {"content", "old_text", "new_text"}:
            fields.append(f"{key}=<{len(str(value))} chars>")
        else:
            fields.append(f"{key}={_short(value)!r}")
    return ", ".join(fields)


_LOGO = (
    r" _____ ____   ___  _   ___     ___    ___ _     _     _____",
    r"|_   _|  _ \ / _ \| | | \ \   / / \  |_ _| |   | |   | ____|",
    r"  | | | |_) | | | | | | |\ \ / / _ \  | || |   | |   |  _|",
    r"  | | |  _ <| |_| | |_| | \ V / ___ \ | || |___| |___| |___",
    r"  |_| |_| \_\\___/ \___/   \_/_/   \_\___|_____|_____|_____|",
)


class CliRenderer:
    """Small terminal presentation layer driven by AgentEvent."""

    def __init__(self, *, color: bool) -> None:
        self.color = color
        self.run_number = 0

    @classmethod
    def for_stdout(cls) -> "CliRenderer":
        enabled = (
            sys.stdout.isatty()
            and os.getenv("TERM", "") != "dumb"
            and "NO_COLOR" not in os.environ
        )
        return cls(color=enabled)

    def _paint(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.color else text

    def accent(self, text: str) -> str:
        return self._paint("36", text)

    def strong(self, text: str) -> str:
        return self._paint("1", text)

    def success(self, text: str) -> str:
        return self._paint("32", text)

    def failure(self, text: str) -> str:
        return self._paint("31", text)

    def muted(self, text: str) -> str:
        return self._paint("2", text)

    def banner(self, workspace: Path, model: str, max_steps: int) -> None:
        if not sys.stdout.isatty():
            return
        print()
        if shutil.get_terminal_size(fallback=(80, 24)).columns >= 72:
            for line in _LOGO:
                print(self.accent(line))
        print(self.accent(self.strong("  Trouvaille")))
        print()
        print(f"  {self.muted('Workspace')}  {workspace}")
        print(f"  {self.muted('Model')}      {model}")
        print(f"  {self.muted('Max steps')}  {max_steps}")
        print(f"  {self.muted('Type exit or quit to leave.')}")
        print()

    def start_run(self, task: str, *, show_user: bool) -> None:
        self.run_number += 1
        print()
        print(self.accent(f"╭─ Run {self.run_number}"))
        if show_user:
            print(f"│  {self.strong('User >')}")
            self._block(task)

    def event(self, event: AgentEvent) -> None:
        if event.kind == "step":
            print(f"│\n├─ {self.accent(self.strong(f'Step {event.step}'))}")
        elif event.kind == "tool_call" and event.call:
            arguments = _arguments(event.call.arguments)
            print(f"│  {self.accent('Tool >')} {event.call.name}({arguments})")
        elif event.kind == "tool_result" and event.result:
            preview = event.result.error or event.result.output or "(no output)"
            if event.result.ok:
                label = self.success("OK")
            else:
                label = self.failure("FAILED")
            print(f"│    {label}  {_short(preview, 160)}")

    def result(self, status: str, answer: str | None, error: str | None) -> None:
        print("│")
        if status == "completed":
            print(f"├─ {self.accent(self.strong('Agent >'))}")
            self._block(answer or "")
        else:
            print(f"├─ {self.failure(self.strong('Error >'))}")
            self._block(error or status)

    def trace(self, path: Path) -> None:
        print(self.muted(f"╰─ Trace > {path}"))

    def trace_error(self, error: OSError) -> None:
        print(f"╰─ {self.failure('Error >')} Could not save trajectory: {error}")

    def session_error(self, error: SessionError) -> None:
        print(f"╰─ {self.failure('Error >')} {error}")

    @staticmethod
    def _block(text: str) -> None:
        lines = str(text).splitlines() or [""]
        for line in lines:
            print(f"│  {line}")


def _display_session_time(info: SessionInfo) -> str:
    timestamp = datetime.fromisoformat(info.updated_at.replace("Z", "+00:00"))
    return timestamp.astimezone().strftime("%m-%d %H:%M")


def _pick_session(store: SessionStore) -> Session:
    if not sys.stdin.isatty():
        raise SessionError("--resume needs an interactive terminal; pass a full session id instead")
    sessions = store.list_sessions()
    if not sessions:
        raise SessionError("No saved sessions exist for this workspace")
    print("\nSaved sessions")
    for index, info in enumerate(sessions, 1):
        print(f"{index}. {_display_session_time(info)}  {info.title}")
        print(f"   {info.run_count} runs · {info.session_id[:8]}")
    try:
        selection = input("Select session > ").strip()
    except EOFError as exc:
        raise SessionError("Session selection ended before a choice was made") from exc
    if not selection.isdigit() or not 1 <= int(selection) <= len(sessions):
        raise SessionError(f"Invalid session selection: {selection!r}")
    return store.load(sessions[int(selection) - 1].session_id)


def main() -> int:
    parser = argparse.ArgumentParser(prog="trouvaille", description="Trouvaille interactive coding agent")
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="Workspace directory (default: current directory)")
    parser.add_argument("--max-steps", type=int, default=10, help="Maximum model calls per task")
    parser.add_argument("--task", help="Run one task and exit instead of opening interactive mode")
    session_group = parser.add_mutually_exclusive_group()
    session_group.add_argument(
        "--resume",
        nargs="?",
        const="",
        metavar="SESSION_ID",
        help="Resume a saved session by id, or open the interactive picker",
    )
    session_group.add_argument(
        "--continue",
        dest="continue_latest",
        action="store_true",
        help="Resume the most recently updated session",
    )
    args = parser.parse_args()
    if args.task is not None and (args.resume is not None or args.continue_latest):
        parser.error("--task cannot be combined with --resume or --continue")

    load_dotenv(Path.cwd() / ".env")
    try:
        app_config = AppConfig(workspace_root=args.workspace)
        workspace = Workspace(app_config.workspace_root)
    except (ValueError, OSError) as exc:
        print(f"Error > {exc}")
        return 2

    session_store: SessionStore | None = None
    session: Session | None = None
    if args.task is None:
        session_store = SessionStore(workspace)
        try:
            if args.resume == "":
                session = _pick_session(session_store)
            elif args.resume is not None:
                session = session_store.load(args.resume)
            elif args.continue_latest:
                session = session_store.latest()
                if session is None:
                    raise SessionError("No saved sessions exist for this workspace")
            else:
                session = session_store.create()
        except SessionError as exc:
            print(f"Error > {exc}")
            return 2

    if not os.getenv("OPENAI_API_KEY"):
        print("Error > OPENAI_API_KEY is missing. Set it in the environment or a local .env file.")
        return 2
    try:
        config = ModelConfig.from_env()
        model = OpenAIModel(config)
        hooks = LifecycleHooks()
        context_manager = ContextManager(ModelContextSummarizer(model))
        hooks.add_before_model(context_manager.prepare)
        agent = Agent(model, default_tools(workspace), workspace, max_steps=args.max_steps, hooks=hooks)
        conversation = Conversation(agent, history=session.messages if session is not None else ())
    except (ValueError, OSError) as exc:
        print(f"Error > {exc}")
        return 2

    renderer = CliRenderer.for_stdout()
    renderer.banner(workspace.root, config.model, args.max_steps)

    def run_task(task: str, *, show_user: bool) -> int:
        nonlocal session
        renderer.start_run(task, show_user=show_user)
        result = conversation.run(task, on_event=renderer.event)
        renderer.result(result.status, result.final_answer, result.error)
        persistence_failed = False
        try:
            path = save_trajectory(task, workspace, result)
            renderer.trace(path)
        except OSError as exc:
            renderer.trace_error(exc)
            persistence_failed = True
        if session is not None and session_store is not None:
            try:
                session = session.after_run(conversation.history)
                session_store.save(session)
            except SessionError as exc:
                renderer.session_error(exc)
                persistence_failed = True
        return 0 if result.status == "completed" and not persistence_failed else 1

    try:
        if args.task is not None:
            return run_task(args.task, show_user=True) if args.task.strip() else 2
        while True:
            try:
                task = input("User > ").strip()
            except EOFError:
                print()
                return 0
            if task.lower() in {"exit", "quit"}:
                return 0
            if task:
                run_task(task, show_user=False)
    except KeyboardInterrupt:
        print("\nError > Interrupted")
        return 130
