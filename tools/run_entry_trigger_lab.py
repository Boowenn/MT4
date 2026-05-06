#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
from typing import List
from entry_trigger_lab.data_loader import sample_runtime
from entry_trigger_lab.trigger_engine import build_trigger_plan, write_trigger_plan
from entry_trigger_lab.telegram_text import build_telegram_text

def _symbols(raw: str) -> List[str]: return [part.strip() for part in raw.split(",") if part.strip()]
def _runtime(path: str) -> Path: return Path(path).expanduser().resolve()

def cmd_status(args):
    runtime_dir=_runtime(args.runtime_dir); plan=runtime_dir/"adaptive"/"QuantGod_EntryTriggerPlan.json"
    print(json.dumps({"schema":"quantgod.entry_trigger_lab.status.v1","runtimeDir":str(runtime_dir),"runtimeExists":runtime_dir.exists(),"planExists":plan.exists(),"safety":{"readOnlyDataPlane":True,"advisoryOnly":True,"orderSendAllowed":False,"brokerExecutionAllowed":False,"telegramCommandExecutionAllowed":False}}, ensure_ascii=False, indent=2)); return 0

def cmd_sample(args):
    runtime_dir=_runtime(args.runtime_dir); sample_runtime(runtime_dir, _symbols(args.symbols), overwrite=args.overwrite)
    print(json.dumps({"ok":True,"runtimeDir":str(runtime_dir),"symbols":_symbols(args.symbols)}, ensure_ascii=False, indent=2)); return 0

def cmd_build(args):
    runtime_dir=_runtime(args.runtime_dir); payload=build_trigger_plan(runtime_dir, _symbols(args.symbols), directions=_symbols(args.directions), timeframe=args.timeframe); path=write_trigger_plan(runtime_dir,payload)
    print(json.dumps({"ok":True,"path":str(path),"decisionCount":len(payload.get("decisions",[]))}, ensure_ascii=False, indent=2)); return 0

def _load_plan(runtime_dir: Path):
    path=runtime_dir/"adaptive"/"QuantGod_EntryTriggerPlan.json"
    if not path.exists(): return build_trigger_plan(runtime_dir,["USDJPYc"])
    return json.loads(path.read_text(encoding="utf-8"))

def cmd_plan(args):
    runtime_dir=_runtime(args.runtime_dir); plan=_load_plan(runtime_dir)
    if args.symbol:
        plan=dict(plan); plan["decisions"]=[item for item in plan.get("decisions",[]) if item.get("symbol")==args.symbol]
    print(json.dumps(plan, ensure_ascii=False, indent=2)); return 0

def cmd_telegram_text(args):
    runtime_dir=_runtime(args.runtime_dir); plan=_load_plan(runtime_dir); text=build_telegram_text(plan, symbol=args.symbol); print(text)
    if args.send:
        if os.environ.get("QG_TELEGRAM_PUSH_ALLOWED") != "1":
            print("Telegram 发送被拒绝：QG_TELEGRAM_PUSH_ALLOWED 必须为 1。", file=sys.stderr); return 2
        try:
            from telegram_notifier.config import load_config
            from telegram_notifier.client import TelegramClient
            cfg = load_config(); result = TelegramClient(cfg).send_message(text)
            print(json.dumps({"telegramSent":True,"result":result}, ensure_ascii=False, indent=2))
        except Exception as exc:
            print(f"Telegram 发送失败：{exc}", file=sys.stderr); return 3
    return 0

def build_parser():
    parser=argparse.ArgumentParser(description="QuantGod P3-9 Entry Trigger Lab"); parser.add_argument("--runtime-dir", default="runtime"); sub=parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(func=cmd_status)
    p=sub.add_parser("sample"); p.add_argument("--symbols", default="USDJPYc"); p.add_argument("--overwrite", action="store_true"); p.set_defaults(func=cmd_sample)
    p=sub.add_parser("build"); p.add_argument("--symbols", default="USDJPYc"); p.add_argument("--directions", default="LONG,SHORT"); p.add_argument("--timeframe", default="M1/M5"); p.set_defaults(func=cmd_build)
    p=sub.add_parser("plan"); p.add_argument("--symbol"); p.set_defaults(func=cmd_plan)
    p=sub.add_parser("telegram-text"); p.add_argument("--symbol"); p.add_argument("--send", action="store_true"); p.set_defaults(func=cmd_telegram_text)
    return parser

def main():
    args=build_parser().parse_args(); return args.func(args)
if __name__ == "__main__": raise SystemExit(main())
