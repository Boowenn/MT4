import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
const ROOT = process.cwd()
function read(relativePath) { return fs.readFileSync(path.join(ROOT, relativePath), 'utf8') }

test('Telegram notifier remains push-only and has no inbound command server', () => {
  const runner = read('tools/run_telegram_notifier.py')
  const safety = read('tools/telegram_notifier/safety.py')
  assert.match(safety, /telegramCommandExecutionAllowed[^\n]+False/)
  assert.match(safety, /telegramWebhookReceiverAllowed[^\n]+False/)
  assert.match(safety, /emailDeliveryAllowed[^\n]+False/)
  assert.doesNotMatch(runner, /\/buy|\/sell|\/close|\/cancel/i)
  assert.doesNotMatch(runner, /order_send|close_order|cancel_order|execute_trade/i)
  assert.doesNotMatch(runner, /http\.server|express\(|fastapi|flask/i)
  assert.doesNotMatch(runner, /setWebhook/)
})

test('Backend Docker image defaults Telegram push disabled and keeps token out of image', () => {
  const dockerfile = read('Dockerfile.local')
  assert.match(dockerfile, /QG_TELEGRAM_PUSH_ALLOWED=0/)
  assert.match(dockerfile, /QG_TELEGRAM_COMMANDS_ALLOWED=0/)
  assert.doesNotMatch(dockerfile, /QG_TELEGRAM_BOT_TOKEN\s*=/i)
  assert.doesNotMatch(dockerfile, /QG_TELEGRAM_CHAT_ID\s*=/i)
})

test('Telegram env example is disabled and contains no committed token', () => {
  const example = read('.env.telegram.local.example')
  assert.match(example, /QG_TELEGRAM_PUSH_ALLOWED=0/)
  assert.match(example, /QG_TELEGRAM_COMMANDS_ALLOWED=0/)
  assert.match(example, /QG_TELEGRAM_BOT_TOKEN=\s*(\n|$)/)
  assert.match(example, /QG_TELEGRAM_CHAT_ID=\s*(\n|$)/)
  assert.doesNotMatch(example, /[0-9]{5,}:[A-Za-z0-9_-]{20,}/)
})
