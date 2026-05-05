const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

function sendJson(res, statusCode, payload) {
  res.writeHead(statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
    Pragma: 'no-cache',
    Expires: '0',
  });
  res.end(JSON.stringify(payload, null, 2));
}

function sendError(res, statusCode, requestUrl, error) {
  sendJson(res, statusCode, {
    ok: false,
    endpoint: requestUrl,
    error: error && error.message ? error.message : String(error),
    safety: {
      readOnlyDataPlane: true,
      advisoryOnly: true,
      dryRunOnly: true,
      orderSendAllowed: false,
      closeAllowed: false,
      cancelAllowed: false,
      livePresetMutationAllowed: false,
      writesMt5OrderRequest: false,
    },
  });
}

function isUSDJPYStrategyLabPath(requestUrl) {
  const pathname = String(requestUrl || '').split('?')[0];
  return pathname === '/api/usdjpy-strategy-lab' || pathname.startsWith('/api/usdjpy-strategy-lab/');
}

function runPythonJson(repoRoot, args, timeoutMs = 45000) {
  return new Promise((resolve) => {
    const pythonBin = process.env.QG_PYTHON_BIN || (process.platform === 'win32' ? 'python' : 'python3');
    const script = path.join(repoRoot, 'tools', 'run_usdjpy_strategy_lab.py');
    if (!fs.existsSync(script)) {
      resolve({ ok: false, skipped: true, reason: 'script_not_found', script });
      return;
    }
    const child = spawn(pythonBin, [script, ...args], {
      cwd: repoRoot,
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
      resolve({ ok: false, exitCode: -1, stdout, stderr: 'timeout' });
    }, timeoutMs);
    child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
    child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
    child.on('error', (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({ ok: false, exitCode: -1, stdout, stderr: error.message });
    });
    child.on('close', (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (code !== 0) {
        resolve({ ok: false, exitCode: code, stdout, stderr: stderr.trim() });
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch (error) {
        resolve({ ok: false, exitCode: code, stdout, stderr: `json_parse_failed: ${error.message}` });
      }
    });
  });
}

async function handle(req, res, ctx) {
  const requestUrl = req.url || '/';
  const url = new URL(requestUrl, 'http://127.0.0.1');
  const pathname = url.pathname;
  const runtimeDir = url.searchParams.get('runtimeDir') || ctx.defaultRuntimeDir;
  const baseArgs = ['--runtime-dir', runtimeDir, '--symbol', 'USDJPYc'];

  if (req.method === 'GET' && (pathname === '/api/usdjpy-strategy-lab' || pathname === '/api/usdjpy-strategy-lab/status')) {
    const payload = await runPythonJson(ctx.repoRoot, [...baseArgs, 'status']);
    sendJson(res, payload && payload.ok === false ? 500 : 200, payload);
    return;
  }
  if (req.method === 'GET' && pathname === '/api/usdjpy-strategy-lab/scoreboard') {
    const payload = await runPythonJson(ctx.repoRoot, [...baseArgs, 'scoreboard']);
    sendJson(res, payload && payload.ok === false ? 500 : 200, payload);
    return;
  }
  if (req.method === 'GET' && pathname === '/api/usdjpy-strategy-lab/dry-run') {
    const payload = await runPythonJson(ctx.repoRoot, [...baseArgs, 'dry-run', '--write']);
    sendJson(res, payload && payload.ok === false ? 500 : 200, payload);
    return;
  }
  if (req.method === 'GET' && pathname === '/api/usdjpy-strategy-lab/telegram-text') {
    const args = [...baseArgs, 'telegram-text'];
    if (url.searchParams.get('refresh') === '1') args.push('--refresh');
    if (url.searchParams.get('send') === '1') args.push('--send');
    const payload = await runPythonJson(ctx.repoRoot, args);
    sendJson(res, payload && payload.ok === false ? 500 : 200, payload);
    return;
  }
  if (req.method === 'POST' && pathname === '/api/usdjpy-strategy-lab/run') {
    const payload = await runPythonJson(ctx.repoRoot, [...baseArgs, 'build', '--write']);
    sendJson(res, payload && payload.ok === false ? 500 : 200, payload);
    return;
  }
  sendJson(res, 404, { ok: false, error: 'USDJPY_STRATEGY_LAB_NOT_FOUND', endpoint: pathname });
}

module.exports = {
  isUSDJPYStrategyLabPath,
  handle,
  sendError,
};
