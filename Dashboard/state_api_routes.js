'use strict';

/**
 * QuantGod P2-3 SQLite state layer API routes.
 *
 * This module is read-only from HTTP. It shells out to the local Python CLI for
 * status/query commands and never exposes ingest/write endpoints to frontend.
 */

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const JSON_HEADERS = {
  'Content-Type': 'application/json; charset=utf-8',
  'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
  Pragma: 'no-cache',
  Expires: '0',
};

const STATE_API_SAFETY = Object.freeze({
  mode: 'QUANTGOD_P2_3_SQLITE_STATE_LAYER_V1',
  phase: 'P2-3',
  localOnly: true,
  statePersistenceOnly: true,
  researchOnly: true,
  advisoryOnly: true,
  readOnlyDataPlane: true,
  notificationPushOnly: true,
  canExecuteTrade: false,
  orderSendAllowed: false,
  closeAllowed: false,
  cancelAllowed: false,
  credentialStorageAllowed: false,
  livePresetMutationAllowed: false,
  canOverrideKillSwitch: false,
  canMutateGovernanceDecision: false,
  canPromoteOrDemoteRoute: false,
  telegramCommandExecutionAllowed: false,
  fundTransferAllowed: false,
  withdrawalAllowed: false,
});

const STATE_ENDPOINTS = new Set([
  '/api/state',
  '/api/state/status',
  '/api/state/config',
  '/api/state/events',
  '/api/state/ai-analysis',
  '/api/state/vibe-strategies',
  '/api/state/notifications',
]);

function urlOf(urlValue) {
  return new URL(urlValue || '/', 'http://127.0.0.1');
}

function urlPathOf(urlValue) {
  const pathname = urlOf(urlValue).pathname.replace(/\/+$/, '') || '/';
  return pathname;
}

function isStatePath(urlValue) {
  return STATE_ENDPOINTS.has(urlPathOf(urlValue));
}

function sendJson(res, statusCode, payload) {
  for (const [k, v] of Object.entries(JSON_HEADERS)) {
    res.setHeader(k, v);
  }
  res.writeHead(statusCode);
  res.end(JSON.stringify(payload, null, 2));
}

function sendError(res, statusCode, endpoint, error, extra = {}) {
  sendJson(res, statusCode, {
    ok: false,
    endpoint,
    error: error && error.message ? error.message : String(error),
    safety: STATE_API_SAFETY,
    ...extra,
  });
}

function positiveLimit(searchParams, fallback = 50) {
  const parsed = Number.parseInt(searchParams.get('limit') || String(fallback), 10);
  if (!Number.isFinite(parsed) || parsed <= 0) return fallback;
  return Math.max(1, Math.min(parsed, 500));
}

function pythonBin() {
  return process.env.QG_PYTHON_BIN || process.env.QG_PYTHON || process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
}

function stateDbPath(ctx = {}) {
  if (process.env.QG_STATE_DB) return path.resolve(process.env.QG_STATE_DB);
  const repoRoot = ctx.repoRoot || path.resolve(ctx.rootDir || __dirname, '..');
  return path.join(repoRoot, 'runtime', 'quantgod_state.sqlite');
}

function baseArgs(ctx = {}) {
  const repoRoot = ctx.repoRoot || path.resolve(ctx.rootDir || __dirname, '..');
  const args = [path.join('tools', 'run_state_store.py'), '--repo-root', repoRoot, '--db', stateDbPath(ctx)];
  const runtimeDir = ctx.defaultRuntimeDir || ctx.runtimeDir;
  if (runtimeDir) args.push('--runtime-dir', runtimeDir);
  const dashboardDir = ctx.rootDir || path.join(repoRoot, 'Dashboard');
  if (dashboardDir) args.push('--dashboard-dir', dashboardDir);
  return args;
}

