"""Save a compact JSON record of an agent run."""

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agentcore.agent import RunResult


def save_trajectory(task: str, workspace_root: Path, result: RunResult) -> Path:
    steps: list[dict] = []
    for message in result.messages:
        if message.role == "assistant":
            steps.append({
                "step": len(steps) + 1,
                "model_response": {"text": message.content, "status": message.model_status},
                "tool_calls": [asdict(call) for call in message.tool_calls],
                "tool_results": [],
            })
        elif message.role == "tool" and steps:
            steps[-1]["tool_results"].append({
                "call_id": message.tool_call_id,
                "result": json.loads(message.content),
            })

    record = {
        "task": task,
        "workspace": str(workspace_root),
        "status": result.status,
        "model_calls": result.steps,
        "task_state": asdict(result.state),
        "steps": steps,
        "final_answer": result.final_answer,
        "error": result.error,
    }
    directory = workspace_root / ".agentcore" / "trajectories"
    directory.mkdir(parents=True, exist_ok=True)
    filename = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{uuid4().hex[:8]}.json"
    path = directory / filename
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
