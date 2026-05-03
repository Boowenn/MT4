"""Safety gates for Telegram push-only notification delivery."""
from __future__ import annotations
import os
from typing import Any
from .config import TelegramConfig, truthy

TELEGRAM_SAFETY: dict[str, Any] = {
    "mode": "QUANTGOD_P3_2_TELEGRAM_PUSH_ONLY_V1",
    "phase": "P3-2",
    "localOnly": True,
    "notificationPushOnly": True,
    "telegramAssociationPollingOnly": True,
    "telegramCommandExecutionAllowed": False,
    "telegramWebhookReceiverAllowed": False,
    "emailDeliveryAllowed": False,
    "advisoryOnly": True,
    "researchOnly": True,
    "readOnlyDataPlane": True,
    "canExecuteTrade": False,
    "orderSendAllowed": False,
    "closeAllowed": False,
    "cancelAllowed": False,
    "credentialStorageAllowed": False,
    "livePresetMutationAllowed": False,
    "canOverrideKillSwitch": False,
    "canMutateGovernanceDecision": False,
    "canPromoteOrDemoteRoute": False,
    "fundTransferAllowed": False,
    "withdrawalAllowed": False,
}


def safety_payload(config: TelegramConfig | None = None) -> dict[str, Any]:
    payload = dict(TELEGRAM_SAFETY)
    if config is not None:
        payload.update({
            "telegramPushAllowed": config.push_allowed,
            "telegramBotTokenConfigured": config.token_configured,
            "telegramChatIdConfigured": config.chat_id_configured,
            "telegramBotTokenRedacted": config.bot_token_redacted,
            "telegramChatIdRedacted": config.chat_id_redacted,
        })
    return payload


def assert_telegram_safety(config: TelegramConfig) -> None:
    if config.commands_allowed:
        raise RuntimeError("Telegram command execution is disabled: set QG_TELEGRAM_COMMANDS_ALLOWED=0")
    forbidden_truthy_env = {
        "QG_ORDER_SEND_ALLOWED": "order send must remain disabled",
        "QG_CLOSE_ALLOWED": "close must remain disabled",
        "QG_CANCEL_ALLOWED": "cancel must remain disabled",
        "QG_CREDENTIAL_STORAGE_ALLOWED": "credential storage must remain disabled",
        "QG_LIVE_PRESET_MUTATION_ALLOWED": "live preset mutation must remain disabled",
        "QG_KILL_SWITCH_OVERRIDE_ALLOWED": "Kill Switch override must remain disabled",
        "QG_EMAIL_DELIVERY_ALLOWED": "email delivery is outside P3-2 Telegram-only scope",
        "QG_WEBHOOK_RECEIVER_ALLOWED": "Telegram/webhook receivers are outside P3-2 scope",
    }
    for key, reason in forbidden_truthy_env.items():
        if truthy(os.environ.get(key)):
            raise RuntimeError(f"Unsafe environment: {key}=truthy; {reason}")


def require_token(config: TelegramConfig) -> None:
    if not config.bot_token:
        raise RuntimeError("Missing QG_TELEGRAM_BOT_TOKEN in environment or .env.telegram.local")


def require_chat_id(config: TelegramConfig) -> None:
    if not config.chat_id:
        raise RuntimeError("Missing QG_TELEGRAM_CHAT_ID. Run link --write-env after sending /start to the bot.")


def require_push_enabled(config: TelegramConfig) -> None:
    assert_telegram_safety(config)
    if not config.push_allowed:
        raise RuntimeError("Telegram push is disabled. Set QG_TELEGRAM_PUSH_ALLOWED=1 in .env.telegram.local to send.")
