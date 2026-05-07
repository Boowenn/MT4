import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const repo = process.cwd();

function read(rel) {
  return fs.readFileSync(path.join(repo, rel), 'utf8');
}

function listFiles(relDir) {
  return fs.readdirSync(path.join(repo, relDir))
    .filter((name) => name.endsWith('.py'))
    .map((name) => path.join(relDir, name));
}

test('USDJPY Strategy JSON backtest exposes USDJPY-scoped API endpoints', () => {
  const routes = read('Dashboard/usdjpy_strategy_lab_api_routes.js');
  for (const endpoint of [
    '/api/usdjpy-strategy-lab/strategy-backtest/status',
    '/api/usdjpy-strategy-lab/strategy-backtest/sample',
    '/api/usdjpy-strategy-lab/strategy-backtest/run',
    '/api/usdjpy-strategy-lab/strategy-backtest/telegram-text',
  ]) {
    assert.match(routes, new RegExp(endpoint.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }
});

test('USDJPY Strategy JSON backtest writes SQLite, trades, equity, and report artifacts', () => {
  const schema = read('tools/usdjpy_strategy_backtest/schema.py');
  const report = read('tools/usdjpy_strategy_backtest/report.py');
  const runner = read('tools/run_usdjpy_strategy_backtest.py');
  for (const marker of [
    'usdjpy.sqlite',
    'QuantGod_StrategyBacktestReport.json',
    'QuantGod_StrategyTrades.csv',
    'QuantGod_StrategyEquityCurve.csv',
    'STRATEGY_JSON_USDJPY_SQLITE_BACKTEST',
    'QG_TELEGRAM_COMMANDS_ALLOWED',
  ]) {
    assert.match(schema + report + runner, new RegExp(marker.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }
});

test('USDJPY Strategy JSON backtest does not introduce live execution or wallets', () => {
  const source = [
    ...listFiles('tools/usdjpy_strategy_backtest'),
    'tools/run_usdjpy_strategy_backtest.py',
  ].map(read).join('\n');

  assert.doesNotMatch(source, /TRADE_ACTION_DEAL|PositionClose|OrderSendAsync|CTrade/);
  assert.doesNotMatch(source, /privateKeyAllowed\s*["']?\s*:\s*true|polymarketRealMoneyAllowed\s*["']?\s*:\s*true/i);
  assert.match(source, /orderSendAllowed["']?\s*:\s*False/);
  assert.match(source, /livePresetMutationAllowed["']?\s*:\s*False/);
});

test('USDJPY Strategy JSON backtest Python sources stay readable and multi-line', () => {
  for (const file of [...listFiles('tools/usdjpy_strategy_backtest'), 'tools/run_usdjpy_strategy_backtest.py']) {
    const source = read(file);
    const lines = source.split(/\r?\n/);
    if (!file.endsWith('__init__.py')) {
      assert.ok(lines.length >= 20, `${file} should stay readable and multi-line`);
    }
    lines.forEach((line, index) => {
      assert.ok(line.length <= 180, `${file}:${index + 1} should not exceed 180 characters`);
    });
  }
});

