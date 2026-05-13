import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const files = [
  'tools/ga_multi_generation_stability/schema.py',
  'tools/ga_multi_generation_stability/io_utils.py',
  'tools/ga_multi_generation_stability/stability.py',
  'tools/ga_multi_generation_stability/telegram_text.py',
  'tools/run_ga_multi_generation_stability.py',
  'tools/production_evidence_validation/ga_audit.py',
  'tests/test_ga_multi_generation_stability.py',
];

for (const file of files) {
  test(`${file} is readable source`, () => {
    const text = readFileSync(file, 'utf8');
    const lines = text.split(/\r?\n/);
    assert.ok(lines.length >= 10, `${file} should be multi-line source`);
    const longLine = lines.find((line) => line.length > 220);
    assert.equal(longLine, undefined, `${file} has an overly long line`);
  });
}

test('GA stability audit does not introduce trading execution', () => {
  const text = files.map((file) => readFileSync(file, 'utf8')).join('\n');
  for (const token of ['OrderSend', 'PositionClose', 'TRADE_ACTION_DEAL', 'livePresetMutationAllowed = True']) {
    assert.equal(text.includes(token), false, `forbidden token found: ${token}`);
  }
});
