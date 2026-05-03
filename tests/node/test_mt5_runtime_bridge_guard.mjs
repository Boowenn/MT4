import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..', '..');
const bridgeDir = path.join(repoRoot, 'tools', 'mt5_runtime_bridge');
const monitorPath = path.join(repoRoot, 'tools', 'run_mt5_ai_telegram_monitor.py');

function readIfExists(filePath) {
  return fs.existsSync(filePath) ? fs.readFileSync(filePath, 'utf8') : '';
}

test('MT5 runtime bridge files exist', () => {
  assert.ok(fs.existsSync(path.join(bridgeDir, 'reader.py')));
  assert.ok(fs.existsSync(path.join(bridgeDir, 'schema.py')));
  assert.ok(fs.existsSync(path.join(repoRoot, 'tools', 'run_mt5_runtime_bridge.py')));
});

test('runtime bridge keeps trading execution disabled', () => {
  const combined = ['reader.py', 'schema.py', 'freshness.py']
    .map((name) => readIfExists(path.join(bridgeDir, name)))
    .join('\n');
  assert.match(combined, /orderSendAllowed"?: False/);
  assert.match(combined, /telegramCommandExecutionAllowed"?: False/);
  assert.doesNotMatch(combined, /\.order_send\s*\(/);
  assert.doesNotMatch(combined, /OrderSend\s*\(/);
});

test('MT5 AI Telegram monitor reports runtime freshness fields when patched', () => {
  const text = readIfExists(monitorPath);
  assert.match(text, /runtimeFresh/);
  assert.match(text, /runtimeAgeSeconds/);
  assert.match(text, /fallback/);
});
