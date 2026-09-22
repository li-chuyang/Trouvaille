import unittest
from types import SimpleNamespace

from agentcore.messages import Message
from agentcore.model import ModelConfig, OpenAIModel, ToolCall


class FakeItem:
    def __init__(self, **fields):
        self.__dict__.update(fields)

    def model_dump(self, **_kwargs):
        return self.__dict__.copy()


class ModelTests(unittest.TestCase):
    def test_openai_response_is_normalized_without_network(self) -> None:
        call = FakeItem(type="function_call", call_id="call_1", name="read_file", arguments='{"path":"a.txt"}')
        client = SimpleNamespace(responses=SimpleNamespace(create=self._create))
        self.response = SimpleNamespace(output=[call], output_text="", status="completed")
        self.model = OpenAIModel(ModelConfig(model="test-model"), client=client)

        result = self.model.complete([Message(role="user", content="read")], [{
            "name": "read_file",
            "description": "Read file",
            "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        }])

        self.assertEqual(result.tool_calls, (ToolCall("call_1", "read_file", {"path": "a.txt"}),))
        self.assertEqual(result.output_items[0]["call_id"], "call_1")
        self.assertEqual(self.request["model"], "test-model")
        self.assertEqual(self.request["input"], [{"role": "user", "content": "read"}])
        self.assertEqual(self.request["tools"][0]["name"], "read_file")
        self.assertFalse(self.request["store"])

    def test_openai_adapter_replays_assistant_and_tool_result(self) -> None:
        client = SimpleNamespace(responses=SimpleNamespace(create=self._create))
        self.response = SimpleNamespace(output=[], output_text="done", status="completed")
        model = OpenAIModel(ModelConfig(model="test-model"), client=client)
        messages = [
            Message(role="user", content="read"),
            Message(role="assistant", content="", output_items=({"type": "function_call", "call_id": "c1", "name": "read_file", "arguments": "{}"},)),
            Message(role="tool", content='{"ok": true}', tool_call_id="c1"),
        ]

        result = model.complete(messages, [])

        self.assertEqual(result.text, "done")
        self.assertEqual(self.request["input"][1]["type"], "function_call")
        self.assertEqual(self.request["input"][2], {"type": "function_call_output", "call_id": "c1", "output": '{"ok": true}'})

    def _create(self, **request):
        self.request = request
        return self.response


if __name__ == "__main__":
    unittest.main()
