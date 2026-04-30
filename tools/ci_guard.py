from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    print(f"CI_GUARD_FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        fail(f"missing required file: {path.relative_to(ROOT)}")


def require_contains(path: Path, needle: str) -> None:
    text = read_text(path)
    if needle not in text:
        fail(f"{path.relative_to(ROOT)} must contain {needle!r}")


def require_not_contains(path: Path, needle: str) -> None:
    text = read_text(path)
    if needle in text:
        fail(f"{path.relative_to(ROOT)} must not contain stale text {needle!r}")


def parse_set_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in read_text(path).splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def check_expected_set_values(path: Path, expected: dict[str, str]) -> None:
    values = parse_set_file(path)
    for key, expected_value in expected.items():
        actual = values.get(key)
        if actual != expected_value:
            fail(
                f"{path.relative_to(ROOT)} drift: {key} expected "
                f"{expected_value!r}, got {actual!r}"
            )


def tracked_files() -> list[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        fail(f"unable to list tracked files: {exc}")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def check_secret_file_hygiene() -> None:
    allowed_env_files = {".env.example"}
    for rel in tracked_files():
        name = Path(rel).name.lower()
        if name.startswith(".env") and rel not in allowed_env_files:
            fail(f"tracked env file is not allowed: {rel}")
        if any(token in name for token in ("credential", "login_config", "password")):
            fail(f"tracked credential-like file name is not allowed: {rel}")
        if "secret" in name and not name.endswith(".example"):
            fail(f"tracked secret-like file name is not allowed: {rel}")


def main() -> None:
    app = ROOT / "frontend/src/App.vue"
    ea = ROOT / "MQL5/Experts/QuantGod_MultiStrategy.mq5"
    live_preset = ROOT / "MQL5/Presets/QuantGod_MT5_HFM_LivePilot.set"
    dist_index = ROOT / "Dashboard/vue-dist/index.html"

    require_contains(app, "function routeDowngradeLabel(row)")
    require_contains(app, "function routeNextStepText(row)")
    require_contains(app, "routeShortName(row) === route")
    require_contains(app, "return { ...direct, ...symbolState }")
    require_contains(app, "'降级模拟'")
    require_contains(app, "MA 已从实盘降级到模拟/候选观察")
    require_contains(app, "保持模拟/候选观察")
    require_not_contains(app, "'实盘暂停'")

    require_contains(ea, 'tradeStatus = "STARTUP_GUARD";')
    require_contains(ea, "PilotRsiBlockSellInUptrend && IsUptrendRegimeLabel(regime.label)")
    require_contains(ea, "PilotRsiRangeTightBuyOnly && IsRangeTightRegimeLabel(regime.label)")
    require_contains(ea, "RSI H1 SELL blocked in")

    check_expected_set_values(
        live_preset,
        {
            "DashboardBuild": "QuantGod-v3.17-mt5-startup-entry-guard",
            "Watchlist": "USDJPY",
            "ShadowMode": "false",
            "ReadOnlyMode": "false",
            "EnablePilotMA": "false",
            "EnablePilotRsiH1Candidate": "true",
            "EnablePilotRsiH1Live": "true",
            "PilotRsiBlockSellInUptrend": "true",
            "PilotRsiRangeTightBuyOnly": "true",
            "EnablePilotBBH1Live": "false",
            "EnablePilotMacdH1Live": "false",
            "EnablePilotSRM15Live": "false",
            "EnableNonRsiLegacyLiveAuthorization": "false",
            "NonRsiLegacyLiveAuthorizationTag": "",
            "PilotLotSize": "0.01",
            "PilotMaxTotalPositions": "1",
        },
    )

    require_contains(dist_index, "/vue/assets/index-")
    check_secret_file_hygiene()
    print("CI_GUARD_OK")


if __name__ == "__main__":
    main()
