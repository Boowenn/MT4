'use strict';
/**
 * QuantGod Phase 3 local dashboard API routes.
 *
 * Vibe Coding, AI Analysis V2, and K-line enhancements are local-first,
 * advisory/research-only surfaces. No endpoint sends orders, closes/cancels
 * tickets, stores credentials, mutates live presets, or bypasses Kill Switches.
 */
const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const MAX_BODY_BYTES = 256 * 1024;
const JSON_HEADERS = {
  'Content-Type': 'application/json; charset=utf-8',
  'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
  Pragma: 'no-cache',
  Expires: '0',
};

const PHASE3_API_SAFETY = Object.freeze({
  mode: 'QUANTGOD_PHASE3_API_V1',
  localOnly: true,
  researchOnly: true,
  advisoryOnly: true,
  readOnlyDataPlane: true,
  generatedCodeCanTradeLive: false,
  telegramCommandExecutionAllowed: false,
  orderSendAllowed: false,
  closeAllowed: false,
  cancelAllowed: false,
  credentialStorageAllowed: false,
  livePresetMutationAllowed: false,
  canOverrideKillSwitch: false,
  canMutateGovernanceDecision: false,
  canPromoteOrDemoteRoute: false,
});

function urlPathOf(urlValue) {
  const url = new URL(urlValue || '/', 'http://127.0.0.1');
  return url.pathname.replace(/\/+$/, '') || '/';
}

function isPhase3Path(urlValue) {
  const p = urlPathOf(urlValue);
  return (
    p === '/api/vibe-coding' ||
    p.startsWith('/api/vibe-coding/') ||
    p === '/api/ai-analysis-v2' ||
    p.startsWith('/api/ai-analysis-v2/') ||
    p === '/api/kline/ai-overlays' ||
    p === '/api/kline/vibe-indicators' ||
    p === '/api/kline/realtime-config'
  );
}

function sendJson(res, statusCode, payload) {
  res.writeHead(statusCode, JSON_HEADERS);
  res.end(JSON.stringify(payload, null, 2));
}

function sendError(res, statusCode, endpoint, error, extra = {}) {
  sendJson(res, statusCode, {
    ok: false,
    endpoint,
    error: error && error.message ? error.message : String(error),
    safety: PHASE3_API_SAFETY,
    ...extra,
  });
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
        resolve(JSON.parse(raw || '{}'));
      } catch (error) {
        reject(new Error(`Invalid JSON body: ${error.message}`));
      }
    });
    req.on('error', reject);
  });
}

function runtimeEnv(ctx = {}) {
  const env = { PYTHONIOENCODING: 'utf-8' };
  const runtimeDir = ctx.defaultRuntimeDir || ctx.runtimeDir;
  if (runtimeDir) env.QG_RUNTIME_DIR = String(runtimeDir);
  return env;
}

function runPythonJson(repoRoot, args, envOverrides = {}, timeoutMs = 45000) {
  return new Promise((resolve) => {
    const pythonBin = process.env.QG_PYTHON_BIN || process.env.QG_PYTHON || process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
    const child = spawn(pythonBin, args, {
      cwd: repoRoot,
      env: { ...process.env, ...envOverrides },
      shell: false,
      windowsHide: true,
    });
    let settled = false;
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      child.kill();
      resolve({ ok: false, error: 'timeout', stdout, stderr, safety: PHASE3_API_SAFETY });
    }, timeoutMs);
    child.stdout.on('data', (chunk) => { stdout += chunk.toString('utf8'); });
    child.stderr.on('data', (chunk) => { stderr += chunk.toString('utf8'); });
    child.on('error', (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({ ok: false, error: error.message, stdout, stderr, safety: PHASE3_API_SAFETY });
    });
    child.on('close', (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (code !== 0) {
        resolve({ ok: false, exitCode: code, error: stderr.trim() || stdout.trim() || `python exited ${code}`, stdout, stderr, safety: PHASE3_API_SAFETY });
        return;
      }
      try {
        resolve(JSON.parse(stdout || '{}'));
      } catch (error) {
        resolve({ ok: false, exitCode: code, error: `python returned non-JSON output: ${error.message}`, stdout, stderr, safety: PHASE3_API_SAFETY });
      }
    });
  });
}

function writePayloadFile(payload) {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'qg-phase3-'));
  const payloadPath = path.join(tempDir, 'payload.json');
  fs.writeFileSync(payloadPath, JSON.stringify(payload || {}, null, 2), 'utf8');
  return { tempDir, payloadPath };
}

async function runPythonWithPayload(repoRoot, scriptArgs, payload, env, timeoutMs) {
  const temp = writePayloadFile(payload);
  try {
    return await runPythonJson(repoRoot, [...scriptArgs, '--payload-file', temp.payloadPath], env, timeoutMs);
  } finally {
    try { fs.unlinkSync(temp.payloadPath); } catch (_) {}
    try { fs.rmdirSync(temp.tempDir); } catch (_) {}
  }
}

