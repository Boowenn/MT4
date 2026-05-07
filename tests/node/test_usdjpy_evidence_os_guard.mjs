import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const repo = process.cwd();

function read(rel) {
  return fs.readFileSync(path.join(repo, rel), 'utf8');
}

test('USDJPY evidence OS API endpoints are exposed under USDJPY namespace', () => {
  const routes = read('Dashboard/usdjpy_strategy_lab_api_routes.js');
  for (const endpoint of [
    '/api/usdjpy-strategy-lab/strategy-backtest/sync-klines',
    '/api/usdjpy-strategy-lab/evidence-os/status',
    '/api/usdjpy-strategy-lab/evidence-os/run',
    '/api/usdjpy-strategy-lab/evidence-os/parity',
    '/api/usdjpy-strategy-lab/evidence-os/execution-feedback',
    '/api/usdjpy-strategy-lab/evidence-os/case-memory',
    '/api/usdjpy-strategy-lab/evidence-os/telegram-text',
    '/api/usdjpy-strategy-lab/telegram-gateway/status',
    '/api/usdjpy-strategy-lab/telegram-gateway/test-event',
    '/api/usdjpy-strategy-lab/telegram-gateway/dispatch',
  ]) {
    assert.match(routes, new RegExp(endpoint.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }
});

test('evidence OS remains read-only and feeds GA scoring', () => {
  const source = [
    read('tools/usdjpy_evidence_os/schema.py'),
    read('tools/usdjpy_evidence_os/parity.py'),
    read('tools/usdjpy_evidence_os/execution_feedback.py'),
    read('tools/usdjpy_evidence_os/case_memory.py'),
    read('tools/usdjpy_evidence_os/telegram_gateway.py'),
    read('tools/run_telegram_gateway.py'),
    read('tools/strategy_ga/fitness.py'),
  ].join('\n');

  assert.match(source, /STRATEGY_JSON_PYTHON_REPLAY_MQL5_EA_PARITY/);
  assert.match(source, /QuantGod_LiveExecutionFeedback\.jsonl/);
  assert.match(source, /QuantGod_CaseMemory\.jsonl/);
  assert.match(source, /QuantGod_TelegramGatewayLedger\.jsonl/);
  assert.match(source, /QuantGod_NotificationEventQueue\.jsonl/);
  assert.match(source, /dispatch_pending/);
  assert.match(source, /gateway_status/);
  assert.match(source, /rate_limited/);
  assert.match(source, /PARITY_OR_EXECUTION_EVIDENCE_FAILED/);
  assert.doesNotMatch(source, /TRADE_ACTION_DEAL|OrderSendAsync|PositionClose|CTrade/);
  assert.doesNotMatch(source, /telegramCommandExecutionAllowed["']?\s*:\s*True/);
});
