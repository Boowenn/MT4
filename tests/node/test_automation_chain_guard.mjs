import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';

const root = process.cwd();
const files = [
  'tools/run_automation_chain.py',
  'tools/automation_chain/runner.py',
  'tools/automation_chain/schema.py',
  'tools/automation_chain/telegram_text.py',
  'Dashboard/automation_chain_api_routes.js',
];

function read(rel) { return readFileSync(join(root, rel), 'utf8'); }

test('automation chain does not contain MT5 execution calls', () => {
  const forbidden = /OrderSend\s*\(|OrderSendAsync\s*\(|TRADE_ACTION_DEAL|PositionClose\s*\(|OrderModify\s*\(|\bCTrade\b|live preset mutation/i;
  for (const file of files) {
    assert.equal(forbidden.test(read(file)), false, `${file} contains forbidden execution wording`);
  }
});

test('automation chain exposes only local advisory safety flags', () => {
  const schema = read('tools/automation_chain/schema.py');
  assert.match(schema, /orderSendAllowed": False/);
  assert.match(schema, /telegramCommandsAllowed": False/);
  assert.match(schema, /doesNotPlaceOrders": True/);
});

test('dashboard route stays under api automation chain namespace', () => {
  const route = read('Dashboard/automation_chain_api_routes.js');
  assert.match(route, /\/api\/automation-chain/);
  assert.doesNotMatch(route, /\/api\/mt5\/order/);
  assert.doesNotMatch(route, /quick-trade/);
});

test('automation chain defaults to USDJPY scope only', () => {
  const combined = files.map((file) => read(file)).join('\n');
  assert.match(read('tools/run_automation_chain.py'), /USDJPYc/);
  assert.match(read('Dashboard/automation_chain_api_routes.js'), /DEFAULT_SYMBOLS\s*=\s*'USDJPYc'/);
  assert.doesNotMatch(combined, /USDJPYc,EURUSDc,XAUUSDc/);
  assert.doesNotMatch(combined, /EURUSDc/);
  assert.doesNotMatch(combined, /XAUUSDc/);
});
