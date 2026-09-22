"""Manual OpenAI smoke test; requires OPENAI_API_KEY and OPENAI_MODEL."""

import tempfile
from pathlib import Path

from agentcore.agent import Agent
from agentcore.model import ModelConfig, OpenAIModel
from agentcore.tools import default_tools
from agentcore.workspace import Workspace


def main() -> None:
    model = OpenAIModel(ModelConfig.from_env())
    with tempfile.TemporaryDirectory() as directory:
        workspace = Workspace(Path(directory))
        marker = "phase03-smoke-marker-72f4"
        (workspace.root / "token.txt").write_text(marker, encoding="utf-8")
        agent = Agent(model, default_tools(workspace), workspace, max_steps=3)
        result = agent.run("Use read_file to read token.txt, then reply with its exact contents.")
        if result.status != "completed" or marker not in (result.final_answer or ""):
            raise RuntimeError(f"Smoke test failed: {result.status}: {result.error or result.final_answer}")
        if not any(message.role == "tool" for message in result.messages):
            raise RuntimeError("Smoke test failed: model did not call a tool")
        print(f"Smoke test passed in {result.steps} model steps with a tool result")


if __name__ == "__main__":
    main()
