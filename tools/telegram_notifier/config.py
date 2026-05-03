"""Local Telegram push-only configuration for QuantGod P3-2."""
from __future__ import annotations
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping

DEFAULT_ENV_FILE = ".env.telegram.local"
DEFAULT_API_BASE_URL = "https://api.telegram.org"


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on", "allow", "allowed"}


def parse_int(value: object, fallback: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def redact_value(value: str, *, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}…{value[-keep:]}"


def choose_value(key: str, env_values: Mapping[str, str], environ: Mapping[str, str], default: str = "") -> str:
    env_value = environ.get(key)
    if env_value is not None and str(env_value).strip() != "":
        return str(env_value).strip()
    file_value = env_values.get(key)
    if file_value is not None:
        return str(file_value).strip()
    return default


@dataclass(frozen=True)
class TelegramConfig:
    repo_root: Path
    env_file: Path
    bot_token: str
    chat_id: str
    push_allowed: bool
    commands_allowed: bool
    api_base_url: str
    timeout_seconds: int

    @property
    def token_configured(self) -> bool:
        return bool(self.bot_token)

    @property
    def chat_id_configured(self) -> bool:
        return bool(self.chat_id)

    @property
    def bot_token_redacted(self) -> str:
        return redact_value(self.bot_token)

    @property
    def chat_id_redacted(self) -> str:
        return redact_value(self.chat_id, keep=3)

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "repoRoot": str(self.repo_root),
            "envFile": str(self.env_file),
            "envFileExists": self.env_file.exists(),
            "botTokenConfigured": self.token_configured,
            "botTokenRedacted": self.bot_token_redacted,
            "chatIdConfigured": self.chat_id_configured,
            "chatIdRedacted": self.chat_id_redacted,
            "pushAllowed": self.push_allowed,
            "commandsAllowed": self.commands_allowed,
            "apiBaseUrl": self.api_base_url,
            "timeoutSeconds": self.timeout_seconds,
        }


def load_config(*, repo_root: Path | str | None = None, env_file: Path | str | None = None, environ: Mapping[str, str] | None = None) -> TelegramConfig:
    root = Path(repo_root).resolve() if repo_root else default_repo_root().resolve()
    env_path = Path(env_file).resolve() if env_file else (root / DEFAULT_ENV_FILE)
    env_values = parse_env_file(env_path)
    source_environ = os.environ if environ is None else environ
    return TelegramConfig(
        repo_root=root,
        env_file=env_path,
        bot_token=choose_value("QG_TELEGRAM_BOT_TOKEN", env_values, source_environ),
        chat_id=choose_value("QG_TELEGRAM_CHAT_ID", env_values, source_environ),
        push_allowed=truthy(choose_value("QG_TELEGRAM_PUSH_ALLOWED", env_values, source_environ, "0")),
        commands_allowed=truthy(choose_value("QG_TELEGRAM_COMMANDS_ALLOWED", env_values, source_environ, "0")),
        api_base_url=choose_value("QG_TELEGRAM_API_BASE_URL", env_values, source_environ, DEFAULT_API_BASE_URL).rstrip("/"),
        timeout_seconds=parse_int(choose_value("QG_TELEGRAM_TIMEOUT_SECONDS", env_values, source_environ, "15"), 15),
    )


def update_env_file(path: Path, updates: Mapping[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    output: list[str] = []
    if not existing_lines:
        output.extend([
            "# QuantGod P3-2 Telegram push-only local config.",
            "# Do not commit this file. Commit only .env.telegram.local.example.",
        ])
    for raw_line in existing_lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw_line:
            output.append(raw_line)
            continue
        key, _old_value = raw_line.split("=", 1)
        key = key.strip()
        if key in updates:
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(raw_line)
    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={value}")
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8", newline="\n")
