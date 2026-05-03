import assert from 'node:assert/strict';
import { test } from 'node:test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const routes = await import(path.resolve(__dirname, '../../Dashboard/state_api_routes.js'));

function makeRes() {
  return {
    statusCode: 0,
    headers: null,
    body: '',
    setHeader(key, value) {
      this.headers = { ...(this.headers || {}), [key]: value };
    },
    writeHead(statusCode, headers) {
      this.statusCode = statusCode;
      this.headers = { ...(this.headers || {}), ...(headers || {}) };
    },
    end(body) {
      this.body = String(body || '');
    },
  };
}

test('state route matcher only accepts /api/state endpoints', () => {
  assert.equal(routes.default.isStatePath('/api/state'), true);
  assert.equal(routes.default.isStatePath('/api/state/events?limit=5'), true);
  assert.equal(routes.default.isStatePath('/api/state/ai-analysis'), true);
  assert.equal(routes.default.isStatePath('/api/latest'), false);
  assert.equal(routes.default.isStatePath('/api/mt5/order/1'), false);
});

test('state API safety flags remain non-execution', () => {
  const safety = routes.default.STATE_API_SAFETY;
  assert.equal(safety.localOnly, true);
  assert.equal(safety.readOnlyDataPlane, true);
  for (const key of [
    'canExecuteTrade',
    'orderSendAllowed',
    'closeAllowed',
    'cancelAllowed',
    'credentialStorageAllowed',
    'livePresetMutationAllowed',
    'canOverrideKillSwitch',
    'canMutateGovernanceDecision',
    'canPromoteOrDemoteRoute',
    'telegramCommandExecutionAllowed',
  ]) {
    assert.equal(safety[key], false, key);
  }
});

test('state route rejects writes over HTTP', async () => {
  const res = makeRes();
  await routes.default.handle({ method: 'POST', url: '/api/state/events' }, res, {});
  const payload = JSON.parse(res.body);
  assert.equal(res.statusCode, 405);
  assert.equal(payload.ok, false);
  assert.equal(payload.safety.orderSendAllowed, false);
});

test('state route maps query endpoints to CLI read commands', () => {
  const args = routes.default.argsForEndpoint(
    { method: 'GET', url: '/api/state/events?limit=7&eventType=AI_ANALYSIS_RUN&source=ai-analysis' },
    { repoRoot: '/tmp/qg-backend', rootDir: '/tmp/qg-backend/Dashboard', defaultRuntimeDir: '/tmp/qg-runtime' },
  );
  assert.deepEqual(args.slice(-7), ['events', '--limit', '7', '--event-type', 'AI_ANALYSIS_RUN', '--source', 'ai-analysis']);
});
