import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const ROOT = process.cwd();
const files = [];

function walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    const stat = statSync(path);
    if (stat.isDirectory()) walk(path);
    else if (/\.(py|md)$/.test(name)) files.push(path);
  }
}

walk(join(ROOT, 'tools', 'adaptive_policy'));
files.push(join(ROOT, 'tools', 'run_adaptive_policy.py'));

test('adaptive policy remains advisory-only and read-only', () => {
  const text = files.map((file) => readFileSync(file, 'utf8')).join('\n');
  assert.match(text, /advisoryOnly/);
  assert.match(text, /orderSendAllowed/);
  assert.doesNotMatch(text, /orderSendAllowed["']?\s*[:=]\s*True/);
  assert.doesNotMatch(text, /closeAllowed["']?\s*[:=]\s*True/);
  assert.doesNotMatch(text, /cancelAllowed["']?\s*[:=]\s*True/);
  assert.doesNotMatch(text, /livePresetMutationAllowed["']?\s*[:=]\s*True/);
  assert.doesNotMatch(text, /telegramCommandExecutionAllowed["']?\s*[:=]\s*True/);
});

test('adaptive policy code does not write MT5 order or preset files', () => {
  const text = files.map((file) => readFileSync(file, 'utf8')).join('\n');
  assert.doesNotMatch(text, /OrderSend|PositionClose|OrderModify|TRADE_ACTION_DEAL|MqlTradeRequest/);
  assert.doesNotMatch(text, /MT5Preset|LivePreset|open\s*\([^)]*OrderRequest|write_text\s*\([^)]*OrderRequest/);
});

test('telegram-facing adaptive text is Chinese-first', () => {
  const text = readFileSync(join(ROOT, 'tools', 'adaptive_policy', 'telegram_text.py'), 'utf8');
  assert.match(text, /自适应策略审查/);
  assert.match(text, /不会下单/);
  assert.match(text, /买入观察/);
  assert.match(text, /卖出观察/);
});
