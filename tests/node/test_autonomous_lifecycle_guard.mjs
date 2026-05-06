import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const repo = process.cwd();

function read(rel) {
  return fs.readFileSync(path.join(repo, rel), 'utf8');
}

test('autonomous lifecycle keeps the three-lane safety model explicit', () => {
  const lifecycle = read('tools/autonomous_lifecycle/lifecycle.py');
  const mt5 = read('tools/autonomous_lifecycle/mt5_shadow_lane.py');
  const polymarket = read('tools/autonomous_lifecycle/polymarket_shadow_lane.py');
  const cent = read('tools/autonomous_lifecycle/cent_account_rules.py');
  const daily = read('tools/daily_autopilot_v2/report.py');

  for (const marker of [
    '实盘要窄，模拟要宽，升降级要快，回滚要硬',
    'USDJPYc',
    'RSI_Reversal',
    'MT5_SHADOW',
    'POLYMARKET_SHADOW',
    'polymarketRealMoneyAllowed',
    'liveMutationAllowed',
  ]) {
    assert.match(lifecycle + mt5 + polymarket + daily, new RegExp(marker));
  }
  assert.match(cent, /QG_AUTO_MAX_LOT/);
  assert.match(cent, /2\.0/);
  assert.doesNotMatch(lifecycle + mt5 + polymarket + cent + daily, /OrderSend|TRADE_ACTION_DEAL|PositionClose|OrderSendAsync|CTrade/);
});

test('strategy policy no longer uses manual promotion language', () => {
  const policy = read('tools/usdjpy_strategy_lab/policy_builder.py');
  const patch = read('tools/usdjpy_autonomous_agent/config_patch.py');
  const state = read('tools/usdjpy_autonomous_agent/agent_state.py');

  assert.doesNotMatch(policy, /manualPromotionRequired["']?\s*:\s*True/);
  assert.match(patch, /patchWritable/);
  assert.doesNotMatch(patch, /patchAllowed/);
  assert.match(patch, /liveMutationAllowed/);
  assert.match(state, /executionStage/);
});

test('API exposes lifecycle and lane endpoints', () => {
  const routes = read('Dashboard/usdjpy_strategy_lab_api_routes.js');
  for (const endpoint of [
    '/api/usdjpy-strategy-lab/autonomous-agent/lifecycle',
    '/api/usdjpy-strategy-lab/autonomous-agent/lanes',
    '/api/usdjpy-strategy-lab/autonomous-agent/mt5-shadow',
    '/api/usdjpy-strategy-lab/autonomous-agent/polymarket-shadow',
    '/api/usdjpy-strategy-lab/autonomous-agent/ea-repro',
    '/api/usdjpy-strategy-lab/autonomous-agent/daily-autopilot-v2',
    '/api/usdjpy-strategy-lab/autonomous-agent/daily-autopilot-v2/run',
    '/api/usdjpy-strategy-lab/autonomous-agent/daily-autopilot-v2/telegram-text',
    '/api/usdjpy-strategy-lab/daily-todo',
    '/api/usdjpy-strategy-lab/daily-todo/run',
    '/api/usdjpy-strategy-lab/daily-todo/telegram-text',
    '/api/usdjpy-strategy-lab/daily-review',
    '/api/usdjpy-strategy-lab/daily-review/run',
    '/api/usdjpy-strategy-lab/daily-review/telegram-text',
  ]) {
    assert.match(routes, new RegExp(endpoint.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }
});

test('daily autopilot v2 keeps Chinese autonomous reporting and push-only safety', () => {
  const runner = read('tools/run_daily_autopilot_v2.py');
  const report = read('tools/daily_autopilot_v2/report.py');
  const text = read('tools/daily_autopilot_v2/telegram_text.py');

  for (const marker of ['今日自动作战计划', '今日自动复盘', 'MT5 模拟车道', 'Polymarket 模拟车道', '不会下单']) {
    assert.match(report + text, new RegExp(marker));
  }
  for (const marker of ['dailyTodo', 'dailyReview', 'completedByAgent', 'autoAppliedByAgent', 'requiresAutonomousGovernance', 'strategyJsonTodo', 'gaEvolutionTodo', 'telegramGatewayTodo', 'WAITING_NEXT_PHASE']) {
    assert.match(report, new RegExp(marker));
  }
  for (const marker of ['Strategy JSON', 'GA Evolution', 'Telegram Gateway', '下一阶段任务']) {
    assert.match(report + text, new RegExp(marker));
  }
  assert.doesNotMatch(report, /requiresManualReview|manualReview|readyForReview/);
  assert.match(runner, /QG_TELEGRAM_COMMANDS_ALLOWED/);
  assert.doesNotMatch(runner + report + text, /privateKeyAllowed\s*["']?\s*:\s*true|polymarketRealMoneyAllowed\s*["']?\s*:\s*true/);
});

test('autonomous lifecycle Python sources are not compressed into one-line files', () => {
  const files = [
    'tools/autonomous_lifecycle/lifecycle.py',
    'tools/autonomous_lifecycle/cent_account_rules.py',
    'tools/autonomous_lifecycle/mt5_shadow_lane.py',
    'tools/autonomous_lifecycle/polymarket_shadow_lane.py',
    'tools/usdjpy_autonomous_agent/config_patch.py',
    'tools/usdjpy_autonomous_agent/promotion_gate.py',
    'tools/daily_autopilot_v2/report.py',
  ];
  for (const file of files) {
    const source = read(file);
    const lines = source.split(/\r?\n/);
    assert.ok(lines.length >= 20, `${file} should stay readable and multi-line`);
    assert.ok(lines[0].length < 160, `${file} first line should not contain compressed source`);
    assert.doesNotMatch(lines[0], /def |class |import .*def /, `${file} first line looks compressed`);
  }
});
