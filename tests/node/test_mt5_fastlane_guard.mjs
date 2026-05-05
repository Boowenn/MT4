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
    else if (/\.(py|mq5|md)$/.test(name)) files.push(path);
  }
}
walk(join(ROOT, 'tools', 'mt5_fastlane'));
files.push(join(ROOT, 'tools', 'run_mt5_fastlane.py'));

function text() {
  return files.map((file) => readFileSync(file, 'utf8')).join('\n');
}

test('MT5 fast lane remains read-only and advisory-only', () => {
  const source = text();
  assert.match(source, /readOnlyDataPlane/);
  assert.match(source, /orderSendAllowed/);
  assert.doesNotMatch(source, /orderSendAllowed["']?\s*[:=]\s*True/);
  assert.doesNotMatch(source, /closeAllowed["']?\s*[:=]\s*True/);
  assert.doesNotMatch(source, /cancelAllowed["']?\s*[:=]\s*True/);
  assert.doesNotMatch(source, /brokerExecutionAllowed["']?\s*[:=]\s*True/);
});

test('MQL5 exporter does not include trade execution calls or live preset mutation', () => {
  const source = text();
  assert.doesNotMatch(source, /\bOrderSend\b|\bOrderSendAsync\b|\bPositionClose\b|\bOrderModify\b|\bCTrade\b|TRADE_ACTION_DEAL/);
  assert.doesNotMatch(source, /LivePreset|MT5Preset|OrderRequest|writeLivePreset|mutatePreset/);
});

test('MQL5 exporter throttles tick writes using QG_TickFlushEvery', () => {
  const source = readFileSync(join(ROOT, 'tools', 'mt5_fastlane', 'QuantGodRuntimeFastLane.mq5'), 'utf8');
  assert.match(source, /input int QG_TickFlushEvery/);
  assert.match(source, /on_tick_sequence\+\+/);
  assert.match(source, /QG_TickFlushEvery/);
  assert.match(source, /return;\s*for\(int i = 0; i < ArraySize\(symbols\); i\+\+\)/s);
});

test('telegram-facing text is Chinese-first', () => {
  const source = readFileSync(join(ROOT, 'tools', 'mt5_fastlane', 'quality.py'), 'utf8');
  assert.match(source, /快通道质量审查/);
  assert.match(source, /不会下单/);
  assert.match(source, /品种质量/);
});
