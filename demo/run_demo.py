"""Run a real end-to-end repair in a temporary copy of demo_workspace."""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT / "demo_workspace"
CLI = Path(sys.executable).with_name("my-agent")


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=180, check=False)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix=".demo-run-", dir=PROJECT) as directory:
        workspace = Path(directory)
        shutil.copytree(FIXTURE, workspace, dirs_exist_ok=True)
        for command in (
            ["git", "init", "-q"],
            ["git", "add", "README.md", "calculator.py", "test_calculator.py"],
            ["git", "-c", "user.name=Demo", "-c", "user.email=demo@example.invalid", "commit", "-q", "-m", "demo baseline"],
        ):
            completed = run(command, workspace)
            if completed.returncode:
                raise RuntimeError(f"Demo setup failed: {completed.stderr}")

        task = (
            "Use list_files to inspect this workspace. Use read_file to read calculator.py and test_calculator.py. "
            "The add function is wrong: fix it using edit_file. Use shell to run `python -m unittest -v` "
            "and verify tests pass. Use git_diff to review the change. Then summarize the fix and test result."
        )
        completed = run([str(CLI), "--workspace", str(workspace), "--max-steps", "10", "--task", task], PROJECT)
        if completed.returncode:
            raise RuntimeError(f"Agent demo failed:\n{completed.stdout}\n{completed.stderr}")

        traces = list((workspace / ".agentcore" / "trajectories").glob("*.json"))
        if len(traces) != 1:
            raise RuntimeError("Expected one demo trajectory")
        record = json.loads(traces[0].read_text(encoding="utf-8"))
        used = [call["name"] for step in record["steps"] for call in step["tool_calls"]]
        required = {"list_files", "read_file", "edit_file", "shell", "git_diff"}
        if not required <= set(used):
            raise RuntimeError(f"Demo missed required tools: {sorted(required - set(used))}\n{completed.stdout}")
        diff_call_ids = {
            call["call_id"] for step in record["steps"] for call in step["tool_calls"] if call["name"] == "git_diff"
        }
        diff_results = [
            item["result"] for step in record["steps"] for item in step["tool_results"]
            if item["call_id"] in diff_call_ids
        ]
        if not any(item["ok"] and "+    return a + b" in item["output"] for item in diff_results):
            raise RuntimeError("Agent git_diff observation did not contain the fix")
        if workspace.joinpath("calculator.py").read_text(encoding="utf-8") != "def add(a: int, b: int) -> int:\n    return a + b\n":
            raise RuntimeError("Agent did not apply the expected fix")

        test = run([sys.executable, "-m", "unittest", "-v"], workspace)
        if test.returncode:
            raise RuntimeError(f"Demo tests failed:\n{test.stdout}\n{test.stderr}")
        diff = run(["git", "diff", "--", "calculator.py"], workspace)
        if diff.returncode or "+    return a + b" not in diff.stdout:
            raise RuntimeError("Demo Git diff did not show the fix")

        print(f"Demo passed: {len(record['steps'])} model steps; tools: {', '.join(used)}")
        print("Calculator tests: 2 passed; Git diff contains the fix")
        print(f"Final answer: {record['final_answer']}")


if __name__ == "__main__":
    main()