function argsForEndpoint(req, ctx = {}) {
  const url = urlOf(req.url || '/');
  const endpoint = url.pathname.replace(/\/+$/, '') || '/';
  const args = baseArgs(ctx);

  if (endpoint === '/api/state' || endpoint === '/api/state/status') {
    return args.concat(['status']);
  }
  if (endpoint === '/api/state/config') {
    return args.concat(['config']);
  }
  if (endpoint === '/api/state/events') {
    args.push('events', '--limit', String(positiveLimit(url.searchParams)));
    const eventType = String(url.searchParams.get('eventType') || url.searchParams.get('event_type') || '').trim();
    const source = String(url.searchParams.get('source') || '').trim();
    if (eventType) args.push('--event-type', eventType);
    if (source) args.push('--source', source);
    return args;
  }
  if (endpoint === '/api/state/ai-analysis') {
    args.push('ai-runs', '--limit', String(positiveLimit(url.searchParams)));
    const symbol = String(url.searchParams.get('symbol') || '').trim();
    if (symbol) args.push('--symbol', symbol);
    return args;
  }
  if (endpoint === '/api/state/vibe-strategies') {
    return args.concat(['vibe-strategies', '--limit', String(positiveLimit(url.searchParams))]);
  }
  if (endpoint === '/api/state/notifications') {
    return args.concat(['notifications', '--limit', String(positiveLimit(url.searchParams))]);
  }
  return null;
}

function runStateCli(args, ctx = {}, timeoutMs = 15000) {
  return new Promise((resolve) => {
    const repoRoot = ctx.repoRoot || path.resolve(ctx.rootDir || __dirname, '..');
    const script = path.join(repoRoot, 'tools', 'run_state_store.py');
    if (!fs.existsSync(script)) {
      resolve({ ok: false, skipped: true, error: 'state_store_cli_not_found', script, safety: STATE_API_SAFETY });
      return;
    }

    const child = spawn(pythonBin(), args, {
      cwd: repoRoot,
      shell: false,
      windowsHide: true,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    });

    let settled = false;
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      child.kill();
      resolve({ ok: false, error: 'timeout', stdout, stderr, safety: STATE_API_SAFETY });
    }, timeoutMs);

    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString('utf8');
    });
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString('utf8');
    });
    child.on('error', (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({ ok: false, error: error.message, stdout, stderr, safety: STATE_API_SAFETY });
    });
    child.on('close', (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (code !== 0) {
        resolve({ ok: false, exitCode: code, error: stderr.trim() || stdout.trim() || `python exited ${code}`, stdout, stderr, safety: STATE_API_SAFETY });
        return;
      }
      try {
        const payload = JSON.parse(stdout || '{}');
        resolve({ ...payload, safety: { ...STATE_API_SAFETY, ...(payload.safety || {}) } });
      } catch (error) {
        resolve({ ok: false, error: `python returned non-JSON output: ${error.message}`, stdout, stderr, safety: STATE_API_SAFETY });
      }
    });
  });
}

async function handle(req, res, ctx = {}) {
  const endpoint = urlPathOf(req.url || '/');
  const method = String(req.method || 'GET').toUpperCase();

  if (!isStatePath(req.url || '/')) {
    sendError(res, 404, endpoint, 'Unsupported state endpoint');
    return true;
  }
  if (method !== 'GET') {
    sendError(res, 405, endpoint, 'GET required');
    return true;
  }

  const args = argsForEndpoint(req, ctx);
  if (!args) {
    sendError(res, 404, endpoint, 'Unsupported state endpoint');
    return true;
  }

  const payload = await runStateCli(args, ctx);
  sendJson(res, payload.ok === false ? 500 : 200, {
    ...payload,
    endpoint,
    safety: { ...STATE_API_SAFETY, ...(payload.safety || {}) },
  });
  return true;
}

module.exports = {
  STATE_API_SAFETY,
  STATE_ENDPOINTS,
  argsForEndpoint,
  handle,
  isStatePath,
  sendError,
};
