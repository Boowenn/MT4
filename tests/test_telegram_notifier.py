from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from telegram_notifier.client import default_urlopen, extract_chat_candidates, validate_message_text
from telegram_notifier.config import load_config, update_env_file
from telegram_notifier.safety import assert_telegram_safety, require_push_enabled

class TelegramNotifierTests(unittest.TestCase):
    def test_config_loads_local_env_without_exposing_full_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            env_file = root / ".env.telegram.local"
            env_file.write_text("QG_TELEGRAM_BOT_TOKEN=123456:ABCDEFSECRET\nQG_TELEGRAM_CHAT_ID=987654321\nQG_TELEGRAM_PUSH_ALLOWED=1\nQG_TELEGRAM_COMMANDS_ALLOWED=0\n", encoding="utf-8")
            config = load_config(repo_root=root, env_file=env_file, environ={})
            self.assertTrue(config.token_configured)
            self.assertTrue(config.chat_id_configured)
            self.assertTrue(config.push_allowed)
            safe_json = json.dumps(config.as_safe_dict())
            self.assertNotIn("ABCDEFSECRET", safe_json)
            self.assertIn("1234", safe_json)

    def test_safety_blocks_telegram_command_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            env_file = root / ".env.telegram.local"
            env_file.write_text("QG_TELEGRAM_COMMANDS_ALLOWED=1\n", encoding="utf-8")
            config = load_config(repo_root=root, env_file=env_file, environ={})
            with self.assertRaises(RuntimeError):
                assert_telegram_safety(config)

    def test_push_requires_explicit_push_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            env_file = root / ".env.telegram.local"
            env_file.write_text("QG_TELEGRAM_BOT_TOKEN=123456:ABCDEF\nQG_TELEGRAM_CHAT_ID=987654321\nQG_TELEGRAM_PUSH_ALLOWED=0\nQG_TELEGRAM_COMMANDS_ALLOWED=0\n", encoding="utf-8")
            config = load_config(repo_root=root, env_file=env_file, environ={})
            with self.assertRaises(RuntimeError):
                require_push_enabled(config)

    def test_update_env_file_writes_chat_id_without_touching_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_file = Path(tmp_dir) / ".env.telegram.local"
            env_file.write_text("QG_TELEGRAM_BOT_TOKEN=keep-this-token\nQG_TELEGRAM_PUSH_ALLOWED=0\n", encoding="utf-8")
            update_env_file(env_file, {"QG_TELEGRAM_CHAT_ID": "123456", "QG_TELEGRAM_PUSH_ALLOWED": "1"})
            text = env_file.read_text(encoding="utf-8")
            self.assertIn("QG_TELEGRAM_BOT_TOKEN=keep-this-token", text)
            self.assertIn("QG_TELEGRAM_CHAT_ID=123456", text)
            self.assertIn("QG_TELEGRAM_PUSH_ALLOWED=1", text)

    def test_extract_chat_candidates_private_only(self) -> None:
        updates = [
            {"update_id": 10, "message": {"message_id": 1, "chat": {"id": 123, "type": "private", "first_name": "Bo"}, "text": "/start"}},
            {"update_id": 11, "message": {"message_id": 2, "chat": {"id": -100, "type": "group", "title": "Group"}, "text": "hello"}},
        ]
        private = extract_chat_candidates(updates, private_only=True)
        self.assertEqual(len(private), 1)
        self.assertEqual(private[0]["chatId"], "123")
        all_chats = extract_chat_candidates(updates, private_only=False)
        self.assertEqual(len(all_chats), 2)

    def test_message_text_validation(self) -> None:
        self.assertEqual(validate_message_text(" hello "), "hello")
        with self.assertRaises(ValueError):
            validate_message_text("")
        with self.assertRaises(ValueError):
            validate_message_text("x" * 4097)

    def test_default_urlopen_is_available_for_system_cert_fallback(self) -> None:
        self.assertTrue(callable(default_urlopen))

if __name__ == "__main__":
    unittest.main()
