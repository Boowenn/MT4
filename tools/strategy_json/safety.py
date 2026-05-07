from __future__ import annotations

from typing import Any, List

FORBIDDEN_TOKENS = {
    "ordersend",
    "ordersendasync",
    "trade_action_deal",
    "positionclose",
    "ordermodify",
    "ctrade",
    "privatekey",
    "mnemonic",
    "wallet",
    "webhook",
    "telegramcommand",
    "eval(",
    "exec(",
    "import ",
    "__",
    "lambda",
    "function",
    "subprocess",
    "os.system",
}

ALLOWED_SAFETY_KEYS = {
    "orderSendAllowed",
    "telegramCommandExecutionAllowed",
}


def find_forbidden_tokens(value: Any, path: str = "$") -> List[str]:
    """Scan Strategy JSON values for code, secrets, and execution primitives."""
    hits: List[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key not in ALLOWED_SAFETY_KEYS:
                hits.extend(find_forbidden_tokens(key, f"{path}.<key>"))
            hits.extend(find_forbidden_tokens(item, f"{path}.{key}"))
        return hits
    if isinstance(value, list):
        for index, item in enumerate(value):
            hits.extend(find_forbidden_tokens(item, f"{path}[{index}]"))
        return hits
    if isinstance(value, str):
        lowered = value.lower()
        for token in FORBIDDEN_TOKENS:
            if token in lowered:
                hits.append(f"{path}: {token}")
    return hits
