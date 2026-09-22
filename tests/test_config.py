import os
import unittest
from pathlib import Path
from unittest.mock import patch

from agentcore.config import AppConfig
from agentcore.model import ModelConfig


class ConfigTests(unittest.TestCase):
    def test_app_config_uses_current_project_directory(self) -> None:
        self.assertEqual(AppConfig.from_cwd().workspace_root, Path.cwd().resolve())

    def test_model_config_reads_environment(self) -> None:
        with patch.dict(os.environ, {"OPENAI_MODEL": "test-model", "OPENAI_API_KEY": "test-key"}):
            config = ModelConfig.from_env()
        self.assertEqual((config.model, config.api_key), ("test-model", "test-key"))

    def test_model_config_requires_model_name(self) -> None:
        with patch.dict(os.environ, {"OPENAI_MODEL": ""}):
            with self.assertRaisesRegex(ValueError, "OPENAI_MODEL is required"):
                ModelConfig.from_env()


if __name__ == "__main__":
    unittest.main()
