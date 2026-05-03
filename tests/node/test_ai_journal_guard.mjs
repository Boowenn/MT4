import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';

const root = process.cwd();

function read(rel) {
  return readFileSync(join(root, rel), 'utf8');
}

test('AI journal modules are present and advisory-only', () => {
  assert.ok(existsSync(join(root, 'tools/ai_journal/writer.py')));
  assert.ok(existsSync(join(root, 'tools/ai_journal/kill_switch.py')));
  const schema = read('tools/ai_journal/schema.py');
  assert.match(schema, /orderSendAllowed"\s*:\s*False/);
  assert.match(schema, /telegramCommandExecutionAllowed"\s*:\s*False/);
  assert.doesNotMatch(schema, /send_order|order_send|OrderSend|trade\.Buy|trade\.Sell/);
});

test('Telegram text normalization exists for Chinese-only human messages', () => {
  const text = read('tools/ai_journal/telegram_text.py');
  assert.match(text, /ensure_chinese_telegram_text/);
  assert.match(text, /最终动作=/);
  assert.match(text, /偏多观察/);
  assert.match(text, /暂停/);
});

test('monitor is patched to journal and normalize Telegram text', () => {
  const monitor = read('tools/run_mt5_ai_telegram_monitor.py');
  assert.match(monitor, /apply_signal_kill_switch/);
  assert.match(monitor, /record_telegram_advisory/);
  assert.match(monitor, /ensure_chinese_telegram_text/);
  assert.match(monitor, /disable-journal/);
});
