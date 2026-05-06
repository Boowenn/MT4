from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schema import build_empty_status, default_safety, latest_path, ledger_path, now_iso, run_path, validate_safe_payload


@dataclass
class ChainStep:
    name: str
    label_zh: str
    command: List[str]
    required: bool = True
    timeout_seconds: int = 120


class AutomationChainRunner:
    def __init__(self, repo_root: str | Path, runtime_dir: str | Path, symbols: List[str], python_bin: str | None = None, max_age_seconds: int = 180):
        self.repo_root = Path(repo_root).resolve()
        self.runtime_dir = Path(runtime_dir)
        focus_symbols = [s.strip() for s in symbols if s.strip() and s.strip().upper().startswith("USDJPY")]
        self.symbols = focus_symbols or ["USDJPYc"]
        self.python_bin = python_bin or sys.executable
        self.max_age_seconds = max_age_seconds

    def _script(self, name: str) -> str:
        return str(self.repo_root / "tools" / name)

    def _symbols_arg(self) -> str:
        return ",".join(self.symbols)

    def build_steps(self, send: bool = False) -> List[ChainStep]:
        runtime = str(self.runtime_dir)
        symbols = self._symbols_arg()
        steps = [
            ChainStep("fastlane_quality", "P3-7 快通道质量", [self.python_bin, self._script("run_mt5_fastlane.py"), "--runtime-dir", runtime, "quality", "--symbols", symbols], required=False),
            ChainStep("adaptive_policy", "P3-6 自适应策略", [self.python_bin, self._script("run_adaptive_policy.py"), "--runtime-dir", runtime, "build", "--symbols", symbols], required=True),
            ChainStep("dynamic_sltp", "P3-8 动态止盈止损", [self.python_bin, self._script("run_dynamic_sltp.py"), "--runtime-dir", runtime, "build", "--symbols", symbols], required=True),
            ChainStep("entry_trigger", "P3-9 入场触发", [self.python_bin, self._script("run_entry_trigger_lab.py"), "--runtime-dir", runtime, "build", "--symbols", symbols], required=True),
            ChainStep("usdjpy_strategy_policy", "USDJPY 策略政策", [self.python_bin, self._script("run_usdjpy_strategy_lab.py"), "--runtime-dir", runtime, "build", "--write"], required=True),
            ChainStep("usdjpy_ea_dry_run", "USDJPY EA 干跑决策", [self.python_bin, self._script("run_usdjpy_strategy_lab.py"), "--runtime-dir", runtime, "dry-run", "--write"], required=True),
            ChainStep("usdjpy_live_loop", "USDJPY 实盘恢复闭环", [self.python_bin, self._script("run_usdjpy_live_loop.py"), "--runtime-dir", runtime, "once"], required=True),
        ]
        if send:
            steps.append(ChainStep("usdjpy_live_loop_telegram", "USDJPY 闭环 Telegram 中文推送", [self.python_bin, self._script("run_usdjpy_live_loop.py"), "--runtime-dir", runtime, "telegram-text", "--refresh", "--send"], required=False, timeout_seconds=60))
        return steps

    def _run_step(self, step: ChainStep) -> Dict[str, Any]:
        script_path = Path(step.command[1]) if len(step.command) > 1 else None
        if script_path and not script_path.exists():
            return {
                "name": step.name,
                "labelZh": step.label_zh,
                "ok": not step.required,
                "required": step.required,
                "skipped": True,
                "reason": f"脚本不存在：{script_path.name}",
                "summaryZh": "脚本不存在，已按缺失证据处理" if step.required else "脚本不存在，已跳过",
            }
        try:
            proc = subprocess.run(step.command, cwd=str(self.repo_root), text=True, capture_output=True, timeout=step.timeout_seconds, encoding="utf-8", errors="replace")
            ok = proc.returncode == 0
            stdout = (proc.stdout or "").strip()
            stderr = (proc.stderr or "").strip()
            return {
                "name": step.name,
                "labelZh": step.label_zh,
                "ok": ok,
                "required": step.required,
                "exitCode": proc.returncode,
                "summaryZh": "运行完成" if ok else "运行失败",
                "stdoutPreview": stdout[-2000:],
                "stderrPreview": stderr[-2000:],
                "commandPreview": " ".join(Path(x).name if i == 1 and x.endswith('.py') else x for i, x in enumerate(step.command)),
            }
        except subprocess.TimeoutExpired:
            return {
                "name": step.name,
                "labelZh": step.label_zh,
                "ok": False,
                "required": step.required,
                "exitCode": -1,
                "summaryZh": "运行超时",
                "reason": "timeout",
            }
        except Exception as exc:  # pragma: no cover
            return {
                "name": step.name,
                "labelZh": step.label_zh,
                "ok": False,
                "required": step.required,
                "exitCode": -1,
                "summaryZh": f"运行异常：{exc}",
                "reason": str(exc),
            }

    def _read_json(self, *parts: str) -> Optional[Dict[str, Any]]:
        path = self.runtime_dir.joinpath(*parts)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            return None

    def _policy_file(self) -> Optional[Dict[str, Any]]:
        return self._read_json("adaptive", "QuantGod_USDJPYAutoExecutionPolicy.json") or self._read_json("adaptive", "QuantGod_AutoExecutionPolicy.json")

    def _dry_run_file(self) -> Optional[Dict[str, Any]]:
        return self._read_json("adaptive", "QuantGod_USDJPYEADryRunDecision.json")

    def _live_loop_file(self) -> Optional[Dict[str, Any]]:
        return self._read_json("live", "QuantGod_USDJPYLiveLoopStatus.json")

    def _collect_missing_evidence(self) -> List[str]:
        checks = [
            (self.runtime_dir / "quality" / "QuantGod_MT5FastLaneQuality.json", "缺少 P3-7 快通道质量证据"),
            (self.runtime_dir / "adaptive" / "QuantGod_AdaptivePolicy.json", "缺少 P3-6 自适应策略输出"),
            (self.runtime_dir / "adaptive" / "QuantGod_DynamicSLTPCalibration.json", "缺少 P3-8 动态止盈止损校准"),
            (self.runtime_dir / "adaptive" / "QuantGod_EntryTriggerPlan.json", "缺少 P3-9 入场触发计划"),
            (self.runtime_dir / "adaptive" / "QuantGod_USDJPYAutoExecutionPolicy.json", "缺少 USDJPY 策略政策"),
            (self.runtime_dir / "adaptive" / "QuantGod_USDJPYEADryRunDecision.json", "缺少 USDJPY EA 干跑决策"),
            (self.runtime_dir / "live" / "QuantGod_USDJPYLiveLoopStatus.json", "缺少 USDJPY 实盘恢复闭环状态"),
        ]
        missing = [label for path, label in checks if not path.exists()]
        for symbol in self.symbols:
            if not (self.runtime_dir / f"QuantGod_MT5RuntimeSnapshot_{symbol}.json").exists():
                missing.append(f"缺少 {symbol} 运行快照")
        return missing

    def _direction_zh(self, direction: str) -> str:
        return "买入观察" if str(direction).upper() in {"LONG", "BUY"} else "卖出观察"

    def _entry_mode_zh(self, mode: str) -> str:
        return {
            "STANDARD_ENTRY": "标准入场",
            "OPPORTUNITY_ENTRY": "机会入场",
            "BLOCKED": "阻断",
        }.get(str(mode), str(mode))

    def _reason_text(self, row: Dict[str, Any]) -> str:
        if row.get("reason"):
            return str(row.get("reason"))
        reasons = row.get("reasons") or []
        if isinstance(reasons, str):
            return reasons
        if isinstance(reasons, list):
            return "；".join(str(item) for item in reasons[:4] if item)
        return ""

    def _actionable_blockers(self, rows: List[str]) -> List[str]:
        positive_only = {
            "运行快照通过",
            "USDJPY 运行快照可用",
            "快通道质量通过",
            "动态止盈止损可用",
        }
        cleaned: List[str] = []
        for raw in rows:
            text = str(raw or "").strip()
            if not text:
                continue
            parts = [part.strip() for part in text.replace("\n", "；").split("；") if part.strip()]
            actionable_parts = [part for part in parts if part not in positive_only]
            cleaned.extend(actionable_parts)
        return list(dict.fromkeys(cleaned))

    def _summarize_policy(self, policy: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        summary = {"opportunities": [], "blocked": [], "standardCount": 0, "opportunityCount": 0, "blockedCount": 0}
        if not policy:
            return summary
        for row in policy.get("strategies", []) or policy.get("policies", []) or []:
            item = {
                "symbol": row.get("symbol"),
                "direction": row.get("direction"),
                "directionZh": self._direction_zh(row.get("direction", "")),
                "entryMode": row.get("entryMode"),
                "entryModeZh": self._entry_mode_zh(row.get("entryMode", "")),
                "recommendedLot": row.get("recommendedLot", 0),
                "score": row.get("score", 0),
                "reason": self._reason_text(row),
            }
            if row.get("entryMode") == "STANDARD_ENTRY" and row.get("allowed"):
                summary["standardCount"] += 1
                summary["opportunities"].append(item)
            elif row.get("entryMode") == "OPPORTUNITY_ENTRY" and row.get("allowed"):
                summary["opportunityCount"] += 1
                summary["opportunities"].append(item)
            else:
                summary["blockedCount"] += 1
                summary["blocked"].append(item)
        return summary

    def _status_from_live_loop(self, live_loop: Optional[Dict[str, Any]], policy_summary: Dict[str, Any], failed_required: List[Dict[str, Any]], missing: List[str]) -> tuple[str, str]:
        if failed_required or missing:
            return "BLOCKED_MISSING_EVIDENCE", "阻断：USDJPY 证据不完整"
        live_state = str((live_loop or {}).get("state") or "")
        live_state_zh = str((live_loop or {}).get("stateZh") or "")
        if live_state == "READY_FOR_EXISTING_EA":
            return "READY_FOR_EXISTING_EA", live_state_zh or "RSI 买入路线已恢复，等待 EA 自身信号"
        if live_state == "POLICY_READY_PRESET_BLOCKED":
            return "POLICY_READY_PRESET_BLOCKED", live_state_zh or "政策已就绪，但实盘 preset 尚未完全恢复"
        if live_state == "EVIDENCE_MISSING":
            return "BLOCKED_MISSING_EVIDENCE", live_state_zh or "证据链不完整，EA 不应自动入场"
        if live_state == "POLICY_BLOCKED":
            return "BLOCKED_BY_USDJPY_POLICY", live_state_zh or "政策仍阻断，EA 不应自动入场"
        if policy_summary["standardCount"] or policy_summary["opportunityCount"]:
            return "READY_WITH_USDJPY_OPPORTUNITIES", "发现 USDJPY 可复核机会"
        return "BLOCKED_BY_USDJPY_POLICY", "阻断：USDJPY 策略政策未放行"

    def build_status(self) -> Dict[str, Any]:
        if not latest_path(self.runtime_dir).exists():
            return build_empty_status(self.runtime_dir, self.symbols)
        try:
            return json.loads(latest_path(self.runtime_dir).read_text(encoding="utf-8-sig"))
        except Exception:
            return build_empty_status(self.runtime_dir, self.symbols)

    def run_once(self, send: bool = False, write: bool = True) -> Dict[str, Any]:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        steps = [self._run_step(step) for step in self.build_steps(send=send)]
        missing = self._collect_missing_evidence()
        policy = self._policy_file()
        dry_run = self._dry_run_file()
        live_loop = self._live_loop_file()
        policy_summary = self._summarize_policy(policy)
        failed_required = [s for s in steps if s.get("required") and not s.get("ok")]
        blocked_reasons: List[str] = []
        for step in failed_required:
            blocked_reasons.append(f"{step.get('labelZh')}未通过：{step.get('summaryZh') or step.get('reason')}")
        blocked_reasons.extend(missing)
        blocked_reasons.extend([str(x) for x in (live_loop or {}).get("whyNoEntry", [])[:8] if x])
        blocked_reasons.extend([item.get("reason", "") for item in policy_summary.get("blocked", [])[:6] if item.get("reason")])
        blocked_reasons = self._actionable_blockers(blocked_reasons)
        state, state_zh = self._status_from_live_loop(live_loop, policy_summary, failed_required, missing)
        report = {
            "schema": "quantgod.automation_chain.v1",
            "generatedAt": now_iso(),
            "runtimeDir": str(self.runtime_dir),
            "symbols": self.symbols,
            "singleSourceOfTruth": "USDJPY_LIVE_LOOP",
            "sourceFiles": {
                "policy": str(self.runtime_dir / "adaptive" / "QuantGod_USDJPYAutoExecutionPolicy.json"),
                "dryRun": str(self.runtime_dir / "adaptive" / "QuantGod_USDJPYEADryRunDecision.json"),
                "liveLoop": str(self.runtime_dir / "live" / "QuantGod_USDJPYLiveLoopStatus.json"),
            },
            "state": state,
            "stateZh": state_zh,
            "steps": steps,
            "missingEvidence": sorted(set(missing)),
            "blockedReasons": [x for x in blocked_reasons if x],
            "policySummary": policy_summary,
            "topLiveEligiblePolicy": (live_loop or {}).get("topLiveEligiblePolicy") or (policy or {}).get("topLiveEligiblePolicy"),
            "topShadowPolicy": (live_loop or {}).get("topShadowPolicy") or (policy or {}).get("topShadowPolicy"),
            "dryRunDecision": dry_run,
            "liveLoopStatus": live_loop,
            "standardCount": policy_summary["standardCount"],
            "opportunityCount": policy_summary["opportunityCount"],
            "blockedCount": policy_summary["blockedCount"],
            "safety": default_safety(),
        }
        validate_safe_payload(report)
        if write:
            self.write_report(report)
        return report

    def write_report(self, report: Dict[str, Any]) -> None:
        target_dir = latest_path(self.runtime_dir).parent
        target_dir.mkdir(parents=True, exist_ok=True)
        text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
        latest_path(self.runtime_dir).write_text(text, encoding="utf-8")
        run_path(self.runtime_dir).write_text(text, encoding="utf-8")
        ledger = ledger_path(self.runtime_dir)
        exists = ledger.exists()
        with ledger.open("a", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=["generatedAt", "state", "stateZh", "standardCount", "opportunityCount", "blockedCount", "missingCount"])
            if not exists:
                writer.writeheader()
            writer.writerow({
                "generatedAt": report.get("generatedAt"),
                "state": report.get("state"),
                "stateZh": report.get("stateZh"),
                "standardCount": report.get("standardCount", 0),
                "opportunityCount": report.get("opportunityCount", 0),
                "blockedCount": report.get("blockedCount", 0),
                "missingCount": len(report.get("missingEvidence", [])),
            })


def loop_forever(runner: AutomationChainRunner, interval_seconds: int, send: bool = False) -> None:
    while True:
        report = runner.run_once(send=send, write=True)
        print(json.dumps({"generatedAt": report.get("generatedAt"), "state": report.get("state"), "stateZh": report.get("stateZh")}, ensure_ascii=False))
        time.sleep(max(5, int(interval_seconds)))
