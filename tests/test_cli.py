import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agentcore.cli import main


class FailingModel:
    def complete(self, messages, schemas):
        raise RuntimeError("API unavailable")


class CliTests(unittest.TestCase):
    def invoke(self, args, env):
        output = io.StringIO()
        with patch("sys.argv", ["my-agent", *args]), patch("agentcore.cli.load_dotenv"), patch.dict("os.environ", env, clear=True), redirect_stdout(output):
            code = main()
        return code, output.getvalue()

    def test_missing_key_and_invalid_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            code, output = self.invoke(["--workspace", directory], {})
            self.assertEqual(code, 2)
            self.assertIn("OPENAI_API_KEY is missing", output)

            code, output = self.invoke(["--workspace", str(Path(directory) / "missing")], {})
            self.assertEqual(code, 2)
            self.assertIn("Workspace is not a directory", output)

    def test_invalid_max_steps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            code, output = self.invoke(["--workspace", directory, "--max-steps", "0"], {"OPENAI_API_KEY": "dummy", "OPENAI_MODEL": "dummy"})
            self.assertEqual(code, 2)
            self.assertIn("max_steps must be positive", output)

    def test_provider_error_is_reported_and_saved(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch("agentcore.cli.OpenAIModel", return_value=FailingModel()):
            code, output = self.invoke(["--workspace", directory, "--task", "try"], {"OPENAI_API_KEY": "dummy", "OPENAI_MODEL": "dummy"})
            self.assertEqual(code, 1)
            self.assertIn("API unavailable", output)
            trace = next((Path(directory) / ".agentcore" / "trajectories").glob("*.json"))
            self.assertEqual(json.loads(trace.read_text(encoding="utf-8"))["status"], "provider_error")

    def test_ctrl_c_exits_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch("builtins.input", side_effect=KeyboardInterrupt):
            code, output = self.invoke(["--workspace", directory], {"OPENAI_API_KEY": "dummy", "OPENAI_MODEL": "dummy"})
            self.assertEqual(code, 130)
            self.assertIn("Interrupted", output)


if __name__ == "__main__":
    unittest.main()
