import json
import tempfile
import unittest
from pathlib import Path

from agentcore.agent import Agent
from agentcore.messages import ToolCall
from agentcore.model import ModelResponse
from agentcore.tools import default_tools
from agentcore.trajectory import save_trajectory
from agentcore.workspace import Workspace


class FakeModel:
    def __init__(self):
        self.count = 0

    def complete(self, messages, schemas):
        self.count += 1
        if self.count == 1:
            return ModelResponse("", (ToolCall("c1", "list_files", {}),), "completed", ())
        return ModelResponse("done", (), "completed", ())


class TrajectoryTests(unittest.TestCase):
    def test_record_contains_steps_calls_results_and_final(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            result = Agent(FakeModel(), default_tools(workspace), workspace).run("List files")
            path = save_trajectory("List files", workspace.root, result)
            record = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual((record["task"], record["status"], record["final_answer"]), ("List files", "completed", "done"))
            self.assertEqual([step["step"] for step in record["steps"]], [1, 2])
            self.assertEqual(record["steps"][0]["tool_calls"][0]["call_id"], "c1")
            self.assertEqual(record["steps"][0]["tool_results"][0]["call_id"], "c1")
            self.assertTrue(record["steps"][0]["tool_results"][0]["result"]["ok"])


if __name__ == "__main__":
    unittest.main()
