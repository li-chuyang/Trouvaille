"""Thin execution abstraction for local commands."""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence


@dataclass(frozen=True)
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int


class ExecutionBackend(Protocol):
    def run(
        self,
        command: str | Sequence[str],
        *,
        cwd: Path,
        timeout: int,
        shell: bool,
    ) -> ExecutionResult: ...


class LocalExecutionBackend:
    def run(
        self,
        command: str | Sequence[str],
        *,
        cwd: Path,
        timeout: int,
        shell: bool,
    ) -> ExecutionResult:
        completed = subprocess.run(
            command,
            shell=shell,
            cwd=cwd,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return ExecutionResult(completed.stdout, completed.stderr, completed.returncode)
