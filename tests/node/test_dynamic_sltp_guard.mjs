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
walk(join(ROOT, 'tools', 'dynamic_sltp'));
files.push(join(ROOT, 'tools', 'run_dynamic_sltp.py'));
const source = files.map((file) => readFileSync(file, 'utf8')).join('\n');

test('dynamic SLTP remains advisory-only and read-only', () => {
  assert.match(source, /readOnlyDataPlane/);
  assert.match(source, /dynamicSltpCalibrationOnly/);
  assert.doesNotMatch(source, /orderSendAllowed["']?\s*[:=]\s*True/);
  assert.doesNotMatch(source, /orderModifyAllowed["']?\s*[:=]\s*True/);
  assert.doesNotMatch(source, /brokerExecutionAllowed["']?\s*[:=]\s*True/);
});

test('dynamic SLTP does not contain MT5 execution operations', () => {
  assert.doesNotMatch(source, /\bOrderSend\b|\bOrderSendAsync\b|\bPositionClose\b|\bOrderModify\b|\bCTrade\b|TRADE_ACTION_DEAL/);
  assert.doesNotMatch(source, /\bOrderSend\b|\bOrderSendAsync\b|\bPositionClose\b|\bOrderModify\b|\bCTrade\b|TRADE_ACTION_DEAL/);
});

test('telegram-facing text is Chinese-first', () => {
  const text = readFileSync(join(ROOT, 'tools', 'dynamic_sltp', 'telegram_text.py'), 'utf8');
  assert.match(text, /动态止盈止损校准/);
  assert.match(text, /不会下单/);
  assert.match(text, /校准结论/);
});
