import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const repo = process.cwd();
const files = [
  'tools/run_usdjpy_bar_replay.py',
  'tools/usdjpy_bar_replay/schema.py',
  'tools/usdjpy_bar_replay/dataset_loader.py',
  'tools/usdjpy_bar_replay/market_clock.py',
  'tools/usdjpy_bar_replay/rsi_replay.py',
  'tools/usdjpy_bar_replay/entry_variants.py',
  'tools/usdjpy_bar_replay/exit_variants.py',
  'tools/usdjpy_bar_replay/replay_engine.py',
  'tools/usdjpy_bar_replay/metrics.py',
  'tools/usdjpy_bar_replay/telegram_text.py',
  'Dashboard/usdjpy_strategy_lab_api_routes.js',
];
const forbidden = /\b(OrderSend|OrderSendAsync|PositionClose|OrderModify|TRADE_ACTION_DEAL|CTrade\s*\(|livePresetMutationAllowed\s*[:=]\s*true|telegramCommandExecutionAllowed\s*[:=]\s*true)\b/;

function read(rel) {
  return fs.readFileSync(path.join(repo, rel), 'utf8');
}

test('P3-19 USDJPY bar replay files exist and stay read-only', () => {
  for (const file of files) {
    assert.ok(fs.existsSync(path.join(repo, file)), `${file} should exist`);
    assert.doesNotMatch(read(file), forbidden, `${file} must not contain execution primitives`);
  }
});

test('P3-19 causal replay forbids posterior-trigger leakage', () => {
  const schema = read('tools/usdjpy_bar_replay/schema.py');
  const replay = read('tools/usdjpy_bar_replay/replay_engine.py');
  const rsi = read('tools/usdjpy_bar_replay/rsi_replay.py');
  assert.match(schema, /FOCUS_SYMBOL\s*=\s*["']USDJPYc["']/);
  assert.match(schema, /"posteriorMayAffectTrigger": False/);
  assert.match(schema, /"posteriorUsedForScoringOnly": True/);
  assert.match(replay, /hardGatesNeverRelaxed/);
  assert.match(replay, /15\/30\/60\/120 分钟后验窗口只用于评分/);
  assert.match(rsi, /posteriorUsedForTrigger["']?: False/);
  assert.doesNotMatch(rsi, /posteriorR|posteriorPips|futureR|futurePips/);
});

test('P3-19 API is exposed only under USDJPY strategy lab', () => {
  const routes = read('Dashboard/usdjpy_strategy_lab_api_routes.js');
  assert.match(routes, /\/api\/usdjpy-strategy-lab\/bar-replay\/status/);
  assert.match(routes, /\/api\/usdjpy-strategy-lab\/bar-replay\/entry/);
  assert.match(routes, /\/api\/usdjpy-strategy-lab\/bar-replay\/exit/);
  assert.match(routes, /run_usdjpy_bar_replay\.py/);
  assert.doesNotMatch(routes, /\/api\/trade|writesMt5OrderRequest: true/);
});

