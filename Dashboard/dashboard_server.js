const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const host = '127.0.0.1';
const port = 8080;
const rootDir = __dirname;
const repoRoot = path.resolve(rootDir, '..');
const defaultRuntimeDir = 'C:\\Program Files\\HFM Metatrader 5\\MQL5\\Files';
const singleMarketRequestName = 'QuantGod_PolymarketSingleMarketRequest.json';
const polymarketHistoryApiScript = path.join(repoRoot, 'tools', 'query_polymarket_history_api.py');
const polymarketHistoryTables = new Set(['all', 'opportunities', 'analyses', 'simulations', 'runs', 'snapshots']);

const contentTypes = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.csv': 'text/csv; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon'
};

const runtimeTextExtensions = new Set(['.json', '.csv', '.txt']);
const utf8Decoder = new TextDecoder('utf-8', { fatal: true });
const shiftJisDecoder = new TextDecoder('shift_jis');

function send(res, statusCode, headers, body) {
  res.writeHead(statusCode, headers);
  res.end(body);
}

function sendJson(res, statusCode, payload) {
  send(res, statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
    Pragma: 'no-cache',
    Expires: '0',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type'
  }, JSON.stringify(payload, null, 2));
}

function readRequestBody(req, maxBytes = 64 * 1024) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let total = 0;
    req.on('data', (chunk) => {
      total += chunk.length;
      if (total > maxBytes) {
        reject(new Error('Request body too large'));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}

function safeJsonPayload(text) {
  try {
    const payload = JSON.parse(String(text || '{}').replace(/^\uFEFF/, ''));
    return payload && typeof payload === 'object' && !Array.isArray(payload) ? payload : {};
  } catch (_) {
    return {};
  }
}

function cleanSingleMarketQuery(value) {
  return String(value || '').replace(/\s+/g, ' ').trim().slice(0, 800);
}

function writeSingleMarketRequest(payload) {
  const query = cleanSingleMarketQuery(
    payload.query || payload.url || payload.marketUrl || payload.marketId || payload.title || payload.question
  );
  if (!query) {
    throw new Error('query is required');
  }

  const request = {
    mode: 'POLYMARKET_SINGLE_MARKET_REQUEST_V1',
    generatedAt: new Date().toISOString(),
    source: 'dashboard_local_input',
    query,
    url: cleanSingleMarketQuery(payload.url || ''),
    marketId: cleanSingleMarketQuery(payload.marketId || ''),
    title: cleanSingleMarketQuery(payload.title || ''),
    note: 'Research-only request. The analyzer may read Gamma API but cannot write wallet orders or mutate MT5.'
  };
  const text = JSON.stringify(request, null, 2);
  const targets = [path.join(rootDir, singleMarketRequestName)];
  if (fs.existsSync(defaultRuntimeDir)) {
    targets.push(path.join(defaultRuntimeDir, singleMarketRequestName));
  }
  const written = [];
  for (const target of targets) {
    fs.writeFileSync(target, text, 'utf8');
    written.push(target);
  }
  return { request, written };
}

function runSingleMarketAnalyzer() {
  return new Promise((resolve) => {
    const script = path.join(repoRoot, 'tools', 'analyze_polymarket_single_market.py');
    if (!fs.existsSync(script)) {
      resolve({ skipped: true, reason: 'analyzer_not_found' });
      return;
    }
    const child = spawn('python', [
      script,
      '--runtime-dir',
      defaultRuntimeDir,
      '--dashboard-dir',
      rootDir
    ], {
      cwd: repoRoot,
      windowsHide: true,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString();
    });
    child.on('error', (error) => {
      resolve({ skipped: false, exitCode: -1, stdout, stderr: error.message });
    });
    child.on('close', (code) => {
      resolve({ skipped: false, exitCode: code, stdout: stdout.trim(), stderr: stderr.trim() });
    });
  });
}

function runJsonPython(script, args = [], timeoutMs = 15000) {
  return new Promise((resolve) => {
    if (!fs.existsSync(script)) {
      resolve({ ok: false, skipped: true, reason: 'script_not_found', script });
      return;
    }
    const child = spawn('python', [script, ...args], {
      cwd: repoRoot,
      windowsHide: true,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
    });
    let settled = false;
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      child.kill();
      resolve({ ok: false, skipped: false, exitCode: -1, stdout, stderr: 'timeout' });
    }, timeoutMs);
    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString();
    });
    child.on('error', (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({ ok: false, skipped: false, exitCode: -1, stdout, stderr: error.message });
    });
    child.on('close', (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (code !== 0) {
        resolve({ ok: false, skipped: false, exitCode: code, stdout, stderr: stderr.trim() });
        return;
      }
      try {
        resolve({ ok: true, skipped: false, exitCode: code, payload: JSON.parse(stdout) });
      } catch (error) {
        resolve({ ok: false, skipped: false, exitCode: code, stdout, stderr: `json_parse_failed: ${error.message}` });
      }
    });
  });
}

async function handleSingleMarketRequest(req, res) {
  try {
    const text = await readRequestBody(req);
    const payload = safeJsonPayload(text);
    const saved = writeSingleMarketRequest(payload);
    const analyzer = await runSingleMarketAnalyzer();
    sendJson(res, 200, {
      ok: analyzer.skipped || analyzer.exitCode === 0,
      written: saved.written,
      request: saved.request,
      analyzer
    });
  } catch (error) {
    sendJson(res, 400, { ok: false, error: error.message || String(error) });
  }
}

