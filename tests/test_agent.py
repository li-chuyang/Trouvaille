import json
import tempfile
import unittest
from pathlib import Path

from agentcore.agent import Agent
from agentcore.messages import ToolCall
from agentcore.model import ModelResponse
from agentcore.tools import default_tools
from agentcore.workspace import Workspace


def answer(text: str) -> ModelResponse:
    return ModelResponse(text=text, tool_calls=(), status="completed", output_items=())


def calls(*items: ToolCall) -> ModelResponse:
    return ModelResponse(text="", tool_calls=items, status="completed", output_items=())


class FakeModel:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.seen = []

    def complete(self, messages, tool_schemas):
        self.seen.append(tuple(messages))
        assert tool_schemas
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class AgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Workspace(Path(self.temp.name))
        self.tools = default_tools(self.workspace)

    def agent(self, model, max_steps=10):
        return Agent(model, self.tools, self.workspace, max_steps=max_steps)

    def test_direct_answer(self) -> None:
        model = FakeModel(answer("done"))
        result = self.agent(model).run("Say done")
        self.assertEqual((result.status, result.final_answer, result.steps), ("completed", "done", 1))
        self.assertEqual([message.role for message in result.messages], ["system", "user", "assistant"])

    def test_read_file_then_answer(self) -> None:
        (self.workspace.root / "note.txt").write_text("hello", encoding="utf-8")
        model = FakeModel(calls(ToolCall("c1", "read_file", {"path": "note.txt"})), answer("hello"))
        result = self.agent(model).run("Read note.txt")
        self.assertEqual((result.status, result.steps), ("completed", 2))
        self.assertEqual(json.loads(model.seen[1][-1].content)["output"], "hello")
        self.assertEqual(model.seen[1][-1].tool_call_id, "c1")

    def test_multiple_tool_rounds(self) -> None:
        model = FakeModel(
            calls(ToolCall("c1", "write_file", {"path": "a.txt", "content": "x"})),
            calls(ToolCall("c2", "read_file", {"path": "a.txt"})),
            answer("finished"),
        )
        result = self.agent(model).run("Write and read")
        self.assertEqual((result.status, result.steps), ("completed", 3))
        self.assertEqual((self.workspace.root / "a.txt").read_text(), "x")
        self.assertEqual([m.tool_call_id for m in result.messages if m.role == "tool"], ["c1", "c2"])

    def test_two_calls_in_one_response_keep_their_ids(self) -> None:
        (self.workspace.root / "a.txt").write_text("A", encoding="utf-8")
        (self.workspace.root / "b.txt").write_text("B", encoding="utf-8")
        model = FakeModel(calls(
            ToolCall("first", "read_file", {"path": "a.txt"}),
            ToolCall("second", "read_file", {"path": "b.txt"}),
        ), answer("A and B"))

        result = self.agent(model).run("Read both")

        observations = [message for message in model.seen[1] if message.role == "tool"]
        self.assertEqual([message.tool_call_id for message in observations], ["first", "second"])
        self.assertEqual([json.loads(message.content)["output"] for message in observations], ["A", "B"])
        self.assertEqual(result.final_answer, "A and B")

    def test_tool_error_is_observed_then_corrected(self) -> None:
        (self.workspace.root / "good.txt").write_text("fixed", encoding="utf-8")
        model = FakeModel(
            calls(ToolCall("bad", "read_file", {"path": "../bad.txt"})),
            calls(ToolCall("good", "read_file", {"path": "good.txt"})),
            answer("fixed"),
        )
        result = self.agent(model).run("Read a file")
        self.assertEqual(result.status, "completed")
        self.assertFalse(json.loads(model.seen[1][-1].content)["ok"])
        self.assertTrue(json.loads(model.seen[2][-1].content)["ok"])

    def test_max_steps_after_observation(self) -> None:
        model = FakeModel(calls(ToolCall("c1", "list_files", {})))
        result = self.agent(model, max_steps=1).run("List files")
        self.assertEqual((result.status, result.steps), ("max_steps", 1))
        self.assertEqual(result.messages[-1].role, "tool")
        self.assertEqual(len(model.seen), 1)

    def test_provider_error_is_distinct(self) -> None:
        result = self.agent(FakeModel(RuntimeError("provider unavailable"))).run("Do task")
        self.assertEqual(result.status, "provider_error")
        self.assertIn("provider unavailable", result.error)
        self.assertEqual([message.role for message in result.messages], ["system", "user"])


if __name__ == "__main__":
    unittest.main()
