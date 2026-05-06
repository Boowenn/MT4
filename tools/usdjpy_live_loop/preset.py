from __future__ import annotations

from pathlib import Path
from typing import Any


PRESET_RELATIVE_PATH = Path("MQL5/Presets/QuantGod_MT5_HFM_LivePilot.set")


def read_set_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith(";") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def set_bool(values: dict[str, str], key: str, default: bool = False) -> bool:
    raw = str(values.get(key, "")).strip().lower()
    if raw in {"true", "1", "yes", "on"}:
        return True
    if raw in {"false", "0", "no", "off"}:
        return False
    return default


def set_float(values: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(str(values.get(key, default)).strip())
    except Exception:
        return default


def load_live_preset(repo_root: Path) -> dict[str, Any]:
    path = repo_root / PRESET_RELATIVE_PATH
    values = read_set_file(path)
    if not values:
        return {
            "found": False,
            "path": str(path),
            "ready": False,
            "reasons": ["未找到 HFM live preset，无法确认实盘 EA 恢复状态"],
        }
    checks = {
        "watchlistUsdJpy": values.get("Watchlist") in {"USDJPY", "USDJPYc"},
        "shadowOff": not set_bool(values, "ShadowMode", True),
        "readOnlyOff": not set_bool(values, "ReadOnlyMode", True),
        "autoTradingOn": set_bool(values, "EnablePilotAutoTrading", False),
        "rsiLiveOn": set_bool(values, "EnablePilotRsiH1Live", False),
        "maLiveOff": not set_bool(values, "EnablePilotMA", False),
        "bbLiveOff": not set_bool(values, "EnablePilotBBH1Live", False),
        "macdLiveOff": not set_bool(values, "EnablePilotMacdH1Live", False),
        "srLiveOff": not set_bool(values, "EnablePilotSRM15Live", False),
        "nonRsiAuthOff": not set_bool(values, "EnableNonRsiLegacyLiveAuthorization", False),
        "maxPositionsTwo": set_float(values, "PilotMaxTotalPositions", 1.0) >= 2.0,
        "manualIgnored": not set_bool(values, "PilotBlockManualPerSymbol", True),
    }
    failed = [key for key, ok in checks.items() if not ok]
    return {
        "found": True,
        "path": str(path),
        "ready": not failed,
        "checks": checks,
        "failedChecks": failed,
        "watchlist": values.get("Watchlist", ""),
        "maxEaPositions": int(set_float(values, "PilotMaxTotalPositions", 1.0)),
        "pilotLotSize": set_float(values, "PilotLotSize", 0.01),
        "maxFloatingLossUSC": set_float(values, "PilotMaxFloatingLossUSC", 30.0),
        "rsiBuyRoutePreserved": set_bool(values, "EnablePilotRsiH1Live", False),
        "allowedLiveRoute": "RSI_Reversal BUY",
        "shadowRoutes": ["MA_Cross", "BB_Triple", "MACD_Divergence", "SR_Breakout"],
        "reasons": ["preset 已允许 USDJPY RSI 买入路线"] if not failed else [f"preset 检查未通过：{', '.join(failed)}"],
    }

