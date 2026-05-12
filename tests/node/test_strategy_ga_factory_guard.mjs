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

test('Strategy GA Factory exposes P4-4 API endpoints', () => {
  const server = read('Dashboard/dashboard_server.js');
  const routes = read('Dashboard/strategy_ga_factory_api_routes.js');
  const runner = read('tools/run_strategy_ga_factory.py');
  for (const marker of [
    "require('./strategy_ga_factory_api_routes')",
    'isStrategyGAFactoryPath',
    '/api/strategy-ga-factory/status',
    '/api/strategy-ga-factory/build',
    '/api/strategy-ga-factory/telegram-text',
    'run_strategy_ga_factory.py',
    'GA Factory',
  ]) {
    assert.match(`${server}\n${routes}\n${runner}`, new RegExp(marker.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }
});

test('Strategy GA Factory sources remain shadow-only and readable', () => {
  const files = [
    ...listFiles('tools/strategy_ga_factory'),
    'tools/run_strategy_ga_factory.py',
    'Dashboard/strategy_ga_factory_api_routes.js',
  ];
  const source = files.map(read).join('\n');
  for (const marker of [
    'QuantGod_GAFactoryState.json',
    'QuantGod_GAEliteArchive.json',
    'QuantGod_GAStrategyGraveyard.json',
    'QuantGod_GALineageTree.json',
    'QuantGod_GAFactoryLedger.csv',
    'ALLOWED_PROMOTION_STAGES',
    'PAPER_LIVE_SIM',
    'gaFactoryDirectLiveAllowed',
    'writesMt5OrderRequest',
  ]) {
    assert.match(source, new RegExp(marker));
  }
  assert.doesNotMatch(source, /OrderSend|OrderSendAsync|PositionClose|TRADE_ACTION_DEAL|CTrade/);
  assert.doesNotMatch(source, /livePresetMutationAllowed["']?\s*:\s*True/);
  for (const file of files) {
    const lines = read(file).split(/\r?\n/);
    assert.ok(lines.length >= 5, `${file} should stay readable`);
    lines.forEach((line, index) => {
      assert.ok(line.length <= 160, `${file}:${index + 1} should not exceed 160 characters`);
    });
  }
});