function intInRange(value, fallback, min, max) {
  const n = Number.parseInt(String(value ?? ''), 10);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(min, Math.min(max, n));
}

async function handleVibe(req, res, ctx, endpoint) {
  const repoRoot = ctx.repoRoot || path.resolve(ctx.rootDir || __dirname, '..');
  const method = String(req.method || 'GET').toUpperCase();
  const url = new URL(req.url || '/', 'http://127.0.0.1');
  const env = runtimeEnv(ctx);
  const script = path.join('tools', 'run_vibe_coding.py');

  if (endpoint === '/api/vibe-coding/config' || endpoint === '/api/vibe-coding') {
    if (method !== 'GET') return sendError(res, 405, endpoint, 'GET required');
    const payload = await runPythonJson(repoRoot, [script, 'config'], env, 20000);
    return sendJson(res, payload.ok === false ? 500 : 200, { ...payload, endpoint, safety: payload.safety || PHASE3_API_SAFETY });
  }
  if (endpoint === '/api/vibe-coding/generate') {
    if (method !== 'POST') return sendError(res, 405, endpoint, 'POST required');
    const body = await readJsonBody(req);
    const payload = await runPythonWithPayload(repoRoot, [script, 'generate'], body, env, 60000);
    return sendJson(res, payload.ok === false ? 500 : 200, { ...payload, endpoint, safety: payload.safety || PHASE3_API_SAFETY });
  }
  if (endpoint === '/api/vibe-coding/import-library') {
    if (method !== 'POST') return sendError(res, 405, endpoint, 'POST required');
    const body = await readJsonBody(req);
    const payload = await runPythonWithPayload(repoRoot, [script, 'import-library'], body, env, 60000);
    return sendJson(res, payload.ok === false ? 500 : 200, { ...payload, endpoint, safety: payload.safety || PHASE3_API_SAFETY });
  }
  if (endpoint === '/api/vibe-coding/iterate') {
    if (method !== 'POST') return sendError(res, 405, endpoint, 'POST required');
    const body = await readJsonBody(req);
    const payload = await runPythonWithPayload(repoRoot, [script, 'iterate'], body, env, 60000);
    return sendJson(res, payload.ok === false ? 500 : 200, { ...payload, endpoint, safety: payload.safety || PHASE3_API_SAFETY });
  }
  if (endpoint === '/api/vibe-coding/backtest') {
    if (method !== 'POST') return sendError(res, 405, endpoint, 'POST required');
    const body = await readJsonBody(req);
    const payload = await runPythonWithPayload(repoRoot, [script, 'backtest'], body, env, 90000);
    return sendJson(res, payload.ok === false ? 500 : 200, { ...payload, endpoint, safety: payload.safety || PHASE3_API_SAFETY });
  }
  if (endpoint === '/api/vibe-coding/analyze') {
    if (method !== 'POST') return sendError(res, 405, endpoint, 'POST required');
    const body = await readJsonBody(req);
    const payload = await runPythonWithPayload(repoRoot, [script, 'analyze'], body, env, 60000);
    return sendJson(res, payload.ok === false ? 500 : 200, { ...payload, endpoint, safety: payload.safety || PHASE3_API_SAFETY });
  }
  if (endpoint === '/api/vibe-coding/strategies') {
    if (method !== 'GET') return sendError(res, 405, endpoint, 'GET required');
    const payload = await runPythonJson(repoRoot, [script, 'list'], env, 20000);
    return sendJson(res, payload.ok === false ? 500 : 200, { ...payload, endpoint, safety: payload.safety || PHASE3_API_SAFETY });
  }
  if (endpoint.startsWith('/api/vibe-coding/strategy/')) {
    if (method !== 'GET') return sendError(res, 405, endpoint, 'GET required');
    const id = decodeURIComponent(endpoint.split('/').pop() || '').slice(0, 180);
    const args = [script, 'get', '--strategy-id', id];
    const version = url.searchParams.get('version');
    if (version) args.push('--version', String(version).slice(0, 40));
    const payload = await runPythonJson(repoRoot, args, env, 20000);
    return sendJson(res, payload.ok === false ? 404 : 200, { ...payload, endpoint, safety: payload.safety || PHASE3_API_SAFETY });
  }
  return sendError(res, 404, endpoint, 'Unsupported Vibe Coding endpoint');
}

async function handleAiV2(req, res, ctx, endpoint) {
  const repoRoot = ctx.repoRoot || path.resolve(ctx.rootDir || __dirname, '..');
  const method = String(req.method || 'GET').toUpperCase();
  const url = new URL(req.url || '/', 'http://127.0.0.1');
  const env = runtimeEnv(ctx);
  const script = path.join('tools', 'run_ai_analysis_v2.py');
  if (endpoint === '/api/ai-analysis-v2/config' || endpoint === '/api/ai-analysis-v2') {
    const payload = await runPythonJson(repoRoot, [script, 'config'], env, 20000);
    return sendJson(res, payload.ok === false ? 500 : 200, { ...payload, endpoint, safety: payload.safety || PHASE3_API_SAFETY });
  }
  if (endpoint === '/api/ai-analysis-v2/run') {
    if (method !== 'POST') return sendError(res, 405, endpoint, 'POST required');
    const body = await readJsonBody(req);
    const symbol = String(body.symbol || url.searchParams.get('symbol') || '').trim();
    if (!symbol) return sendError(res, 400, endpoint, 'symbol is required');
    const timeframes = Array.isArray(body.timeframes) ? body.timeframes.join(',') : String(body.timeframes || url.searchParams.get('timeframes') || 'M15,H1,H4,D1');
    const payload = await runPythonJson(repoRoot, [script, 'run', '--symbol', symbol.slice(0, 64), '--timeframes', timeframes.slice(0, 80)], env, 90000);
    return sendJson(res, payload.ok === false ? 500 : 200, { ...payload, endpoint, safety: payload.safety || PHASE3_API_SAFETY });
  }
  if (endpoint === '/api/ai-analysis-v2/latest') {
    const payload = await runPythonJson(repoRoot, [script, 'latest', '--allow-empty'], env, 20000);
    return sendJson(res, payload.ok === false ? 404 : 200, { ...payload, endpoint, safety: payload.safety || PHASE3_API_SAFETY });
  }
  if (endpoint === '/api/ai-analysis-v2/history') {
    const args = [script, 'history', '--limit', String(intInRange(url.searchParams.get('limit'), 20, 1, 200))];
    const symbol = String(url.searchParams.get('symbol') || '').trim();
    if (symbol) args.push('--symbol', symbol.slice(0, 64));
    const payload = await runPythonJson(repoRoot, args, env, 20000);
    return sendJson(res, payload.ok === false ? 500 : 200, { ...payload, endpoint, safety: payload.safety || PHASE3_API_SAFETY });
  }
  if (endpoint.startsWith('/api/ai-analysis-v2/history/')) {
    const id = decodeURIComponent(endpoint.split('/').pop() || '').slice(0, 200);
    const payload = await runPythonJson(repoRoot, [script, 'history-item', '--id', id], env, 20000);
    return sendJson(res, payload.ok === false ? 404 : 200, { ...payload, endpoint, safety: payload.safety || PHASE3_API_SAFETY });
  }
  return sendError(res, 404, endpoint, 'Unsupported AI Analysis V2 endpoint');
}

async function handleKline(req, res, ctx, endpoint) {
  const repoRoot = ctx.repoRoot || path.resolve(ctx.rootDir || __dirname, '..');
  const url = new URL(req.url || '/', 'http://127.0.0.1');
  const env = runtimeEnv(ctx);
  const script = path.join('tools', 'kline_phase3_overlays.py');
  let args = [script];
  if (endpoint === '/api/kline/ai-overlays') {
    args.push('ai-overlays', '--limit', String(intInRange(url.searchParams.get('limit'), 50, 1, 500)));
    const symbol = String(url.searchParams.get('symbol') || '').trim();
    if (symbol) args.push('--symbol', symbol.slice(0, 64));
  } else if (endpoint === '/api/kline/vibe-indicators') {
    args.push('vibe-indicators');
    const id = String(url.searchParams.get('strategy_id') || url.searchParams.get('strategyId') || '').trim();
    if (id) args.push('--strategy-id', id.slice(0, 180));
  } else if (endpoint === '/api/kline/realtime-config') {
    args.push('realtime-config');
  } else {
    return sendError(res, 404, endpoint, 'Unsupported K-line endpoint');
  }
  const payload = await runPythonJson(repoRoot, args, env, 20000);
  return sendJson(res, payload.ok === false ? 500 : 200, { ...payload, endpoint, safety: payload.safety || PHASE3_API_SAFETY });
}

async function handle(req, res, ctx = {}) {
  const endpoint = urlPathOf(req.url || '/');
  try {
    if (endpoint === '/api/vibe-coding' || endpoint.startsWith('/api/vibe-coding/')) return await handleVibe(req, res, ctx, endpoint);
    if (endpoint === '/api/ai-analysis-v2' || endpoint.startsWith('/api/ai-analysis-v2/')) return await handleAiV2(req, res, ctx, endpoint);
    if (endpoint.startsWith('/api/kline/')) return await handleKline(req, res, ctx, endpoint);
    sendError(res, 404, endpoint, 'Unsupported Phase 3 endpoint');
    return true;
  } catch (error) {
    sendError(res, 500, endpoint, error);
    return true;
  }
}

module.exports = {
  PHASE3_API_SAFETY,
  handle,
  isPhase3Path,
  sendError,
  urlPathOf,
};
