import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "simulator"))
from app import ai_config_example
from app.ai_training_graph import TrainingAgentConfig


class AIConfigTests(unittest.TestCase):
    def test_clean_checkout_has_provider_default_without_a_key(self):
        with patch.dict(os.environ, {}, clear=True), patch.multiple(
            ai_config_example, API_KEY="", MODEL="qwen-plus",
            BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
        ):
            config = TrainingAgentConfig.from_environment()
        self.assertEqual(config.api_key, "")
        self.assertEqual(config.model, "qwen-plus")
        self.assertEqual(config.base_url, "https://dashscope.aliyuncs.com/compatible-mode/v1")

    def test_environment_overrides_example(self):
        with patch.dict(os.environ, {
            "DASHSCOPE_API_KEY": "test-only-key",
            "DASHSCOPE_BASE_URL": "https://provider.example/v1",
            "DASHSCOPE_MODEL": "test-model"
        }, clear=True):
            config = TrainingAgentConfig.from_environment(enable_llm=False)
        self.assertEqual(config.api_key, "test-only-key")
        self.assertEqual(config.base_url, "https://provider.example/v1")
        self.assertEqual(config.model, "test-model")
        self.assertFalse(config.enable_llm)


if __name__ == "__main__":
    unittest.main()
