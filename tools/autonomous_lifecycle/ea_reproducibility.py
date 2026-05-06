from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Dict

try:
    from tools.usdjpy_strategy_lab.schema import FOCUS_SYMBOL, utc_now_iso
except ModuleNotFoundError:  # pragma: no cover
    from usdjpy_strategy_lab.schema import FOCUS_SYMBOL, utc_now_iso


def _sha256(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit(repo_root: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def _watchlist_hint(source_path: Path) -> str:
    text = source_path.read_text(encoding="utf-8", errors="ignore") if source_path.exists() else ""
    for line in text.splitlines():
        if "Watchlist" in line and "=" in line:
            return line.strip()[:160]
    return ""


def build_ea_reproducibility(runtime_dir: Path, *, repo_root: Path | None = None, write: bool = False) -> Dict[str, Any]:
    repo = Path(repo_root) if repo_root else Path(__file__).resolve().parents[2]
    runtime_dir = Path(runtime_dir)
    source = repo / "MQL5" / "Experts" / "QuantGod_MultiStrategy.mq5"
    preset = repo / "MQL5" / "Presets" / "QuantGod_MT5_HFM_LivePilot.set"
    ex5_candidates = [
        runtime_dir / "MQL5" / "Experts" / "QuantGod_MultiStrategy.ex5",
        repo / "MQL5" / "Experts" / "QuantGod_MultiStrategy.ex5",
    ]
    ex5 = next((path for path in ex5_candidates if path.exists()), ex5_candidates[0])
    watchlist_hint = _watchlist_hint(source)
    payload = {
        "ok": True,
        "schema": "quantgod.ea_reproducibility.v1",
        "generatedAtIso": utc_now_iso(),
        "symbol": FOCUS_SYMBOL,
        "eaSourceCommit": _git_commit(repo),
        "eaSourcePath": str(source),
        "eaSourceSha256": _sha256(source),
        "eaEx5Path": str(ex5),
        "eaEx5Sha256": _sha256(ex5),
        "presetPath": str(preset),
        "presetHash": _sha256(preset),
        "watchlistHint": watchlist_hint,
        "watchlistUsdJpyOnlyExpected": True,
        "accountModeExpected": "cent",
        "statusZh": "可对账" if _sha256(source) and _sha256(preset) else "缺少源码或 preset 对账文件",
        "safety": {
            "readOnly": True,
            "doesNotCompile": True,
            "doesNotMutatePreset": True,
            "orderSendAllowed": False,
        },
    }
    if write:
        out = runtime_dir / "agent"
        out.mkdir(parents=True, exist_ok=True)
        (out / "QuantGod_EABuildReproducibility.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload

