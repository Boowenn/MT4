'use strict';

/**
 * QuantGod Phase 1 local dashboard routes.
 *
 * This module is intentionally self-contained so it can be inserted near the
 * start of Dashboard/dashboard_server.js without depending on the server's
 * internal helpers. Every endpoint shells out to read-only/advisory Python
 * tools and returns JSON only on localhost.
 */

const { spawn } = require('child_process');
const path = require('path');

const MAX_BODY_BYTES = 128 * 1024;
const JSON_HEADERS = {
  'Content-Type': 'application/json; charset=utf-8',
  'Cache-Control': 'no-store',
};

const PHASE1_API_SAFETY = Object.freeze({
  localOnly: true,
  readOnly: true,
  advisoryOnly: true,
  orderSendAllowed: false,
  closeAllowed: false,
  cancelAllowed: false,
  credentialStorageAllowed: false,
  livePresetMutationAllowed: false,
  canOverrideKillSwitch: false,
  canMutateGovernanceDecision: false,
});

function sendJson(res, statusCode, payload) {
  const body = JSON.stringify(payload, null, 2);
  res.writeHead(statusCode, JSON_HEADERS);
  res.end(body);
}

function isPhase1Path(urlValue) {
  const url = new URL(urlValue || '/', 'http://127.0.0.1');
  const urlPath = url.pathname.replace(/\/+$/, '') || '/';
  return (
    urlPath === '/api/shadow-signals' ||
    urlPath.startsWith('/api/ai-analysis') ||
    urlPath === '/api/mt5-readonly/kline' ||
    urlPath === '/api/mt5-readonly/trades' ||
    urlPath === '/api/mt5-readonly/shadow-signals'
  );
}

function sendUnhandledError(res, error, endpoint = '/api/phase1') {
  sendJson(res, 500, {
    ok: false,
    mode: 'QUANTGOD_PHASE1_API_V1',
    endpoint,
    error: error && error.message ? error.message : String(error),
    safety: PHASE1_API_SAFETY,
  });
}

function notFoundPayload(urlPath) {
  return {
    ok: false,
    mode: 'QUANTGOD_PHASE1_API_V1',
    endpoint: urlPath,
    error: 'Unsupported Phase 1 endpoint',
    safety: PHASE1_API_SAFETY,
  };
}

function cleanSymbol(value) {
  const symbol = String(value || '').trim();
  if (!symbol) return '';
  return symbol.slice(0, 64);
}

function cleanTimeframes(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item || '').trim().toUpperCase()).filter(Boolean);
  }
  return String(value || 'M15,H1,H4,D1')
    .split(',')
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean);
}

function intInRange(value, fallback, min, max) {
  const parsed = Number.parseInt(String(value ?? ''), 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(min, Math.min(max, parsed));
}

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on('data', (chunk) => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        reject(new Error('Request body is too large'));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => {
      if (!chunks.length) {
        resolve({});
        return;
      }
      const raw = Buffer.concat(chunks).toString('utf8');
      try {
        resolve(JSON.parse(raw));
      } catch (error) {
        reject(new Error(`Invalid JSON body: ${error.message}`));
      }
    });
    req.on('error', reject);
  });
}

