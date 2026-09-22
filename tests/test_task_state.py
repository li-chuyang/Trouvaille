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


def response(*calls: ToolCall, text: str = "") -> ModelResponse:
    return ModelResponse(text=text, tool_calls=calls, status="completed", output_items=())


class FakeModel:
    def __init__(self, *responses: ModelResponse | Exception):
        self.responses = list(responses)

    def complete(self, messages, schemas):
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class TaskStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Workspace(Path(self.temp.name))
        self.tools = default_tools(self.workspace)

    def test_files_and_command_outcomes_are_recorded(self) -> None:
        (self.workspace.root / "input.txt").write_text("old", encoding="utf-8")
        model = FakeModel(
            response(
                ToolCall("r", "read_file", {"path": "input.txt"}),
                ToolCall("w", "write_file", {"path": "new.txt", "content": "new"}),
                ToolCall("e", "edit_file", {"path": "input.txt", "old_text": "old", "new_text": "updated"}),
                ToolCall("ok", "shell", {"command": "test -f input.txt"}),
                ToolCall("bad", "shell", {"command": "test -f missing.txt"}),
            ),
            response(text="done"),
        )

        result = Agent(model, self.tools, self.workspace).run("Update files")

        self.assertEqual((result.status, result.state.status, result.state.current_step), ("completed", "completed", 2))
        self.assertEqual(result.state.goal, "Update files")
        self.assertEqual(result.state.files_inspected, ("input.txt",))
        self.assertEqual(result.state.files_modified, ("new.txt", "input.txt"))
        self.assertEqual([(item.command, item.ok, item.exit_code) for item in result.state.commands], [
            ("test -f input.txt", True, 0),
            ("test -f missing.txt", False, 1),
        ])
        self.assertEqual(len(result.state.errors), 1)
        self.assertIn("shell: Exit code: 1", result.state.errors[0])

    def test_failed_file_tool_is_error_not_modification(self) -> None:
        model = FakeModel(
            response(ToolCall("bad", "write_file", {"path": "../outside.txt", "content": "x"})),
            response(text="Recovered"),
        )

        result = Agent(model, self.tools, self.workspace).run("Try a path")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.state.files_modified, ())
        self.assertIn("write_file", result.state.errors[0])

    def test_provider_error_and_max_steps_are_represented(self) -> None:
        provider = Agent(FakeModel(RuntimeError("service unavailable")), self.tools, self.workspace).run("First")
        self.assertEqual((provider.state.status, provider.state.current_step), ("provider_error", 1))
        self.assertIn("service unavailable", provider.state.errors[0])

        limited = Agent(FakeModel(response(ToolCall("l", "list_files", {}))), self.tools, self.workspace, max_steps=1).run("Second")
        self.assertEqual((limited.state.status, limited.state.current_step), ("max_steps", 1))
        self.assertIn("Maximum model steps reached", limited.state.errors[0])

    def test_state_resets_for_each_run_and_direct_answer_keeps_messages(self) -> None:
        model = FakeModel(
            response(ToolCall("w", "write_file", {"path": "a.txt", "content": "A"})),
            response(text="first done"),
            response(text="second done"),
        )
        agent = Agent(model, self.tools, self.workspace)

        first = agent.run("First")
        second = agent.run("Second")

        self.assertEqual(first.state.files_modified, ("a.txt",))
        self.assertEqual(second.state.files_modified, ())
        self.assertEqual((second.state.goal, second.state.status, second.state.current_step), ("Second", "completed", 1))
        self.assertEqual([message.role for message in second.messages], ["system", "user", "assistant"])
        self.assertEqual(second.final_answer, "second done")

    def test_task_state_is_saved_in_trajectory(self) -> None:
        (self.workspace.root / "note.txt").write_text("hello", encoding="utf-8")
        model = FakeModel(
            response(ToolCall("r", "read_file", {"path": "note.txt"})),
            response(text="hello"),
        )
        result = Agent(model, self.tools, self.workspace).run("Read note")

        path = save_trajectory("Read note", self.workspace.root, result)
        record = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(record["task_state"]["goal"], "Read note")
        self.assertEqual(record["task_state"]["files_inspected"], ["note.txt"])
        self.assertEqual(record["task_state"]["status"], "completed")
        self.assertEqual(record["steps"][0]["tool_results"][0]["result"]["output"], "hello")


if __name__ == "__main__":
    unittest.main()
