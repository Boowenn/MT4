import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';
import assert from 'node:assert/strict';

const root = process.cwd();
const files = [
  'tools/ai_analysis/advisory_fusion.py',
  'tools/ai_analysis/deepseek_validator.py',
  'tools/run_ai_advisory_fusion.py',
  'tools/run_mt5_ai_telegram_monitor.py',
  'Dashboard/phase1_api_routes.js',
];

function read(path) {
  return readFileSync(join(root, path), 'utf8');
}

test('DeepSeek Telegram fusion does not introduce execution APIs', () => {
  const code = files.map(read).join('\n');
  const forbiddenCodePatterns = [
    /\.order_send\s*\(/i,
    /TRADE_ACTION_DEAL/i,
    /TRADE_ACTION_CLOSE/i,
    /MetaTrader5\s*\.\s*order/i,
    /place_order\s*\(/i,
    /cancel_order\s*\(/i,
    /close_position\s*\(/i,
    /modify_live_preset\s*\(/i,
  ];
  for (const pattern of forbiddenCodePatterns) {
    assert.equal(pattern.test(code), false, `forbidden execution code pattern found: ${pattern}`);
  }
});

test('DeepSeek Telegram fusion does not add Telegram command or webhook receivers', () => {
  const code = files.map(read).join('\n');
  const forbiddenCodePatterns = [/getUpdates\s*\(/, /setWebhook\s*\(/, /deleteWebhook\s*\(/, /answerCallbackQuery\s*\(/];
  for (const pattern of forbiddenCodePatterns) {
    assert.equal(pattern.test(code), false, `forbidden Telegram receiver pattern found: ${pattern}`);
  }
});

test('fusion safety payload keeps execution capabilities false', () => {
  const code = read('tools/ai_analysis/advisory_fusion.py') + '\n' + read('tools/run_ai_advisory_fusion.py');
  const requiredFalseFlags = [
    'orderSendAllowed',
    'closeAllowed',
    'cancelAllowed',
    'credentialStorageAllowed',
    'livePresetMutationAllowed',
    'canOverrideKillSwitch',
    'telegramCommandExecutionAllowed',
    'telegramWebhookReceiverAllowed',
    'webhookReceiverAllowed',
    'emailDeliveryAllowed',
  ];
  for (const flag of requiredFalseFlags) {
    assert.match(code, new RegExp(`"${flag}"\\s*:\\s*False`), `${flag} must be present and false in Python safety payload`);
  }
});


test('monitor includes fusion metadata and audit line after overlay patch', () => {
  const monitor = read('tools/run_mt5_ai_telegram_monitor.py');
  assert.match(monitor, /fuse_advisory_report/);
  assert.match(monitor, /advisory_fusion/);
  assert.match(monitor, /(融合审查|AI 共识|advisory_fusion)/);
});

test('Phase 1 exposes one-click DeepSeek Telegram route without execution flags', () => {
  const routes = read('Dashboard/phase1_api_routes.js');
  assert.match(routes, /\/api\/ai-analysis\/deepseek-telegram\/run/);
  assert.match(routes, /run_mt5_ai_telegram_monitor\.py/);
  assert.match(routes, /--send/);
  assert.match(routes, /orderSendAllowed:\s*false/);
  assert.match(routes, /livePresetMutationAllowed:\s*false/);
});
