import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from subprocess import CompletedProcess

from agentcore.tools import default_tools
from agentcore.workspace import Workspace


class ToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tools = default_tools(Workspace(self.root))

    def test_file_tools_and_search(self) -> None:
        self.assertTrue(self.tools.dispatch("write_file", {"path": "notes/a.txt", "content": "one\nneedle\n"}).ok)
        self.assertEqual(self.tools.dispatch("read_file", {"path": "notes/a.txt"}).output, "one\nneedle\n")
        self.assertEqual(self.tools.dispatch("search", {"pattern": "needle"}).output, "notes/a.txt:2:needle")
        self.assertEqual(self.tools.dispatch("list_files", {"path": "notes"}).output, "a.txt")

    def test_path_traversal_and_symlink_escape(self) -> None:
        self.assertFalse(self.tools.dispatch("write_file", {"path": "../escape.txt", "content": "no"}).ok)
        self.assertFalse(self.tools.dispatch("read_file", {"path": str(self.root / "notes.txt")}).ok)
        (self.root / "outside").symlink_to(self.root.parent, target_is_directory=True)
        self.assertFalse(self.tools.dispatch("write_file", {"path": "outside/escape.txt", "content": "no"}).ok)

    def test_shell_success_and_nonzero(self) -> None:
        success = self.tools.dispatch("shell", {"command": "pwd"})
        self.assertTrue(success.ok)
        self.assertEqual(success.stdout.strip(), str(self.root.resolve()))
        self.assertEqual(success.exit_code, 0)

        failure = self.tools.dispatch("shell", {"command": "printf problem >&2; exit 7"})
        self.assertFalse(failure.ok)
        self.assertEqual(failure.stderr, "problem")
        self.assertEqual(failure.exit_code, 7)

    def test_unknown_tool_and_invalid_arguments(self) -> None:
        self.assertFalse(self.tools.dispatch("missing", {}).ok)
        self.assertFalse(self.tools.dispatch("read_file", {}).ok)
        self.assertFalse(self.tools.dispatch("read_file", {"path": 1}).ok)
        self.assertFalse(self.tools.dispatch("read_file", {"path": "x", "extra": "y"}).ok)
        self.assertFalse(self.tools.dispatch("read_file", "x").ok)

    def test_edit_file_requires_unique_match(self) -> None:
        target = self.root / "code.py"
        target.write_text("print('before')\n", encoding="utf-8")
        result = self.tools.dispatch("edit_file", {"path": "code.py", "old_text": "before", "new_text": "after"})
        self.assertTrue(result.ok)
        self.assertEqual(target.read_text(encoding="utf-8"), "print('after')\n")
        self.assertFalse(self.tools.dispatch("edit_file", {"path": "code.py", "old_text": "missing", "new_text": "x"}).ok)
        target.write_text("two two", encoding="utf-8")
        self.assertFalse(self.tools.dispatch("edit_file", {"path": "code.py", "old_text": "two", "new_text": "one"}).ok)

    def test_git_diff_uses_workspace_and_returns_output(self) -> None:
        with patch("agentcore.tools.subprocess.run", return_value=CompletedProcess([], 0, "diff text", "")) as run:
            result = self.tools.dispatch("git_diff", {})
        self.assertTrue(result.ok)
        self.assertEqual(result.output, "diff text")
        self.assertEqual(run.call_args.args[0], ["git", "diff", "--no-ext-diff", "--", "."])
        self.assertEqual(run.call_args.kwargs["cwd"], self.root.resolve())


if __name__ == "__main__":
    unittest.main()
