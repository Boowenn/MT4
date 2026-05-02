"""Versioned registry for Vibe Coding generated strategies."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
from typing import Any

from .config import VibeCodingConfig, load_config, phase3_vibe_safety


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def slugify(value: str, fallback: str = "strategy") -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", value or "").strip("-").lower()
    return (text or fallback)[:64]


def code_hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]


@dataclass
class StrategyRecord:
    strategy_id: str
    version: str
    name: str
    description: str
    symbol: str | None
    timeframe: str | None
    code_path: str
    metadata_path: str
    code_hash: str
    created_at: str
    parent_version: str | None = None
    validation: dict[str, Any] | None = None
    backtests: list[dict[str, Any]] | None = None
    safety: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["safety"] = self.safety or phase3_vibe_safety()
        payload["backtests"] = self.backtests or []
        return payload


class StrategyRegistry:
    def __init__(self, config: VibeCodingConfig | None = None):
        self.config = config or load_config()
        self.config.strategy_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.config.strategy_dir / "index.json"

    def _load_index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"schema": "quantgod.vibe_strategies.v1", "updatedAt": utc_now(), "strategies": []}
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8-sig"))
        except Exception:
            return {"schema": "quantgod.vibe_strategies.v1", "updatedAt": utc_now(), "strategies": []}

    def _save_index(self, index: dict[str, Any]) -> None:
        index["updatedAt"] = utc_now()
        self.index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    def next_strategy_id(self, description: str, suggested_name: str | None = None) -> str:
        base = slugify(suggested_name or description)
        digest = hashlib.sha1(f"{description}|{utc_now()}".encode("utf-8")).hexdigest()[:8]
        return f"vibe-{base}-{digest}"

    def next_version(self, strategy_id: str) -> str:
        records = self.list_versions(strategy_id)
        return f"v{len(records) + 1}"

    def save_strategy(
        self,
        *,
        code: str,
        description: str,
        symbol: str | None = None,
        timeframe: str | None = None,
        strategy_id: str | None = None,
        name: str | None = None,
        parent_version: str | None = None,
        validation: dict[str, Any] | None = None,
    ) -> StrategyRecord:
        strategy_id = strategy_id or self.next_strategy_id(description, name)
        version = self.next_version(strategy_id)
        strategy_path = self.config.strategy_dir / strategy_id
        strategy_path.mkdir(parents=True, exist_ok=True)
        code_path = strategy_path / f"{version}.py"
        metadata_path = strategy_path / f"{version}.json"
        record = StrategyRecord(
            strategy_id=strategy_id,
            version=version,
            name=name or strategy_id,
            description=description,
            symbol=symbol,
            timeframe=timeframe,
            code_path=str(code_path),
            metadata_path=str(metadata_path),
            code_hash=code_hash(code),
            created_at=utc_now(),
            parent_version=parent_version,
            validation=validation,
            backtests=[],
            safety=phase3_vibe_safety(),
        )
        code_path.write_text(code, encoding="utf-8")
        metadata_path.write_text(json.dumps(record.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        index = self._load_index()
        index.setdefault("strategies", []).append(record.to_dict())
        self._save_index(index)
        return record

    def list_strategies(self) -> dict[str, Any]:
        index = self._load_index()
        grouped: dict[str, dict[str, Any]] = {}
        for rec in index.get("strategies", []):
            sid = rec.get("strategy_id")
            if not sid:
                continue
            group = grouped.setdefault(sid, {"strategy_id": sid, "versions": [], "latest": None})
            group["versions"].append(rec)
            group["latest"] = rec
        return {
            "ok": True,
            "schema": index.get("schema", "quantgod.vibe_strategies.v1"),
            "updatedAt": index.get("updatedAt"),
            "strategies": list(grouped.values()),
            "safety": phase3_vibe_safety(),
        }

    def list_versions(self, strategy_id: str) -> list[dict[str, Any]]:
        index = self._load_index()
        return [rec for rec in index.get("strategies", []) if rec.get("strategy_id") == strategy_id]

    def get_strategy(self, strategy_id: str, version: str | None = None, include_code: bool = True) -> dict[str, Any]:
        versions = self.list_versions(strategy_id)
        if not versions:
            return {"ok": False, "error": "strategy_not_found", "strategy_id": strategy_id, "safety": phase3_vibe_safety()}
        selected = versions[-1] if not version else next((rec for rec in versions if rec.get("version") == version), None)
        if not selected:
            return {"ok": False, "error": "version_not_found", "strategy_id": strategy_id, "version": version, "safety": phase3_vibe_safety()}
        payload = {"ok": True, "strategy": selected, "versions": versions, "safety": phase3_vibe_safety()}
        if include_code:
            code_path = Path(selected.get("code_path", ""))
            payload["code"] = code_path.read_text(encoding="utf-8") if code_path.exists() else ""
        return payload

    def append_backtest(self, strategy_id: str, version: str, result: dict[str, Any]) -> None:
        index = self._load_index()
        changed = False
        for rec in index.get("strategies", []):
            if rec.get("strategy_id") == strategy_id and rec.get("version") == version:
                rec.setdefault("backtests", []).append(result)
                meta_path = Path(rec.get("metadata_path", ""))
                if meta_path.exists():
                    meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
                    meta.setdefault("backtests", []).append(result)
                    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
                changed = True
        if changed:
            self._save_index(index)
