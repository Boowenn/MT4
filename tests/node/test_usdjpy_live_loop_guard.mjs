import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const repoRoot = path.resolve(process.cwd());
const files = [
  'tools/usdjpy_live_loop/schema.py',
  'tools/usdjpy_live_loop/preset.py',
  'tools/usdjpy_live_loop/runner.py',
  'tools/usdjpy_live_loop/telegram_text.py',
  'tools/run_usdjpy_live_loop.py',
  'Dashboard/usdjpy_strategy_lab_api_routes.js',
];

const forbidden = /\b(OrderSend|OrderSendAsync|PositionClose|OrderModify|TRADE_ACTION_DEAL|CTrade\s*\(|MT5OrderRequest|writesMt5OrderRequest\s*[:=]\s*true|telegramCommandExecutionAllowed\s*[:=]\s*true|livePresetMutationAllowed\s*[:=]\s*true)\b/;

test('USDJPY live loop files exist', () => {
  for (const file of files) {
    assert.ok(fs.existsSync(path.join(repoRoot, file)), `${file} should exist`);
  }
});

test('USDJPY live loop exposes operator evidence endpoints', () => {
  const route = fs.readFileSync(path.join(repoRoot, 'Dashboard/usdjpy_strategy_lab_api_routes.js'), 'utf8');
  assert.match(route, /\/api\/usdjpy-strategy-lab\/live-loop/);
  assert.match(route, /\/api\/usdjpy-strategy-lab\/live-loop\/run/);
  assert.match(route, /\/api\/usdjpy-strategy-lab\/live-loop\/telegram-text/);
});

test('USDJPY live loop does not contain execution primitives', () => {
  for (const file of files) {
    const text = fs.readFileSync(path.join(repoRoot, file), 'utf8');
    assert.doesNotMatch(text, forbidden, `${file} must not contain execution primitives`);
  }
});

