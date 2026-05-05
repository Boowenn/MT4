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
        self.symbols = [s.strip() for s in symbols if s.strip()]
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
            ChainStep("auto_execution_policy", "P3-11 自动执行政策", [self.python_bin, self._script("run_auto_execution_policy.py"), "--runtime-dir", runtime, "build", "--symbols", symbols, "--write"], required=True),
        ]
        if send:
            steps.append(ChainStep("auto_policy_telegram", "自动执行政策 Telegram 中文推送", [self.python_bin, self._script("run_auto_execution_policy.py"), "--runtime-dir", runtime, "telegram-text", "--symbols", symbols, "--send"], required=False, timeout_seconds=60))
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
        return self._read_json("adaptive", "QuantGod_AutoExecutionPolicy.json")

    def _collect_missing_evidence(self) -> List[str]:
        checks = [
            (self.runtime_dir / "quality" / "QuantGod_MT5FastLaneQuality.json", "缺少 P3-7 快通道质量证据"),
            (self.runtime_dir / "adaptive" / "QuantGod_AdaptivePolicy.json", "缺少 P3-6 自适应策略输出"),
            (self.runtime_dir / "adaptive" / "QuantGod_DynamicSLTPCalibration.json", "缺少 P3-8 动态止盈止损校准"),
            (self.runtime_dir / "adaptive" / "QuantGod_EntryTriggerPlan.json", "缺少 P3-9 入场触发计划"),
            (self.runtime_dir / "adaptive" / "QuantGod_AutoExecutionPolicy.json", "缺少 P3-11 自动执行政策"),
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

    def _summarize_policy(self, policy: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        summary = {"opportunities": [], "blocked": [], "standardCount": 0, "opportunityCount": 0, "blockedCount": 0}
        if not policy:
            return summary
        for row in policy.get("policies", []) or []:
            item = {
                "symbol": row.get("symbol"),
                "direction": row.get("direction"),
                "directionZh": self._direction_zh(row.get("direction", "")),
                "entryMode": row.get("entryMode"),
                "entryModeZh": self._entry_mode_zh(row.get("entryMode", "")),
                "recommendedLot": row.get("recommendedLot", 0),
                "score": row.get("score", 0),
                "reason": row.get("reason", ""),
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
        policy_summary = self._summarize_policy(policy)
        failed_required = [s for s in steps if s.get("required") and not s.get("ok")]
        blocked_reasons: List[str] = []
        for step in failed_required:
            blocked_reasons.append(f"{step.get('labelZh')}未通过：{step.get('summaryZh') or step.get('reason')}")
        blocked_reasons.extend(missing)
        blocked_reasons.extend([item.get("reason", "") for item in policy_summary.get("blocked", [])[:6] if item.get("reason")])
        if failed_required or missing:
            state = "BLOCKED_MISSING_EVIDENCE"
            state_zh = "阻断：证据不完整"
        elif policy_summary["standardCount"] or policy_summary["opportunityCount"]:
            state = "READY_WITH_OPPORTUNITIES"
            state_zh = "发现可复核机会"
        else:
            state = "BLOCKED_BY_POLICY"
            state_zh = "阻断：策略政策未放行"
        report = {
            "schema": "quantgod.automation_chain.v1",
            "generatedAt": now_iso(),
            "runtimeDir": str(self.runtime_dir),
            "symbols": self.symbols,
            "state": state,
            "stateZh": state_zh,
            "steps": steps,
            "missingEvidence": sorted(set(missing)),
            "blockedReasons": [x for x in blocked_reasons if x],
            "policySummary": policy_summary,
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
