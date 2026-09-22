"""Plain-text CLI for the coding agent."""

import argparse
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from agentcore.agent import Agent, AgentEvent
from agentcore.model import ModelConfig, OpenAIModel
from agentcore.tools import default_tools
from agentcore.trajectory import save_trajectory
from agentcore.workspace import Workspace


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


def _show_event(event: AgentEvent) -> None:
    if event.kind == "step":
        print(f"Step {event.step}")
    elif event.kind == "tool_call" and event.call:
        print(f"Tool > {event.call.name}({_arguments(event.call.arguments)})")
    elif event.kind == "tool_result" and event.result:
        state = "success" if event.result.ok else "failure"
        preview = event.result.error or event.result.output
        print(f"Result > {state}: {_short(preview, 160)}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="my-agent", description="Interactive coding agent")
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="Workspace directory (default: current directory)")
    parser.add_argument("--max-steps", type=int, default=10, help="Maximum model calls per task")
    parser.add_argument("--task", help="Run one task and exit instead of opening interactive mode")
    args = parser.parse_args()

    load_dotenv(Path.cwd() / ".env")
    try:
        workspace = Workspace(args.workspace)
    except (ValueError, OSError) as exc:
        print(f"Error > {exc}")
        return 2
    if not os.getenv("OPENAI_API_KEY"):
        print("Error > OPENAI_API_KEY is missing. Set it in the environment or a local .env file.")
        return 2
    try:
        config = ModelConfig.from_env()
        agent = Agent(OpenAIModel(config), default_tools(workspace), workspace, max_steps=args.max_steps)
    except (ValueError, OSError) as exc:
        print(f"Error > {exc}")
        return 2

    def run_task(task: str) -> int:
        result = agent.run(task, on_event=_show_event)
        if result.status == "completed":
            print(f"Agent > {result.final_answer}")
        else:
            print(f"Error > {result.error}")
        try:
            path = save_trajectory(task, workspace.root, result)
            print(f"Trace > {path}")
        except OSError as exc:
            print(f"Error > Could not save trajectory: {exc}")
            return 1
        return 0 if result.status == "completed" else 1

    try:
        if args.task is not None:
            return run_task(args.task) if args.task.strip() else 2
        while True:
            try:
                task = input("User > ").strip()
            except EOFError:
                print()
                return 0
            if task.lower() in {"exit", "quit"}:
                return 0
            if task:
                run_task(task)
    except KeyboardInterrupt:
        print("\nError > Interrupted")
        return 130
