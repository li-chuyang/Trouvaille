"""Developer CLI for Trouvaille's native evaluation harness."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from trouvaille.evaluation import (
    CAPABILITY_TAGS,
    EvalRunner,
    EvaluationError,
    compare_runs,
    load_eval_suite,
    select_tasks,
    write_report,
)
from trouvaille.model import ModelConfig, OpenAIModel


DEFAULT_SUITE = Path("evals/baseline")
DEFAULT_OUTPUT = Path("eval_runs")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trouvaille-eval",
        description="Evaluate Trouvaille on controlled coding tasks with independent graders",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  trouvaille-eval list
  trouvaille-eval validate
  trouvaille-eval run --task simple_bugfix --allow-local-execution
  trouvaille-eval run --tag navigation --limit 2 --allow-local-execution
  trouvaille-eval report eval_runs/<run-id>
  trouvaille-eval compare eval_runs/<old-run> eval_runs/<new-run>

Run evaluation only when you want to measure Agent capability. Normal `trouvaille`
runs do not start evaluation automatically. Live runs use API credits and an
unsandboxed LocalExecutionBackend.
""",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    list_parser = subcommands.add_parser(
        "list",
        help="List available evaluation tasks",
        description="Show every task, title, and capability tag in an evaluation suite.",
    )
    _add_suite_argument(list_parser)

    validate_parser = subcommands.add_parser(
        "validate",
        help="Validate task definitions without calling a model",
        description="Check task schemas, fixture boundaries, tags, and oracle command definitions. No API call is made.",
    )
    _add_suite_argument(validate_parser)

    run_parser = subcommands.add_parser(
        "run",
        help="Run selected tasks and grade the resulting workspaces",
        description=(
            "Run controlled tasks sequentially through the normal Trouvaille runtime, "
            "then grade each final workspace with its independent oracle."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""selection rules:
  no --task/--tag   run every task in the suite
  --task ID         run an exact task ID; repeat to select several
  --tag TAG         run tasks with any selected tag; repeat to select several
  --limit N         keep only the first N matched tasks

Example:
  trouvaille-eval run --task simple_bugfix --output eval_runs --allow-local-execution
""",
    )
    _add_suite_argument(run_parser)
    run_parser.add_argument("--task", action="append", default=[], help="Task ID to run (repeatable)")
    run_parser.add_argument(
        "--tag",
        action="append",
        default=[],
        choices=sorted(CAPABILITY_TAGS),
        help="Run tasks carrying at least one selected tag (repeatable)",
    )
    run_parser.add_argument("--limit", type=int, help="Maximum number of selected tasks")
    run_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Run artifact root")
    run_parser.add_argument(
        "--allow-local-execution",
        action="store_true",
        help="Acknowledge that model-generated commands run locally without a security sandbox",
    )

    report_parser = subcommands.add_parser(
        "report",
        help="Regenerate a report from existing attempt results",
        description="Rebuild report.json and report.md in an existing evaluation run directory.",
    )
    report_parser.add_argument("run_dir", type=Path)

    compare_parser = subcommands.add_parser(
        "compare",
        help="Compare common tasks from two evaluation runs",
        description="Show pass/fail transitions and metric changes for task IDs present in both runs.",
    )
    compare_parser.add_argument("run_a", type=Path)
    compare_parser.add_argument("run_b", type=Path)
    return parser


def _add_suite_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE, help="Evaluation suite directory")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "list":
            suite = load_eval_suite(args.suite)
            print(f"Suite: {suite.name} ({len(suite.tasks)} tasks)")
            for task in suite.tasks:
                print(f"- {task.task_id}: {task.title} [{', '.join(task.capabilities)}]")
            return 0

        if args.command == "validate":
            suite = load_eval_suite(args.suite)
            print(f"Valid: {suite.name} — {len(suite.tasks)} tasks — digest {suite.digest[:12]}")
            print("Definitions, fixture boundaries, schemas, tags, and oracle commands are valid.")
            return 0

        if args.command == "report":
            report = write_report(args.run_dir.resolve())
            print(
                f"Report: {report['functional_passes']}/{report['attempted_tasks']} functional, "
                f"{report['workflow_passes']}/{report['attempted_tasks']} workflow"
            )
            print(args.run_dir.resolve() / "report.md")
            return 0

        if args.command == "compare":
            comparison = compare_runs(args.run_a.resolve(), args.run_b.resolve())
            for warning in comparison["warnings"]:
                print(f"Warning: {warning}")
            print(f"Common tasks: {len(comparison['common_task_ids'])}")
            print(f"FAIL -> PASS: {_items(comparison['fail_to_pass'])}")
            print(f"PASS -> FAIL: {_items(comparison['pass_to_fail'])}")
            for name, values in comparison["metrics"].items():
                print(f"{name}: {values['run_a']} -> {values['run_b']} (delta {values['delta']})")
            return 0

        if not args.allow_local_execution:
            print(
                "Error: evaluation lets the model run commands through LocalExecutionBackend, "
                "which is not a security sandbox. Re-run with --allow-local-execution only for "
                "the controlled local fixtures in this repository."
            )
            return 2
        suite = load_eval_suite(args.suite)
        selected = select_tasks(suite, task_ids=args.task, tags=args.tag, limit=args.limit)
        load_dotenv(Path.cwd() / ".env")
        if not os.getenv("OPENAI_API_KEY"):
            raise EvaluationError("OPENAI_API_KEY is missing; set it in the environment or local .env")
        config = ModelConfig.from_env()
        runner = EvalRunner(
            lambda _task: OpenAIModel(config),
            provider="openai",
            model_name=config.model,
        )
        print(
            "Warning: running controlled fixtures with a live model and unsandboxed local command execution."
        )
        print(f"Selected {len(selected)} task(s): {', '.join(task.task_id for task in selected)}")
        run_dir = runner.run(suite, selected, args.output)
        print(f"Evaluation artifacts: {run_dir}")
        return 0
    except (EvaluationError, OSError, ValueError) as exc:
        print(f"Error: {exc}")
        return 2


def _items(values: object) -> str:
    if not isinstance(values, list) or not values:
        return "none"
    return ", ".join(str(value) for value in values)


if __name__ == "__main__":
    raise SystemExit(main())