async function handlePolymarketHistory(req, res) {
  try {
    const parsed = new URL(req.url || '/', `http://${host}:${port}`);
    const table = parsed.searchParams.get('table') || 'all';
    if (!polymarketHistoryTables.has(table)) {
      sendJson(res, 400, { ok: false, error: `unsupported table: ${table}` });
      return;
    }
    const query = parsed.searchParams.get('q') || '';
    const limit = parsed.searchParams.get('limit') || '50';
    const offset = parsed.searchParams.get('offset') || '0';
    const result = await runJsonPython(polymarketHistoryApiScript, [
      '--repo-root',
      repoRoot,
      '--table',
      table,
      '--q',
      query,
      '--limit',
      limit,
      '--offset',
      offset
    ], 15000);
    if (!result.ok) {
      sendJson(res, 500, { ok: false, error: result.stderr || result.reason || 'history_query_failed', detail: result });
      return;
    }
    sendJson(res, 200, result.payload);
  } catch (error) {
    sendJson(res, 400, { ok: false, error: error.message || String(error) });
  }
}

function maybeTranscodeRuntimeText(target, ext, data) {
  const base = path.basename(target);
  if (!runtimeTextExtensions.has(ext) || !base.startsWith('QuantGod_')) {
    return data;
  }

  try {
    utf8Decoder.decode(data);
    return data;
  } catch (_) {
    // Some MT4/MT5 runtime CSV files are written in the terminal locale; keep
    // the legacy Shift-JIS compatibility path only when bytes are not UTF-8.
  }

  try {
    const utf8Text = shiftJisDecoder.decode(data);
    return Buffer.from(utf8Text, 'utf8');
  } catch (err) {
    console.warn(`QuantGod dashboard server transcode fallback for ${base}: ${err.message}`);
    return data;
  }
}

function safeResolve(urlPath) {
  const pathname = decodeURIComponent(urlPath.split('?')[0] || '/');
  const normalized = pathname === '/' ? '/QuantGod_Dashboard.html' : pathname;
  const target = path.resolve(rootDir, '.' + normalized);
  if (!target.startsWith(rootDir)) {
    return null;
  }
  return target;
}

function resolveRuntimeFallback(target) {
  const base = path.basename(target || '');
  if (!base.startsWith('QuantGod_')) return null;
  const runtimeTarget = path.join(defaultRuntimeDir, base);
  if (!runtimeTarget.startsWith(defaultRuntimeDir)) return null;
  return fs.existsSync(runtimeTarget) ? runtimeTarget : null;
}

function sendStaticFile(target, res) {
  fs.stat(target, (statErr, stats) => {
    if (statErr || !stats.isFile()) {
      send(res, 404, { 'Content-Type': 'text/plain; charset=utf-8' }, 'Not Found');
      return;
    }

    const ext = path.extname(target).toLowerCase();
    const contentType = contentTypes[ext] || 'application/octet-stream';

    fs.readFile(target, (readErr, data) => {
      if (readErr) {
        send(res, 500, { 'Content-Type': 'text/plain; charset=utf-8' }, 'Read Failed');
        return;
      }

      const body = maybeTranscodeRuntimeText(target, ext, data);

      send(res, 200, {
        'Content-Type': contentType,
        'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
        Pragma: 'no-cache',
        Expires: '0',
        'Access-Control-Allow-Origin': '*'
      }, body);
    });
  });
}

const server = http.createServer((req, res) => {
  const requestUrl = req.url || '/';
  if (req.method === 'OPTIONS') {
    sendJson(res, 204, {});
    return;
  }
  if (req.method === 'GET' && requestUrl.split('?')[0] === '/api/latest') {
    const latestDashboard = path.join(defaultRuntimeDir, 'QuantGod_Dashboard.json');
    if (fs.existsSync(latestDashboard)) {
      sendStaticFile(latestDashboard, res);
      return;
    }
    send(res, 404, { 'Content-Type': 'text/plain; charset=utf-8' }, 'Not Found');
    return;
  }
  if (req.method === 'GET' && requestUrl.split('?')[0] === '/api/polymarket/history') {
    handlePolymarketHistory(req, res);
    return;
  }
  if (req.method === 'POST' && requestUrl.split('?')[0] === '/api/polymarket/single-market-request') {
    handleSingleMarketRequest(req, res);
    return;
  }
  if (req.method === 'POST' && requestUrl.split('?')[0] === '/api/polymarket/analyze') {
    handleSingleMarketRequest(req, res);
    return;
  }
  const target = safeResolve(req.url || '/');
  if (!target) {
    send(res, 403, { 'Content-Type': 'text/plain; charset=utf-8' }, 'Forbidden');
    return;
  }

  const fallback = fs.existsSync(target) ? target : resolveRuntimeFallback(target);
  sendStaticFile(fallback || target, res);
});

server.listen(port, host, () => {
  console.log(`QuantGod dashboard server running at http://${host}:${port}/QuantGod_Dashboard.html`);
});

server.on('error', (err) => {
  console.error('QuantGod dashboard server failed:', err.message);
  process.exit(1);
});