function runPythonJson(repoRoot, args, envOverrides = {}) {
  return new Promise((resolve, reject) => {
    const pythonBin = process.env.QG_PYTHON_BIN || process.env.QG_PYTHON || process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
    const child = spawn(pythonBin, args, {
      cwd: repoRoot,
      env: { ...process.env, ...envOverrides },
      shell: false,
      windowsHide: true,
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString('utf8');
    });
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString('utf8');
    });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(`python exited ${code}: ${stderr || stdout || 'no output'}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout || '{}'));
      } catch (error) {
        reject(new Error(`python returned non-JSON output: ${error.message}; stdout=${stdout.slice(0, 400)}`));
      }
    });
  });
}

function withPhase1Envelope(payload, endpoint) {
  if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
    return {
      ...payload,
      _phase1: {
        mode: 'QUANTGOD_PHASE1_API_V1',
        endpoint,
        safety: PHASE1_API_SAFETY,
      },
    };
  }
  return {
    ok: true,
    mode: 'QUANTGOD_PHASE1_API_V1',
    endpoint,
    value: payload,
    safety: PHASE1_API_SAFETY,
  };
}

function runtimeEnv(ctx) {
  const overrides = {};
  const runtimeDir = ctx && (ctx.defaultRuntimeDir || ctx.runtimeDir);
  if (runtimeDir) overrides.QG_RUNTIME_DIR = String(runtimeDir);
  return overrides;
}

async function handle(req, res, ctx = {}) {
  const repoRoot = ctx.repoRoot || path.resolve(__dirname, '..');
  const url = new URL(req.url || '/', 'http://127.0.0.1');
  const method = String(req.method || 'GET').toUpperCase();
  const urlPath = url.pathname.replace(/\/+$/, '') || '/';

  try {
    if (urlPath === '/api/ai-analysis/run') {
      if (method !== 'POST') {
        sendJson(res, 405, { ok: false, error: 'POST required', safety: PHASE1_API_SAFETY });
        return true;
      }
      const body = await readJsonBody(req);
      const symbol = cleanSymbol(body.symbol || url.searchParams.get('symbol'));
      if (!symbol) {
        sendJson(res, 400, { ok: false, error: 'symbol is required', safety: PHASE1_API_SAFETY });
        return true;
      }
      const timeframes = cleanTimeframes(body.timeframes || url.searchParams.get('timeframes')).join(',');
      const payload = await runPythonJson(
        repoRoot,
        [path.join('tools', 'run_ai_analysis.py'), 'run', '--symbol', symbol, '--timeframes', timeframes],
        runtimeEnv(ctx),
      );
      sendJson(res, 200, withPhase1Envelope(payload, urlPath));
      return true;
    }

    if (urlPath === '/api/ai-analysis/latest') {
      const payload = await runPythonJson(
        repoRoot,
        [path.join('tools', 'run_ai_analysis.py'), 'latest', '--allow-empty'],
        runtimeEnv(ctx),
      );
      sendJson(res, 200, withPhase1Envelope(payload || { ok: false, error: 'latest analysis not found' }, urlPath));
      return true;
    }

    if (urlPath === '/api/ai-analysis/history') {
      const symbol = cleanSymbol(url.searchParams.get('symbol'));
      const limit = intInRange(url.searchParams.get('limit'), 20, 1, 200);
      const args = [path.join('tools', 'run_ai_analysis.py'), 'history', '--limit', String(limit)];
      if (symbol) args.push('--symbol', symbol);
      const payload = await runPythonJson(repoRoot, args, runtimeEnv(ctx));
      sendJson(res, 200, withPhase1Envelope(payload, urlPath));
      return true;
    }

    if (urlPath.startsWith('/api/ai-analysis/history/')) {
      const id = decodeURIComponent(urlPath.split('/').pop() || '').slice(0, 180);
      const payload = await runPythonJson(
        repoRoot,
        [path.join('tools', 'run_ai_analysis.py'), 'history-item', '--id', id],
        runtimeEnv(ctx),
      );
      sendJson(res, payload && payload.ok === false ? 404 : 200, withPhase1Envelope(payload, urlPath));
      return true;
    }

    if (urlPath === '/api/ai-analysis/config') {
      const payload = await runPythonJson(
        repoRoot,
        [path.join('tools', 'run_ai_analysis.py'), 'config'],
        runtimeEnv(ctx),
      );
      sendJson(res, 200, withPhase1Envelope(payload, urlPath));
      return true;
    }

    if (urlPath === '/api/mt5-readonly/kline') {
      const symbol = cleanSymbol(url.searchParams.get('symbol'));
      if (!symbol) {
        sendJson(res, 400, { ok: false, error: 'symbol is required', safety: PHASE1_API_SAFETY });
        return true;
      }
      const tf = String(url.searchParams.get('tf') || 'H1').trim().toUpperCase();
      const bars = intInRange(url.searchParams.get('bars'), 200, 1, 2000);
      const payload = await runPythonJson(
        repoRoot,
        [path.join('tools', 'mt5_chart_readonly.py'), 'kline', '--symbol', symbol, '--tf', tf, '--bars', String(bars)],
        runtimeEnv(ctx),
      );
      sendJson(res, 200, withPhase1Envelope(payload, urlPath));
      return true;
    }

    if (urlPath === '/api/mt5-readonly/trades') {
      const symbol = cleanSymbol(url.searchParams.get('symbol'));
      if (!symbol) {
        sendJson(res, 400, { ok: false, error: 'symbol is required', safety: PHASE1_API_SAFETY });
        return true;
      }
      const days = intInRange(url.searchParams.get('days'), 30, 1, 365);
      const payload = await runPythonJson(
        repoRoot,
        [path.join('tools', 'mt5_chart_readonly.py'), 'trades', '--symbol', symbol, '--days', String(days)],
        runtimeEnv(ctx),
      );
      sendJson(res, 200, withPhase1Envelope(payload, urlPath));
      return true;
    }

    if (urlPath === '/api/shadow-signals' || urlPath === '/api/mt5-readonly/shadow-signals') {
      const symbol = cleanSymbol(url.searchParams.get('symbol'));
      if (!symbol) {
        sendJson(res, 400, { ok: false, error: 'symbol is required', safety: PHASE1_API_SAFETY });
        return true;
      }
      const days = intInRange(url.searchParams.get('days'), 7, 1, 365);
      const payload = await runPythonJson(
        repoRoot,
        [path.join('tools', 'mt5_chart_readonly.py'), 'shadow-signals', '--symbol', symbol, '--days', String(days)],
        runtimeEnv(ctx),
      );
      sendJson(res, 200, withPhase1Envelope(payload, urlPath));
      return true;
    }

    if (urlPath.startsWith('/api/ai-analysis/') || urlPath === '/api/shadow-signals') {
      sendJson(res, 404, notFoundPayload(urlPath));
      return true;
    }

    return false;
  } catch (error) {
    sendJson(res, 500, {
      ok: false,
      mode: 'QUANTGOD_PHASE1_API_V1',
      endpoint: urlPath,
      error: error && error.message ? error.message : String(error),
      safety: PHASE1_API_SAFETY,
    });
    return true;
  }
}

module.exports = {
  PHASE1_API_SAFETY,
  handle,
  isPhase1Path,
  sendUnhandledError,
};
