"""Manual Phase 04 CLI scenarios using the configured OpenAI model."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
CLI = Path(sys.executable).with_name("my-agent")


def run_case(label: str, workspace: Path, task: str, required_tools: set[str]) -> str:
    completed = subprocess.run(
        [str(CLI), "--workspace", str(workspace), "--max-steps", "8", "--task", task],
        cwd=PROJECT,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(f"{label} failed (exit {completed.returncode}):\n{completed.stdout}\n{completed.stderr}")
    traces = sorted((workspace / ".agentcore" / "trajectories").glob("*.json"), key=lambda path: path.stat().st_mtime_ns)
    record = json.loads(traces[-1].read_text(encoding="utf-8"))
    used = {call["name"] for step in record["steps"] for call in step["tool_calls"]}
    if not required_tools <= used:
        raise AssertionError(f"{label} missed tools {required_tools - used}:\n{completed.stdout}")
    print(f"{label}: PASS ({len(record['steps'])} steps; tools: {', '.join(sorted(used))})")
    return record["final_answer"] or ""


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory)
        (workspace / "README.md").write_text("Temporary project\n", encoding="utf-8")
        (workspace / "src").mkdir()

        structure = run_case(
            "A directory structure",
            workspace,
            "Use list_files on the workspace root and src directory. Describe the structure, mentioning README.md and src/.",
            {"list_files"},
        )
        if "README.md" not in structure or "src" not in structure:
            raise AssertionError(f"A answer omitted structure: {structure}")

        created = run_case(
            "B create and run",
            workspace,
            "Use write_file to create hello.py containing exactly print('hello from agent') and a newline. Use shell to run python hello.py. Report its stdout.",
            {"write_file", "shell"},
        )
        if (workspace / "hello.py").read_text(encoding="utf-8") != "print('hello from agent')\n" or "hello from agent" not in created:
            raise AssertionError(f"B file or answer incorrect: {created}")

        edited = run_case(
            "C edit and verify",
            workspace,
            "Use edit_file to replace 'hello from agent' with 'hello after edit' in hello.py. Use shell to run python hello.py. Report its stdout.",
            {"edit_file", "shell"},
        )
        if (workspace / "hello.py").read_text(encoding="utf-8") != "print('hello after edit')\n" or "hello after edit" not in edited:
            raise AssertionError(f"C file or answer incorrect: {edited}")


if __name__ == "__main__":
    main()
