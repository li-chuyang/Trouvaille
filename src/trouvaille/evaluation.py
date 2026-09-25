"""End-to-end evaluation harness around the normal Trouvaille runtime."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import tomllib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Sequence
from uuid import uuid4

from trouvaille.agent import RunResult
from trouvaille.conversation import Conversation
from trouvaille.model import Model
from trouvaille.runtime import RuntimeComponents, build_runtime
from trouvaille.trajectory import save_trajectory
from trouvaille.workspace import Workspace


EVAL_SCHEMA_VERSION = 1
CAPABILITY_TAGS = frozenset({
    "bugfix",
    "navigation",
    "cross-file",
    "editing",
    "instructions",
    "verification",
    "integrated",
})
_PLACEHOLDER = re.compile(r"\{([^{}]+)\}")
_SUPPORTED_PLACEHOLDERS = frozenset({"python", "workspace", "grader"})


class EvaluationError(ValueError):
    pass


class OracleStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True)
class EvalOracle:
    argv: tuple[str, ...]
    timeout_seconds: int


@dataclass(frozen=True)
class EvalTask:
    schema_version: int
    task_id: str
    title: str
    prompt: str
    capabilities: tuple[str, ...]
    max_steps: int
    oracle: EvalOracle
    root: Path
    workspace_dir: Path
    grader_dir: Path


@dataclass(frozen=True)
class EvalSuite:
    name: str
    root: Path
    tasks: tuple[EvalTask, ...]
    digest: str


@dataclass(frozen=True)
class OracleResult:
    status: OracleStatus
    exit_code: int | None
    stdout: str
    stderr: str
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.status is OracleStatus.PASS


@dataclass(frozen=True)
class AttemptResult:
    schema_version: int
    task_id: str
    capabilities: tuple[str, ...]
    agent_status: str
    agent_completed: bool
    oracle_status: str
    oracle_exit_code: int | None
    oracle_passed: bool
    functional_success: bool
    workflow_success: bool
    steps: int
    model_calls: int
    tool_calls: int
    files_inspected: tuple[str, ...]
    taskstate_files_modified: tuple[str, ...]
    actual_files_modified: tuple[str, ...]
    verification_attempts: int
    verification_failures: int
    elapsed_seconds: float
    input_tokens: int | None
    output_tokens: int | None
    cost: float | None
    context_compactions: int | None
    error: str | None
    failure_kind: str | None


@dataclass(frozen=True)
class EvalRunMetadata:
    schema_version: int
    run_id: str
    suite_name: str
    suite_digest: str
    selected_task_ids: tuple[str, ...]
    started_at: str
    finished_at: str | None
    trouvaille_git_commit: str | None
    trouvaille_git_dirty: bool | None
    python_version: str
    platform: str
    provider: str
    model: str
    settings: dict[str, object]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_eval_task(task_root: Path, *, default_max_steps: int = 30) -> EvalTask:
    definition = task_root / "task.toml"
    if not definition.is_file():
        raise EvaluationError(f"Missing task.toml: {task_root}")
    try:
        data = tomllib.loads(definition.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise EvaluationError(f"Invalid task definition {definition}: {exc}") from exc
    if not isinstance(data, dict):
        raise EvaluationError(f"Task definition must be a TOML table: {definition}")
    version = data.get("schema_version")
    if version != EVAL_SCHEMA_VERSION:
        raise EvaluationError(f"Unsupported task schema_version in {definition}: {version!r}")

    task_id = _required_text(data, "id", definition)
    title = _required_text(data, "title", definition)
    prompt = _required_text(data, "prompt", definition)
    raw_capabilities = data.get("capabilities")
    if not isinstance(raw_capabilities, list) or not raw_capabilities:
        raise EvaluationError(f"Task capabilities must be a non-empty list: {definition}")
    if any(not isinstance(item, str) or not item.strip() for item in raw_capabilities):
        raise EvaluationError(f"Task capabilities must contain non-empty strings: {definition}")
    capabilities = tuple(dict.fromkeys(item.strip() for item in raw_capabilities))
    unknown = sorted(set(capabilities) - CAPABILITY_TAGS)
    if unknown:
        raise EvaluationError(f"Unsupported capability tags in {definition}: {unknown}")

    max_steps = data.get("max_steps", default_max_steps)
    if not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps <= 0:
        raise EvaluationError(f"max_steps must be a positive integer: {definition}")
    oracle_data = data.get("oracle")
    if not isinstance(oracle_data, dict):
        raise EvaluationError(f"Missing [oracle] table: {definition}")
    raw_argv = oracle_data.get("argv")
    if not isinstance(raw_argv, list) or not raw_argv or any(not isinstance(item, str) or not item for item in raw_argv):
        raise EvaluationError(f"oracle.argv must be a non-empty string list: {definition}")
    for argument in raw_argv:
        placeholders = set(_PLACEHOLDER.findall(argument))
        unsupported = sorted(placeholders - _SUPPORTED_PLACEHOLDERS)
        if unsupported:
            raise EvaluationError(f"Unsupported oracle placeholders in {definition}: {unsupported}")
        remainder = _PLACEHOLDER.sub("", argument)
        if "{" in remainder or "}" in remainder:
            raise EvaluationError(f"Malformed oracle placeholder in {definition}: {argument!r}")
    timeout = oracle_data.get("timeout_seconds")
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
        raise EvaluationError(f"oracle.timeout_seconds must be a positive integer: {definition}")

    workspace_dir = task_root / "workspace"
    grader_dir = task_root / "grader"
    if not workspace_dir.is_dir():
        raise EvaluationError(f"Missing task workspace: {workspace_dir}")
    if not grader_dir.is_dir():
        raise EvaluationError(f"Missing task grader: {grader_dir}")
    _validate_fixture_tree(workspace_dir)
    return EvalTask(
        schema_version=version,
        task_id=task_id,
        title=title,
        prompt=prompt,
        capabilities=capabilities,
        max_steps=max_steps,
        oracle=EvalOracle(tuple(raw_argv), timeout),
        root=task_root.resolve(),
        workspace_dir=workspace_dir.resolve(),
        grader_dir=grader_dir.resolve(),
    )


def load_eval_suite(root: Path, *, default_max_steps: int = 30) -> EvalSuite:
    suite_root = root.resolve()
    if not suite_root.is_dir():
        raise EvaluationError(f"Evaluation suite is not a directory: {suite_root}")
    task_directories = sorted(
        (path for path in suite_root.iterdir() if path.is_dir() and not path.name.startswith(".")),
        key=lambda path: path.name,
    )
    if not task_directories:
        raise EvaluationError(f"Evaluation suite contains no task directories: {suite_root}")
    tasks = tuple(load_eval_task(path, default_max_steps=default_max_steps) for path in task_directories)
    identifiers = [task.task_id for task in tasks]
    duplicates = sorted({item for item in identifiers if identifiers.count(item) > 1})
    if duplicates:
        raise EvaluationError(f"Duplicate evaluation task IDs: {duplicates}")
    return EvalSuite(suite_root.name, suite_root, tasks, suite_digest(suite_root))


def suite_digest(root: Path) -> str:
    digest = hashlib.sha256()
    suite_root = root.resolve()
    for task_dir in sorted((path for path in suite_root.iterdir() if path.is_dir()), key=lambda path: path.name):
        paths = [task_dir / "task.toml"]
        for subtree in (task_dir / "workspace", task_dir / "grader"):
            if subtree.is_dir():
                paths.extend(path for path in subtree.rglob("*") if path.is_file())
        for path in sorted(paths, key=lambda item: item.relative_to(suite_root).as_posix()):
            if path.is_symlink():
                raise EvaluationError(f"Evaluation definitions must not contain symlinks: {path}")
            relative = path.relative_to(suite_root).as_posix().encode("utf-8")
            data = path.read_bytes()
            digest.update(len(relative).to_bytes(8, "big"))
            digest.update(relative)
            digest.update(len(data).to_bytes(8, "big"))
            digest.update(data)
    return digest.hexdigest()


def select_tasks(
    suite: EvalSuite,
    *,
    task_ids: Sequence[str] = (),
    tags: Sequence[str] = (),
    limit: int | None = None,
) -> tuple[EvalTask, ...]:
    if limit is not None and limit <= 0:
        raise EvaluationError("Evaluation limit must be positive")
    requested = set(task_ids)
    known = {task.task_id for task in suite.tasks}
    missing = sorted(requested - known)
    if missing:
        raise EvaluationError(f"Unknown evaluation task IDs: {missing}")
    unknown_tags = sorted(set(tags) - CAPABILITY_TAGS)
    if unknown_tags:
        raise EvaluationError(f"Unsupported capability tags: {unknown_tags}")
    selected = tuple(
        task
        for task in suite.tasks
        if (not requested or task.task_id in requested)
        and (not tags or any(tag in task.capabilities for tag in tags))
    )
    if limit is not None:
        selected = selected[:limit]
    if not selected:
        raise EvaluationError("No evaluation tasks matched the selection")
    return selected


def expand_oracle_argv(task: EvalTask, workspace: Path) -> tuple[str, ...]:
    values = {
        "python": sys.executable,
        "workspace": str(workspace.resolve()),
        "grader": str(task.grader_dir),
    }
    return tuple(_PLACEHOLDER.sub(lambda match: values[match.group(1)], item) for item in task.oracle.argv)


def run_oracle(task: EvalTask, workspace: Path) -> OracleResult:
    argv = expand_oracle_argv(task, workspace)
    environment = _sanitized_environment()
    try:
        completed = subprocess.run(
            argv,
            shell=False,
            cwd=workspace,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=task.oracle.timeout_seconds,
            check=False,
            env=environment,
        )
    except subprocess.TimeoutExpired as exc:
        return OracleResult(
            OracleStatus.TIMEOUT,
            None,
            _timeout_text(exc.stdout),
            _timeout_text(exc.stderr),
            f"Oracle exceeded {task.oracle.timeout_seconds}s timeout",
        )
    except OSError as exc:
        return OracleResult(OracleStatus.ERROR, None, "", "", f"{type(exc).__name__}: {exc}")
    status = OracleStatus.PASS if completed.returncode == 0 else OracleStatus.FAIL
    return OracleResult(status, completed.returncode, completed.stdout, completed.stderr)


class EvalRunner:
    """Sequentially run native evaluation tasks through the shared normal runtime."""

    def __init__(
        self,
        model_factory: Callable[[EvalTask], Model],
        *,
        provider: str,
        model_name: str,
        default_max_steps: int = 30,
        project_root: Path | None = None,
    ) -> None:
        if default_max_steps <= 0:
            raise ValueError("default_max_steps must be positive")
        self.model_factory = model_factory
        self.provider = provider
        self.model_name = model_name
        self.default_max_steps = default_max_steps
        self.project_root = (
            project_root.resolve()
            if project_root is not None
            else Path(__file__).resolve().parents[2]
        )

    def run(
        self,
        suite: EvalSuite,
        tasks: Sequence[EvalTask],
        output_root: Path,
    ) -> Path:
        if not tasks:
            raise EvaluationError("Cannot run an empty task selection")
        started = _utc_now()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"{stamp}--{suite.name}-{uuid4().hex[:8]}"
        run_dir = output_root.resolve() / run_id
        attempts_dir = run_dir / "attempts"
        attempts_dir.mkdir(parents=True, exist_ok=False)
        commit, dirty = _git_metadata(self.project_root)
        metadata = EvalRunMetadata(
            schema_version=EVAL_SCHEMA_VERSION,
            run_id=run_id,
            suite_name=suite.name,
            suite_digest=suite.digest,
            selected_task_ids=tuple(task.task_id for task in tasks),
            started_at=started,
            finished_at=None,
            trouvaille_git_commit=commit,
            trouvaille_git_dirty=dirty,
            python_version=platform.python_version(),
            platform=platform.platform(),
            provider=self.provider,
            model=self.model_name,
            settings={
                "default_max_steps": self.default_max_steps,
                "task_max_steps": {task.task_id: task.max_steps for task in tasks},
                "sequential": True,
                "local_execution_backend": True,
            },
        )
        _write_json(run_dir / "run.json", asdict(metadata))
        for task in tasks:
            self.run_attempt(task, attempts_dir / task.task_id)
        metadata = EvalRunMetadata(**{**asdict(metadata), "finished_at": _utc_now()})
        _write_json(run_dir / "run.json", asdict(metadata))
        write_report(run_dir)
        return run_dir

    def run_attempt(self, task: EvalTask, attempt_dir: Path) -> AttemptResult:
        attempt_dir.mkdir(parents=True, exist_ok=False)
        started = time.monotonic()
        result: RunResult | None = None
        runtime: RuntimeComponents | None = None
        runtime_error: str | None = None
        actual_files: tuple[str, ...] = ()
        diff = ""
        oracle = OracleResult(OracleStatus.ERROR, None, "", "", "Attempt did not reach oracle")

        try:
            with tempfile.TemporaryDirectory(prefix=f"trouvaille-eval-{task.task_id}-") as temporary:
                workspace_path = Path(temporary) / "workspace"
                shutil.copytree(task.workspace_dir, workspace_path)
                _initialize_git(workspace_path)
                workspace = Workspace(workspace_path)
                try:
                    model = self.model_factory(task)
                    runtime = build_runtime(workspace, model, max_steps=task.max_steps)
                    conversation = Conversation(runtime.agent)
                    result = conversation.run(task.prompt)
                    trajectory = save_trajectory(task.prompt, workspace, result)
                    shutil.copy2(trajectory, attempt_dir / "trajectory.json")
                except Exception as exc:
                    runtime_error = f"{type(exc).__name__}: {exc}"
                    _write_json(attempt_dir / "trajectory.json", {
                        "task": task.prompt,
                        "status": "runtime_error",
                        "error": runtime_error,
                    })
                try:
                    actual_files, diff = _capture_repository_changes(workspace_path)
                except Exception as exc:
                    detail = f"{type(exc).__name__}: {exc}"
                    runtime_error = f"{runtime_error}; {detail}" if runtime_error else detail
                oracle = run_oracle(task, workspace_path)
        except Exception as exc:
            runtime_error = f"{type(exc).__name__}: {exc}"
            if not (attempt_dir / "trajectory.json").exists():
                _write_json(attempt_dir / "trajectory.json", {
                    "task": task.prompt,
                    "status": "runtime_error",
                    "error": runtime_error,
                })

        elapsed = time.monotonic() - started
        (attempt_dir / "diff.patch").write_text(diff, encoding="utf-8")
        (attempt_dir / "oracle.log").write_text(_oracle_log(task, oracle), encoding="utf-8")
        attempt = _attempt_result(
            task,
            result,
            runtime,
            oracle,
            actual_files,
            elapsed,
            runtime_error,
        )
        _write_json(attempt_dir / "result.json", asdict(attempt))
        return attempt


def build_report(results: Sequence[AttemptResult]) -> dict[str, object]:
    attempted = len(results)
    functional = sum(item.functional_success for item in results)
    workflow = sum(item.workflow_success for item in results)
    oracle_errors = sum(item.oracle_status in {OracleStatus.ERROR.value, OracleStatus.TIMEOUT.value} for item in results)
    capabilities: dict[str, dict[str, object]] = {}
    for tag in sorted({tag for item in results for tag in item.capabilities}):
        tagged = [item for item in results if tag in item.capabilities]
        passed = sum(item.functional_success for item in tagged)
        capabilities[tag] = {
            "tasks": len(tagged),
            "functional_passes": passed,
            "functional_pass_rate": _rate(passed, len(tagged)),
            "workflow_passes": sum(item.workflow_success for item in tagged),
            "workflow_pass_rate": _rate(sum(item.workflow_success for item in tagged), len(tagged)),
        }
    return {
        "schema_version": EVAL_SCHEMA_VERSION,
        "attempted_tasks": attempted,
        "oracle_infrastructure_errors": oracle_errors,
        "functional_passes": functional,
        "functional_pass_rate": _rate(functional, attempted),
        "workflow_passes": workflow,
        "workflow_pass_rate": _rate(workflow, attempted),
        "average_steps": _mean([item.steps for item in results]),
        "median_steps": _median([item.steps for item in results]),
        "average_tool_calls": _mean([item.tool_calls for item in results]),
        "average_model_calls": _mean([item.model_calls for item in results]),
        "average_elapsed_seconds": _mean([item.elapsed_seconds for item in results]),
        "input_tokens": _optional_sum([item.input_tokens for item in results]),
        "output_tokens": _optional_sum([item.output_tokens for item in results]),
        "cost": _optional_sum([item.cost for item in results]),
        "failure_breakdown": _failure_breakdown(results),
        "by_capability": capabilities,
        "tasks": [asdict(item) for item in results],
    }


def write_report(run_dir: Path) -> dict[str, object]:
    results = load_attempt_results(run_dir)
    report = build_report(results)
    _write_json(run_dir / "report.json", report)
    lines = [
        f"# Trouvaille evaluation report — {run_dir.name}",
        "",
        "> One run is a development signal, not a statistically stable estimate.",
        "",
        f"- Attempted tasks: {report['attempted_tasks']}",
        f"- Functional pass: {report['functional_passes']}/{report['attempted_tasks']} ({_percent(report['functional_pass_rate'])})",
        f"- Workflow pass: {report['workflow_passes']}/{report['attempted_tasks']} ({_percent(report['workflow_pass_rate'])})",
        f"- Oracle infrastructure errors: {report['oracle_infrastructure_errors']}",
        f"- Average steps: {_display_number(report['average_steps'])}",
        f"- Average tool calls: {_display_number(report['average_tool_calls'])}",
        f"- Average model calls: {_display_number(report['average_model_calls'])}",
        f"- Average elapsed seconds: {_display_number(report['average_elapsed_seconds'])}",
        "",
        "## Outcomes",
        "",
        "| Task | Agent | Oracle | Functional | Workflow | Steps | Tools |",
        "| --- | --- | --- | --- | --- | ---: | ---: |",
    ]
    for item in results:
        lines.append(
            f"| {item.task_id} | {item.agent_status} | {item.oracle_status} | "
            f"{'PASS' if item.functional_success else 'FAIL'} | "
            f"{'PASS' if item.workflow_success else 'FAIL'} | {item.steps} | {item.tool_calls} |"
        )
    lines.extend(["", "## Tagged task pass rates", ""])
    for tag, values in report["by_capability"].items():
        lines.append(
            f"- `{tag}`: {values['functional_passes']}/{values['tasks']} functional "
            f"({_percent(values['functional_pass_rate'])})"
        )
    (run_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def compare_runs(run_a: Path, run_b: Path) -> dict[str, object]:
    metadata_a = _read_json(run_a / "run.json")
    metadata_b = _read_json(run_b / "run.json")
    results_a = {item.task_id: item for item in load_attempt_results(run_a)}
    results_b = {item.task_id: item for item in load_attempt_results(run_b)}
    common = sorted(results_a.keys() & results_b.keys())
    if not common:
        raise EvaluationError("Evaluation runs have no common task IDs")
    warnings = []
    if metadata_a.get("suite_digest") != metadata_b.get("suite_digest"):
        warnings.append("Suite digests differ; task definitions may not be directly comparable.")
    if (metadata_a.get("provider"), metadata_a.get("model")) != (
        metadata_b.get("provider"), metadata_b.get("model")
    ):
        warnings.append("Model/provider differ; results are not a controlled comparison.")
    left = [results_a[item] for item in common]
    right = [results_b[item] for item in common]
    pass_to_fail = [item for item in common if results_a[item].functional_success and not results_b[item].functional_success]
    fail_to_pass = [item for item in common if not results_a[item].functional_success and results_b[item].functional_success]
    return {
        "schema_version": EVAL_SCHEMA_VERSION,
        "run_a": str(run_a),
        "run_b": str(run_b),
        "common_task_ids": common,
        "warnings": warnings,
        "pass_to_fail": pass_to_fail,
        "fail_to_pass": fail_to_pass,
        "metrics": {
            "functional_pass_rate": _metric_pair(
                _rate(sum(item.functional_success for item in left), len(left)),
                _rate(sum(item.functional_success for item in right), len(right)),
            ),
            "workflow_pass_rate": _metric_pair(
                _rate(sum(item.workflow_success for item in left), len(left)),
                _rate(sum(item.workflow_success for item in right), len(right)),
            ),
            "average_steps": _metric_pair(_mean([item.steps for item in left]), _mean([item.steps for item in right])),
            "average_tool_calls": _metric_pair(_mean([item.tool_calls for item in left]), _mean([item.tool_calls for item in right])),
            "average_model_calls": _metric_pair(_mean([item.model_calls for item in left]), _mean([item.model_calls for item in right])),
            "average_elapsed_seconds": _metric_pair(
                _mean([item.elapsed_seconds for item in left]),
                _mean([item.elapsed_seconds for item in right]),
            ),
            "input_tokens": _metric_pair(
                _optional_sum([item.input_tokens for item in left]),
                _optional_sum([item.input_tokens for item in right]),
            ),
            "output_tokens": _metric_pair(
                _optional_sum([item.output_tokens for item in left]),
                _optional_sum([item.output_tokens for item in right]),
            ),
            "cost": _metric_pair(
                _optional_sum([item.cost for item in left]),
                _optional_sum([item.cost for item in right]),
            ),
        },
    }


def load_attempt_results(run_dir: Path) -> tuple[AttemptResult, ...]:
    attempts = run_dir / "attempts"
    if not attempts.is_dir():
        raise EvaluationError(f"Missing attempts directory: {attempts}")
    results = []
    for path in sorted(attempts.glob("*/result.json")):
        data = _read_json(path)
        try:
            data["capabilities"] = tuple(data["capabilities"])
            data["files_inspected"] = tuple(data["files_inspected"])
            data["taskstate_files_modified"] = tuple(data["taskstate_files_modified"])
            data["actual_files_modified"] = tuple(data["actual_files_modified"])
            results.append(AttemptResult(**data))
        except (KeyError, TypeError) as exc:
            raise EvaluationError(f"Invalid attempt result {path}: {exc}") from exc
    if not results:
        raise EvaluationError(f"Run contains no attempt results: {run_dir}")
    return tuple(results)


def _attempt_result(
    task: EvalTask,
    result: RunResult | None,
    runtime: RuntimeComponents | None,
    oracle: OracleResult,
    actual_files: tuple[str, ...],
    elapsed: float,
    runtime_error: str | None,
) -> AttemptResult:
    agent_status = result.status if result is not None else "runtime_error"
    completed = agent_status == "completed"
    functional = oracle.passed
    workflow = functional and completed
    state = result.state if result is not None else None
    verification = tuple(item for item in state.commands if item.tool == "verify") if state else ()
    tool_calls = sum(len(message.tool_calls) for message in result.messages if message.role == "assistant") if result else 0
    compactions = None
    if runtime is not None:
        compactions = sum(
            bool(stats.tool_results_compacted or stats.summary_used)
            for stats in runtime.context_manager.stats_history
        )
    error = runtime_error or (result.error if result is not None else None) or oracle.error
    failure = _failure_kind(agent_status, oracle.status, runtime_error)
    return AttemptResult(
        schema_version=EVAL_SCHEMA_VERSION,
        task_id=task.task_id,
        capabilities=task.capabilities,
        agent_status=agent_status,
        agent_completed=completed,
        oracle_status=oracle.status.value,
        oracle_exit_code=oracle.exit_code,
        oracle_passed=oracle.passed,
        functional_success=functional,
        workflow_success=workflow,
        steps=result.steps if result is not None else 0,
        model_calls=result.steps if result is not None else 0,
        tool_calls=tool_calls,
        files_inspected=state.files_inspected if state else (),
        taskstate_files_modified=state.files_modified if state else (),
        actual_files_modified=actual_files,
        verification_attempts=len(verification),
        verification_failures=sum(not item.ok for item in verification),
        elapsed_seconds=round(elapsed, 6),
        input_tokens=None,
        output_tokens=None,
        cost=None,
        context_compactions=compactions,
        error=error,
        failure_kind=failure,
    )


def _failure_kind(agent_status: str, oracle: OracleStatus, runtime_error: str | None) -> str | None:
    if runtime_error is not None:
        return "runtime_infrastructure_error"
    if oracle is OracleStatus.ERROR:
        return "oracle_error"
    if oracle is OracleStatus.TIMEOUT:
        return "oracle_timeout"
    if agent_status == "max_steps":
        return "agent_max_steps"
    if agent_status != "completed":
        return "agent_error"
    if oracle is OracleStatus.FAIL:
        return "oracle_failure"
    return None


def _initialize_git(workspace: Path) -> None:
    commands = (
        ("git", "init", "-q"),
        ("git", "config", "user.name", "Trouvaille Eval"),
        ("git", "config", "user.email", "eval@trouvaille.invalid"),
    )
    for command in commands:
        _checked_command(command, workspace)
    exclude = workspace / ".git" / "info" / "exclude"
    with exclude.open("a", encoding="utf-8") as handle:
        handle.write("\n.agentcore/\n__pycache__/\n*.pyc\n")
    _checked_command(("git", "add", "-A"), workspace)
    _checked_command(
        ("git", "commit", "-qm", "evaluation baseline"),
        workspace,
        environment={
            **os.environ,
            "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
            "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
        },
    )


def _capture_repository_changes(workspace: Path) -> tuple[tuple[str, ...], str]:
    _checked_command(("git", "add", "-A"), workspace)
    names = _checked_command(
        ("git", "diff", "--cached", "--name-only", "-z", "HEAD"),
        workspace,
    ).stdout
    files = tuple(sorted(path for path in names.split("\0") if path and not path.startswith(".agentcore/")))
    diff = _checked_command(
        ("git", "diff", "--cached", "--binary", "--no-ext-diff", "HEAD"),
        workspace,
    ).stdout
    return files, diff


def _checked_command(
    command: Sequence[str],
    cwd: Path,
    *,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        tuple(command),
        shell=False,
        cwd=cwd,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=30,
        check=False,
        env=environment,
    )
    if completed.returncode != 0:
        raise EvaluationError(
            f"Command failed ({completed.returncode}): {list(command)!r}: "
            f"{completed.stderr.strip()}"
        )
    return completed


def _git_metadata(project_root: Path) -> tuple[str | None, bool | None]:
    try:
        commit = _checked_command(("git", "rev-parse", "HEAD"), project_root).stdout.strip()
        status = _checked_command(("git", "status", "--porcelain"), project_root).stdout
        return commit or None, bool(status.strip())
    except (OSError, EvaluationError, subprocess.TimeoutExpired):
        return None, None


def _oracle_log(task: EvalTask, oracle: OracleResult) -> str:
    lines = [
        f"task: {task.task_id}",
        f"status: {oracle.status.value}",
        f"exit_code: {oracle.exit_code}",
    ]
    if oracle.error:
        lines.append(f"error: {oracle.error}")
    lines.extend(["", "--- stdout ---", oracle.stdout, "--- stderr ---", oracle.stderr])
    return "\n".join(lines).rstrip() + "\n"


def _sanitized_environment() -> dict[str, str]:
    allowed = (
        "PATH",
        "LANG",
        "LC_ALL",
        "SYSTEMROOT",
        "TMPDIR",
        "TEMP",
        "TMP",
    )
    environment = {key: os.environ[key] for key in allowed if key in os.environ}
    environment.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"})
    return environment


def _validate_fixture_tree(workspace: Path) -> None:
    forbidden_directories = {".git", ".agentcore", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    for path in workspace.rglob("*"):
        if path.is_symlink():
            raise EvaluationError(f"Fixture workspace must not contain symlinks: {path}")
        if path.name in forbidden_directories or path.suffix in {".pyc", ".pyo"}:
            raise EvaluationError(f"Fixture workspace contains forbidden runtime data: {path}")


def _required_text(data: dict, field: str, definition: Path) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise EvaluationError(f"Task {field} must be a non-empty string: {definition}")
    return value.strip()


def _timeout_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"Could not read JSON {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise EvaluationError(f"Expected JSON object: {path}")
    return data


def _rate(count: int, total: int) -> float | None:
    return count / total if total else None


def _mean(values: Sequence[float | int]) -> float | None:
    return round(statistics.fmean(values), 6) if values else None


def _median(values: Sequence[float | int]) -> float | None:
    return round(float(statistics.median(values)), 6) if values else None


def _optional_sum(values: Sequence[int | float | None]) -> int | float | None:
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def _failure_breakdown(results: Sequence[AttemptResult]) -> dict[str, int]:
    values: dict[str, int] = {}
    for item in results:
        if item.failure_kind:
            values[item.failure_kind] = values.get(item.failure_kind, 0) + 1
    return dict(sorted(values.items()))


def _percent(value: object) -> str:
    return "n/a" if value is None else f"{float(value) * 100:.1f}%"


def _display_number(value: object) -> str:
    return "n/a" if value is None else f"{float(value):.2f}"


def _metric_pair(left: int | float | None, right: int | float | None) -> dict[str, int | float | None]:
    delta = None if left is None or right is None else right - left
    return {"run_a": left, "run_b": right, "delta": delta}
