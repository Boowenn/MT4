from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools.ai_analysis.providers.base import AIProviderConfig, AIProviderError, assert_ai_provider_safety
from tools.ai_analysis.providers.deepseek_provider import DeepSeekProvider
from tools.ai_analysis.providers.router import load_ai_provider, load_ai_provider_config


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class TestAIProviderRouter(unittest.TestCase):
    def test_loads_ai_env_and_redacts_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_file = root / ".env.ai.local"
            env_file.write_text(
                "\n".join(
                    [
                        "QG_AI_ENABLED=1",
                        "QG_AI_PROVIDER=deepseek",
                        "QG_AI_MODEL=deepseek-v4-flash",
                        "QG_AI_API_KEY=sk-test-secret-123456",
                    ]
                ),
                encoding="utf-8",
            )
            cfg = load_ai_provider_config(repo_root=root, environ={})
            self.assertTrue(cfg.enabled)
            self.assertTrue(cfg.configured)
            redacted = cfg.redacted()
            self.assertNotIn("sk-test-secret-123456", json.dumps(redacted))
            self.assertIn("***", redacted["api_key"])

    def test_compat_loads_existing_deepseek_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.deepseek.local").write_text(
                "DEEPSEEK_API_KEY=ds-existing-key\nQG_MT5_AI_DEEPSEEK_MODEL=deepseek-v4-pro\n",
                encoding="utf-8",
            )
            cfg = load_ai_provider_config(repo_root=root, environ={})
            self.assertEqual(cfg.provider, "deepseek")
            self.assertEqual(cfg.model, "deepseek-v4-pro")
            self.assertTrue(cfg.enabled)

    def test_mock_provider_returns_advisory_only_json(self) -> None:
        cfg = AIProviderConfig(enabled=True, provider="mock", model="mock-local")
        provider = load_ai_provider(cfg)
        response = provider.chat_json(system_prompt="json", user_payload={"symbol": "USDJPYc"})
        self.assertTrue(response.ok)
        self.assertEqual(response.parsed["verdict"], "观望，不开新仓")
        self.assertFalse(response.parsed["orderSendAllowed"])

    def test_deepseek_provider_parses_openai_compatible_response(self) -> None:
        captured = {}

        def opener(request, timeout):
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse({"choices": [{"message": {"content": "{\"ok\":true,\"advisoryOnly\":true}"}}]})

        cfg = AIProviderConfig(enabled=True, provider="deepseek", api_key="secret", model="deepseek-v4-flash")
        response = DeepSeekProvider(cfg, opener=opener).chat_json(system_prompt="Return JSON", user_payload={"x": 1})
        self.assertTrue(response.ok)
        self.assertTrue(response.parsed["ok"])
        self.assertEqual(captured["body"]["response_format"], {"type": "json_object"})

    def test_safety_rejects_truthy_execution_flags(self) -> None:
        with self.assertRaises(AIProviderError):
            assert_ai_provider_safety({"QG_ORDER_SEND_ALLOWED": "1"})


if __name__ == "__main__":
    unittest.main()
