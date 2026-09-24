"""Deterministic completion verification from explicit execution evidence."""

from dataclasses import dataclass
from enum import Enum

from trouvaille.lifecycle import FinishContext, FinishDecision
from trouvaille.task_state import CommandOutcome, TaskState


class VerificationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class VerificationResult:
    status: VerificationStatus
    reason: str
    evidence: CommandOutcome | None = None

    @property
    def allowed(self) -> bool:
        return self.status is not VerificationStatus.FAILED


class EvidenceVerifier:
    """Require the latest fresh explicit verify attempt after native file edits."""

    def evaluate(self, state: TaskState) -> VerificationResult:
        if state.last_modification_index is None:
            return VerificationResult(
                VerificationStatus.SKIPPED,
                "No tracked native file modifications require verification.",
            )

        fresh = [
            outcome
            for outcome in state.commands
            if outcome.tool == "verify"
            and outcome.operation_index > state.last_modification_index
        ]
        if not fresh:
            return VerificationResult(
                VerificationStatus.FAILED,
                "No fresh verification has run since the latest tracked file modification.",
            )

        latest = max(fresh, key=lambda outcome: outcome.operation_index)
        if latest.ok:
            return VerificationResult(
                VerificationStatus.PASSED,
                f"Fresh verification passed: {latest.command}",
                latest,
            )
        exit_detail = (
            f"exit code {latest.exit_code}"
            if latest.exit_code is not None
            else "no exit code"
        )
        return VerificationResult(
            VerificationStatus.FAILED,
            f"Latest fresh verification failed ({exit_detail}): {latest.command}",
            latest,
        )

    def check(self, context: FinishContext) -> FinishDecision:
        result = self.evaluate(context.state)
        if result.allowed:
            return FinishDecision.allow(result.reason, status=result.status.value)
        return FinishDecision.block(result.reason, status=result.status.value)
