from __future__ import annotations

import hashlib
import json
from typing import Any, Dict


def _canonical_strategy_json(seed: Dict[str, Any]) -> str:
    """Return a stable representation for dedupe and lineage tracing."""
    return json.dumps(
        seed,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_text(value: str) -> str:
    """Hash text with the repository-wide SHA-256 convention."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def strategy_fingerprint(seed: Dict[str, Any]) -> str:
    """Build the Strategy JSON fingerprint used by GA duplicate checks."""
    canonical = _canonical_strategy_json(seed)
    return _sha256_text(canonical)
