const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const host = process.env.QG_DASHBOARD_HOST || '127.0.0.1';
const port = Number.parseInt(process.env.QG_DASHBOARD_PORT || '8080', 10) || 8080;
const rootDir = __dirname;
const repoRoot = path.resolve(rootDir, '..');
const defaultRuntimeDir = 'C:\\Program Files\\HFM Metatrader 5\\MQL5\\Files';
const singleMarketRequestName = 'QuantGod_PolymarketSingleMarketRequest.json';
const polymarketRadarName = 'QuantGod_PolymarketMarketRadar.json';
const polymarketAiScoreName = 'QuantGod_PolymarketAiScoreV1.json';
const polymarketSingleMarketAnalysisName = 'QuantGod_PolymarketSingleMarketAnalysis.json';
const polymarketHistoryApiScript = path.join(repoRoot, 'tools', 'query_polymarket_history_api.py');
const mt5ReadonlyBridgeScript = path.join(repoRoot, 'tools', 'mt5_readonly_bridge.py');
const mt5SymbolRegistryScript = path.join(repoRoot, 'tools', 'mt5_symbol_registry.py');
const polymarketHistoryTables = new Set(['all', 'opportunities', 'analyses', 'simulations', 'runs', 'snapshots']);
const mt5ReadonlyEndpoints = new Set(['status', 'account', 'positions', 'orders', 'symbols', 'quote', 'snapshot']);
const mt5SymbolRegistryEndpoints = new Set(['registry', 'resolve']);
const polymarketReadOnlyJsonFiles = new Set([
  polymarketRadarName,
  polymarketAiScoreName,
  polymarketSingleMarketAnalysisName
]);

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

function readQuantGodJsonFile(fileName) {
  const base = path.basename(fileName || '');
  if (!polymarketReadOnlyJsonFiles.has(base)) {
    throw new Error(`unsupported read-only json file: ${base}`);
  }
  const candidates = [path.join(rootDir, base)];
  if (fs.existsSync(defaultRuntimeDir)) {
    candidates.push(path.join(defaultRuntimeDir, base));
  }
  for (const candidate of candidates) {
    if (!fs.existsSync(candidate)) continue;
    const text = fs.readFileSync(candidate, 'utf8').replace(/^\uFEFF/, '');
    return { payload: JSON.parse(text), filePath: candidate };
  }
  throw new Error(`file not found: ${base}`);
}

function withServiceMeta(payload, endpoint, filePath) {
  const source = {
    service: 'quantgod_dashboard_local_api',
    endpoint,
    filePath,
    readOnly: true,
    walletWriteAllowed: false,
    orderSendAllowed: false,
    mutatesMt5: false
  };
  if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
    return { ...payload, _api: source };
  }
  return { payload, _api: source };
}

async function queryPolymarketHistory(table, query = '', limit = '50', offset = '0') {
  return runJsonPython(polymarketHistoryApiScript, [
    '--repo-root',
    repoRoot,
    '--table',
    table,
    '--q',
    query,
    '--limit',
    String(limit),
    '--offset',
    String(offset)
  ], 15000);
}

function cleanMt5ReadonlyParam(value, maxLength = 160) {
  return String(value || '').replace(/\s+/g, ' ').trim().slice(0, maxLength);
}

function clampMt5ReadonlyLimit(value, fallback = 120, max = 2000) {
  const parsed = Number.parseInt(String(value || ''), 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(0, Math.min(parsed, max));
}

function buildMt5ReadonlyArgs(endpoint, parsedUrl) {
  const params = parsedUrl.searchParams;
  const args = ['--endpoint', endpoint];
  const symbol = cleanMt5ReadonlyParam(params.get('symbol') || params.get('focusSymbol') || '');
  const group = cleanMt5ReadonlyParam(params.get('group') || '*', 120) || '*';
  const query = cleanMt5ReadonlyParam(params.get('q') || params.get('query') || '', 120);
  const limit = clampMt5ReadonlyLimit(params.get('limit'), 120);
  const symbolsLimit = clampMt5ReadonlyLimit(params.get('symbolsLimit') || params.get('symbols_limit'), 120);

  if (symbol) args.push('--symbol', symbol);
  args.push('--group', group);
  if (query) args.push('--query', query);
  args.push('--limit', String(limit));
  args.push('--symbols-limit', String(symbolsLimit));
  return args;
}

async function handleMt5Readonly(req, res, endpoint) {
  if (!mt5ReadonlyEndpoints.has(endpoint)) {
    sendJson(res, 404, {
      ok: false,
      status: 'NOT_FOUND',
      endpoint,
      error: 'unsupported_mt5_readonly_endpoint',
      supportedEndpoints: Array.from(mt5ReadonlyEndpoints).sort(),
      safety: {
        readOnly: true,
        orderSendAllowed: false,
        closeAllowed: false,
        cancelAllowed: false,
        credentialStorageAllowed: false,
        livePresetMutationAllowed: false,
        mutatesMt5: false
      }
    });
    return;
  }
  const normalizedEndpoint = endpoint;
  try {
    const parsed = new URL(req.url || '/', `http://${host}:${port}`);
    const result = await runJsonPython(mt5ReadonlyBridgeScript, buildMt5ReadonlyArgs(normalizedEndpoint, parsed), 12000);
    if (!result.ok) {
      sendJson(res, 200, {
        ok: false,
        status: 'UNAVAILABLE',
        endpoint: normalizedEndpoint,
        error: result.stderr || result.reason || 'mt5_readonly_bridge_failed',
        detail: result,
        safety: {
          readOnly: true,
          orderSendAllowed: false,
          closeAllowed: false,
          cancelAllowed: false,
          credentialStorageAllowed: false,
          livePresetMutationAllowed: false,
          mutatesMt5: false
        }
      });
      return;
    }
    const payload = result.payload && typeof result.payload === 'object' ? result.payload : {};
    sendJson(res, 200, {
      ...payload,
      _api: {
        service: 'quantgod_dashboard_mt5_readonly_bridge',
        endpoint: `/api/mt5-readonly/${normalizedEndpoint}`,
        script: mt5ReadonlyBridgeScript,
        readOnly: true,
        orderSendAllowed: false,
        closeAllowed: false,
        cancelAllowed: false,
        mutatesMt5: false
      }
    });
  } catch (error) {
    sendJson(res, 200, {
      ok: false,
      status: 'UNAVAILABLE',
      endpoint: normalizedEndpoint,
      error: error.message || String(error),
      safety: {
        readOnly: true,
        orderSendAllowed: false,
        closeAllowed: false,
        cancelAllowed: false,
        credentialStorageAllowed: false,
        livePresetMutationAllowed: false,
        mutatesMt5: false
      }
    });
  }
}

function buildMt5SymbolRegistryArgs(endpoint, parsedUrl) {
  const params = parsedUrl.searchParams;
  const args = ['--endpoint', endpoint];
  const symbol = cleanMt5ReadonlyParam(params.get('symbol') || params.get('canonical') || params.get('brokerSymbol') || '', 160);
  const group = cleanMt5ReadonlyParam(params.get('group') || '*', 120) || '*';
  const query = cleanMt5ReadonlyParam(params.get('q') || params.get('query') || '', 120);
  const limit = clampMt5ReadonlyLimit(params.get('limit'), 2000, 5000);

  if (symbol) args.push('--symbol', symbol);
  args.push('--group', group);
  if (query) args.push('--query', query);
  args.push('--limit', String(limit));
  return args;
}

async function handleMt5SymbolRegistry(req, res, endpoint) {
  if (!mt5SymbolRegistryEndpoints.has(endpoint)) {
    sendJson(res, 404, {
      ok: false,
      status: 'NOT_FOUND',
      endpoint,
      error: 'unsupported_mt5_symbol_registry_endpoint',
      supportedEndpoints: Array.from(mt5SymbolRegistryEndpoints).sort(),
      safety: {
        readOnly: true,
        orderSendAllowed: false,
        closeAllowed: false,
        cancelAllowed: false,
        symbolSelectAllowed: false,
        credentialStorageAllowed: false,
        livePresetMutationAllowed: false,
        mutatesMt5: false
      }
    });
    return;
  }
  try {
    const parsed = new URL(req.url || '/', `http://${host}:${port}`);
    const result = await runJsonPython(mt5SymbolRegistryScript, buildMt5SymbolRegistryArgs(endpoint, parsed), 15000);
    if (!result.ok) {
      sendJson(res, 200, {
        ok: false,
        status: 'UNAVAILABLE',
        endpoint,
        error: result.stderr || result.reason || 'mt5_symbol_registry_failed',
        detail: result,
        safety: {
          readOnly: true,
          orderSendAllowed: false,
          closeAllowed: false,
          cancelAllowed: false,
          symbolSelectAllowed: false,
          credentialStorageAllowed: false,
          livePresetMutationAllowed: false,
          mutatesMt5: false
        }
      });
      return;
    }
    const payload = result.payload && typeof result.payload === 'object' ? result.payload : {};
    sendJson(res, 200, {
      ...payload,
      _api: {
        service: 'quantgod_dashboard_mt5_symbol_registry',
        endpoint: endpoint === 'resolve' ? '/api/mt5-symbol-registry/resolve' : '/api/mt5-symbol-registry',
        script: mt5SymbolRegistryScript,
        readOnly: true,
        orderSendAllowed: false,
        closeAllowed: false,
        cancelAllowed: false,
        symbolSelectAllowed: false,
        mutatesMt5: false
      }
    });
  } catch (error) {
    sendJson(res, 200, {
      ok: false,
      status: 'UNAVAILABLE',
      endpoint,
      error: error.message || String(error),
      safety: {
        readOnly: true,
        orderSendAllowed: false,
        closeAllowed: false,
        cancelAllowed: false,
        symbolSelectAllowed: false,
        credentialStorageAllowed: false,
        livePresetMutationAllowed: false,
        mutatesMt5: false
      }
    });
  }
}

function firstDefined(...values) {
  for (const value of values) {
    if (value !== undefined && value !== null && value !== '') return value;
  }
  return '';
}

function toBoolean(value) {
  if (typeof value === 'boolean') return value;
  const normalized = String(value ?? '').trim().toLowerCase();
  return normalized === 'true' || normalized === '1' || normalized === 'yes' || normalized === 'y';
}

function normalizeAnalyzeHistoryRows(rows = []) {
  return rows.map((row, index) => ({
    rowId: index + 1,
    generatedAt: firstDefined(row.generatedAt, row.lastSeenAt, row.seenAt),
    status: firstDefined(row.status, 'OK'),
    decision: firstDefined(row.decision, 'RESEARCH_ONLY_SINGLE_MARKET_NO_BETTING'),
    query: firstDefined(row.query, row.question, row.marketId),
    querySource: firstDefined(row.querySource, row.source, 'history_api'),
    marketId: firstDefined(row.marketId),
    question: firstDefined(row.question, row.eventTitle),
    category: firstDefined(row.category),
    marketProbability: firstDefined(row.marketProbability, row.marketProbabilityPct),
    aiProbability: firstDefined(row.aiProbability, row.aiProbabilityPct),
    divergence: firstDefined(row.divergence, row.divergencePct),
    confidence: firstDefined(row.confidence, row.confidencePct),
    recommendation: firstDefined(row.recommendation, row.recommendedAction),
    risk: firstDefined(row.risk),
    shadowTrack: firstDefined(row.suggestedShadowTrack, row.shadowTrack),
    url: firstDefined(row.polymarketUrl, row.url),
    walletWrite: toBoolean(firstDefined(row.walletWrite, row.walletWriteAllowed)),
    orderSend: toBoolean(firstDefined(row.orderSend, row.orderSendAllowed)),
    historyType: firstDefined(row.historyType, 'analyses'),
    source: 'sqlite_history_api'
  }));
}

function clampSearchLimit(value, fallback = 36) {
  const parsed = Number.parseInt(String(value || ''), 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(8, Math.min(120, parsed));
}

function searchHaystack(value) {
  if (value === null || value === undefined) return '';
  if (Array.isArray(value)) return value.map(searchHaystack).join(' ');
  if (typeof value === 'object') {
    return Object.values(value).map(searchHaystack).join(' ');
  }
  return String(value);
}

function matchesSearchQuery(value, query) {
  const normalized = String(query || '').trim().toLowerCase();
  if (!normalized) return true;
  return searchHaystack(value).toLowerCase().includes(normalized);
}

function numericScore(...values) {
  for (const value of values) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return 0;
}

function compactRadarResult(item = {}, generatedAt = '') {
  return {
    sourceType: 'radar',
    sourceLabel: '机会雷达',
    title: firstDefined(item.question, item.slug, item.marketId, '--'),
    subtitle: firstDefined(item.eventTitle, item.category, item.slug),
    marketId: firstDefined(item.marketId),
    url: firstDefined(item.polymarketUrl, item.url),
    generatedAt: firstDefined(item.generatedAt, item.seenAt, generatedAt),
    risk: firstDefined(item.risk),
    recommendation: firstDefined(item.recommendedAction, 'SHADOW_REVIEW'),
    track: firstDefined(item.suggestedShadowTrack),
    probability: firstDefined(item.probability),
    divergence: firstDefined(item.divergence),
    score: numericScore(item.aiRuleScore, item.ruleScore),
    detail: {
      rank: item.rank,
      volume: item.volume,
      liquidity: item.liquidity,
      riskFlags: item.riskFlags || []
    }
  };
}

function compactAiScoreResult(item = {}, generatedAt = '') {
  return {
    sourceType: 'ai-score',
    sourceLabel: 'AI 评分',
    title: firstDefined(item.question, item.eventTitle, item.marketId, '--'),
    subtitle: firstDefined(item.action, item.nextStep, item.executionMode),
    marketId: firstDefined(item.marketId),
    url: firstDefined(item.polymarketUrl, item.url),
    generatedAt: firstDefined(item.generatedAt, item.seenAt, generatedAt),
    risk: firstDefined(item.color, item.risk),
    recommendation: firstDefined(item.action, item.recommendedAction),
    track: firstDefined(item.track, item.suggestedShadowTrack),
    probability: firstDefined(item.probability),
    divergence: firstDefined(item.divergence),
    score: numericScore(item.score, item.aiRuleScore),
    detail: {
      reasons: item.reasons || [],
      components: item.components || {},
      nextStep: item.nextStep || ''
    }
  };
}

function compactAnalysisResult(row = {}) {
  return {
    sourceType: 'analysis',
    sourceLabel: '单市场分析',
    title: firstDefined(row.question, row.query, row.marketId, '--'),
    subtitle: firstDefined(row.recommendation, row.status, row.decision),
    marketId: firstDefined(row.marketId),
    url: firstDefined(row.url, row.polymarketUrl),
    generatedAt: firstDefined(row.generatedAt, row.seenAt),
    risk: firstDefined(row.risk),
    recommendation: firstDefined(row.recommendation, row.decision, row.status),
    track: firstDefined(row.shadowTrack, row.suggestedShadowTrack),
    probability: firstDefined(row.marketProbability, row.marketProbabilityPct),
    divergence: firstDefined(row.divergence, row.divergencePct),
    score: numericScore(row.confidence, row.confidencePct),
    detail: {
      aiProbability: firstDefined(row.aiProbability, row.aiProbabilityPct),
      confidence: firstDefined(row.confidence, row.confidencePct),
      historyType: firstDefined(row.historyType, 'analyses')
    }
  };
}

function compactHistoryResult(row = {}) {
  return {
    sourceType: firstDefined(row.historyType, 'history'),
    sourceLabel: '历史库',
    title: firstDefined(row.question, row.query, row.marketId, row.runId, row.mode, '--'),
    subtitle: firstDefined(row.recommendation, row.state, row.decision, row.schemaVersion),
    marketId: firstDefined(row.marketId),
    url: firstDefined(row.polymarketUrl, row.url),
    generatedAt: firstDefined(row.generatedAt, row.seenAt, row.lastSeenAt, row.firstSeenAt),
    risk: firstDefined(row.risk),
    recommendation: firstDefined(row.recommendation, row.recommendedAction, row.state, row.decision),
    track: firstDefined(row.suggestedShadowTrack, row.track, row.source),
    probability: firstDefined(row.probability, row.marketProbability),
    divergence: firstDefined(row.divergence),
    score: numericScore(row.aiRuleScore, row.ruleScore, row.confidence, row.executedPf),
    detail: {
      historyType: firstDefined(row.historyType),
      source: firstDefined(row.source),
      rawType: 'history'
    }
  };
}

function sortSearchResults(results = []) {
  return results
    .slice()
    .sort((a, b) => {
      const scoreDelta = numericScore(b.score) - numericScore(a.score);
      if (scoreDelta) return scoreDelta;
      const rightTime = Date.parse(b.generatedAt || '') || 0;
      const leftTime = Date.parse(a.generatedAt || '') || 0;
      return rightTime - leftTime;
    });
}

function normalizeMarketGroupValue(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .slice(0, 260);
}

function normalizeMarketGroupKey(item = {}) {
  const marketId = normalizeMarketGroupValue(item.marketId);
  if (marketId) return `market:${marketId}`;

  const url = normalizeMarketGroupValue(item.url);
  if (url) {
    try {
      const parsed = new URL(url);
      const slug = parsed.pathname.replace(/\/+$/g, '').split('/').filter(Boolean).pop();
      return `url:${slug || `${parsed.origin}${parsed.pathname}`}`;
    } catch (_error) {
      return `url:${url}`;
    }
  }

  const title = normalizeMarketGroupValue(item.title);
  if (title) return `title:${title}`;

  const fallback = normalizeMarketGroupValue(firstDefined(item.subtitle, item.sourceType, 'unknown'));
  return `fallback:${fallback}`;
}

function marketRiskRank(risk) {
  const normalized = String(risk || '').trim().toLowerCase();
  if (['red', 'danger', 'high', 'blocked'].includes(normalized)) return 3;
  if (['yellow', 'watch', 'medium', 'warn', 'warning'].includes(normalized)) return 2;
  if (['green', 'good', 'low', 'ok'].includes(normalized)) return 1;
  return 0;
}

function newerTimestamp(left, right) {
  const leftTime = Date.parse(left || '') || 0;
  const rightTime = Date.parse(right || '') || 0;
  return rightTime > leftTime ? right : left;
}

function toSearchEvidenceItem(item = {}) {
  return {
    sourceType: firstDefined(item.sourceType),
    sourceLabel: firstDefined(item.sourceLabel, item.sourceType),
    title: firstDefined(item.title),
    subtitle: firstDefined(item.subtitle),
    marketId: firstDefined(item.marketId),
    url: firstDefined(item.url),
    generatedAt: firstDefined(item.generatedAt),
    risk: firstDefined(item.risk),
    recommendation: firstDefined(item.recommendation),
    track: firstDefined(item.track),
    probability: firstDefined(item.probability),
    divergence: firstDefined(item.divergence),
    score: numericScore(item.score),
    detail: item.detail || {}
  };
}

function mergeMarketSearchGroup(group, item = {}) {
  const itemScore = numericScore(item.score);
  const currentScore = numericScore(group.score);
  const itemTime = item.generatedAt || '';
  const nextTime = newerTimestamp(group.generatedAt, itemTime);
  const itemIsNewer = nextTime === itemTime && itemTime !== group.generatedAt;
  const itemIsHigherScore = itemScore > currentScore;

  group.title = firstDefined(group.title, item.title, item.marketId, item.url, '--');
  group.subtitle = firstDefined(group.subtitle, item.subtitle, item.url, '多源聚合结果');
  group.marketId = firstDefined(group.marketId, item.marketId);
  group.url = firstDefined(group.url, item.url);
  group.generatedAt = nextTime;
  group.score = Math.max(currentScore, itemScore);

  if (marketRiskRank(item.risk) > marketRiskRank(group.risk)) {
    group.risk = item.risk;
  } else {
    group.risk = firstDefined(group.risk, item.risk);
  }

  if (itemIsHigherScore || itemIsNewer || !group.recommendation) {
    group.recommendation = firstDefined(item.recommendation, group.recommendation);
    group.track = firstDefined(item.track, group.track);
  }
  group.probability = firstDefined(group.probability, item.probability);
  group.divergence = firstDefined(group.divergence, item.divergence);

  if (item.sourceType && !group.sourceTypes.includes(item.sourceType)) group.sourceTypes.push(item.sourceType);
  const sourceLabel = firstDefined(item.sourceLabel, item.sourceType);
  if (sourceLabel && !group.sourceLabels.includes(sourceLabel)) group.sourceLabels.push(sourceLabel);

  group.evidence.push(toSearchEvidenceItem(item));
  group.evidence = sortSearchResults(group.evidence);
  group.evidenceCount += 1;
  group.summaryLine = `${group.evidenceCount} 条证据 · ${group.sourceLabels.join(' / ') || '未分类来源'}`;
  return group;
}

function groupSearchResultsByMarket(results = [], limit = 36) {
  const grouped = new Map();
  for (const item of sortSearchResults(results)) {
    const key = normalizeMarketGroupKey(item);
    if (!grouped.has(key)) {
      grouped.set(key, {
        sourceType: 'market-group',
        sourceLabel: '综合证据',
        groupKey: key,
        title: '',
        subtitle: '',
        marketId: '',
        url: '',
        generatedAt: '',
        risk: '',
        recommendation: '',
        track: '',
        probability: '',
        divergence: '',
        score: 0,
        sourceTypes: [],
        sourceLabels: [],
        evidenceCount: 0,
        evidence: [],
        detail: { grouped: true }
      });
    }
    mergeMarketSearchGroup(grouped.get(key), item);
  }

  return Array.from(grouped.values())
    .sort((a, b) => {
      const scoreDelta = numericScore(b.score) - numericScore(a.score);
      if (scoreDelta) return scoreDelta;
      const evidenceDelta = numericScore(b.evidenceCount) - numericScore(a.evidenceCount);
      if (evidenceDelta) return evidenceDelta;
      const rightTime = Date.parse(b.generatedAt || '') || 0;
      const leftTime = Date.parse(a.generatedAt || '') || 0;
      return rightTime - leftTime;
    })
    .slice(0, limit);
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
    const result = await queryPolymarketHistory(table, query, limit, offset);
    if (!result.ok) {
      sendJson(res, 500, { ok: false, error: result.stderr || result.reason || 'history_query_failed', detail: result });
      return;
    }
    sendJson(res, 200, result.payload);
  } catch (error) {
    sendJson(res, 400, { ok: false, error: error.message || String(error) });
  }
}

async function handlePolymarketReadOnlyJson(req, res, fileName, endpoint) {
  try {
    const { payload, filePath } = readQuantGodJsonFile(fileName);
    sendJson(res, 200, withServiceMeta(payload, endpoint, filePath));
  } catch (error) {
    sendJson(res, 404, {
      ok: false,
      error: error.message || String(error),
      endpoint,
      safety: {
        walletWriteAllowed: false,
        orderSendAllowed: false,
        mutatesMt5: false,
        readOnly: true
      }
    });
  }
}

async function handlePolymarketAnalyzeHistory(req, res) {
  try {
    const parsed = new URL(req.url || '/', `http://${host}:${port}`);
    const query = parsed.searchParams.get('q') || '';
    const limit = parsed.searchParams.get('limit') || '80';
    let latest = null;
    let latestPath = '';
    let latestError = '';
    try {
      const read = readQuantGodJsonFile(polymarketSingleMarketAnalysisName);
      latest = withServiceMeta(read.payload, '/api/polymarket/analyze/history', read.filePath);
      latestPath = read.filePath;
    } catch (error) {
      latestError = error.message || String(error);
    }

    const result = await queryPolymarketHistory('analyses', query, limit, '0');
    if (!result.ok) {
      sendJson(res, 500, {
        ok: false,
        error: result.stderr || result.reason || 'analyze_history_query_failed',
        latest,
        latestError,
        detail: result
      });
      return;
    }

    const rows = normalizeAnalyzeHistoryRows(result.payload?.search?.rows || result.payload?.recent?.analyses || []);
    sendJson(res, 200, {
      mode: 'POLYMARKET_ANALYZE_HISTORY_API_V1',
      status: result.payload?.status || 'OK',
      generatedAt: new Date().toISOString(),
      source: 'quantgod_dashboard_local_api',
      decision: 'READ_ONLY_ANALYZE_HISTORY_NO_WALLET_WRITE',
      latest,
      latestPath,
      latestError,
      rows,
      summary: {
        rows: rows.length,
        matched: result.payload?.search?.count || rows.length,
        totalRows: result.payload?.summary?.marketAnalyses || rows.length
      },
      history: result.payload,
      safety: {
        readsPrivateKey: false,
        walletWriteAllowed: false,
        orderSendAllowed: false,
        startsExecutor: false,
        mutatesMt5: false,
        readOnly: true
      }
    });
  } catch (error) {
    sendJson(res, 400, { ok: false, error: error.message || String(error) });
  }
}

async function handlePolymarketSearch(req, res) {
  try {
    const parsed = new URL(req.url || '/', `http://${host}:${port}`);
    const query = String(parsed.searchParams.get('q') || '').trim().slice(0, 240);
    const limit = clampSearchLimit(parsed.searchParams.get('limit'), 36);
    const errors = [];

    let radar = null;
    let radarPath = '';
    try {
      const read = readQuantGodJsonFile(polymarketRadarName);
      radar = withServiceMeta(read.payload, '/api/polymarket/radar', read.filePath);
      radarPath = read.filePath;
    } catch (error) {
      errors.push({ source: 'radar', error: error.message || String(error) });
    }

    let aiScore = null;
    let aiScorePath = '';
    try {
      const read = readQuantGodJsonFile(polymarketAiScoreName);
      aiScore = withServiceMeta(read.payload, '/api/polymarket/ai-score', read.filePath);
      aiScorePath = read.filePath;
    } catch (error) {
      errors.push({ source: 'ai-score', error: error.message || String(error) });
    }

    let latestAnalysis = null;
    let latestAnalysisPath = '';
    try {
      const read = readQuantGodJsonFile(polymarketSingleMarketAnalysisName);
      latestAnalysis = withServiceMeta(read.payload, '/api/polymarket/analyze/history', read.filePath);
      latestAnalysisPath = read.filePath;
    } catch (error) {
      errors.push({ source: 'single-analysis-latest', error: error.message || String(error) });
    }

    const historyResult = await queryPolymarketHistory('all', query, String(limit), '0');
    if (!historyResult.ok) {
      errors.push({ source: 'history', error: historyResult.stderr || historyResult.reason || 'history_query_failed' });
    }

    const analysisResult = await queryPolymarketHistory('analyses', query, String(limit), '0');
    if (!analysisResult.ok) {
      errors.push({ source: 'analysis-history', error: analysisResult.stderr || analysisResult.reason || 'analysis_query_failed' });
    }

    const radarItems = Array.isArray(radar?.radar)
      ? radar.radar.filter((item) => matchesSearchQuery(item, query)).slice(0, limit)
      : [];
    const aiScoreItems = Array.isArray(aiScore?.scores)
      ? aiScore.scores.filter((item) => matchesSearchQuery(item, query)).slice(0, limit)
      : [];

    const historyPayload = historyResult.payload || {};
    const historyRows = query
      ? (historyPayload.search?.rows || [])
      : [
          ...(historyPayload.recent?.opportunities || []),
          ...(historyPayload.recent?.analyses || []),
          ...(historyPayload.recent?.simulations || []),
        ].slice(0, limit);
    const analysisRows = normalizeAnalyzeHistoryRows(
      analysisResult.payload?.search?.rows || analysisResult.payload?.recent?.analyses || []
    );

    const latestAnalysisRows = [];
    if (latestAnalysis && matchesSearchQuery(latestAnalysis, query)) {
      const latestMarket = latestAnalysis.market || {};
      const latestAnalysisBody = latestAnalysis.analysis || {};
      latestAnalysisRows.push({
        rowId: 0,
        generatedAt: firstDefined(latestAnalysis.generatedAt, latestAnalysisBody.generatedAt),
        status: firstDefined(latestAnalysis.status, 'OK'),
        decision: firstDefined(latestAnalysis.decision, 'RESEARCH_ONLY_SINGLE_MARKET_NO_BETTING'),
        query: firstDefined(latestAnalysis.request?.query, latestMarket.question, latestMarket.marketId),
        querySource: firstDefined(latestAnalysis.request?.source, 'latest_snapshot'),
        marketId: firstDefined(latestMarket.marketId),
        question: firstDefined(latestMarket.question, latestMarket.slug),
        category: firstDefined(latestMarket.category),
        marketProbability: firstDefined(latestAnalysisBody.marketProbabilityPct, latestMarket.probability),
        aiProbability: firstDefined(latestAnalysisBody.aiProbabilityPct),
        divergence: firstDefined(latestAnalysisBody.divergencePct),
        confidence: firstDefined(latestAnalysisBody.confidencePct),
        recommendation: firstDefined(latestAnalysisBody.recommendation, latestAnalysis.summary?.recommendation),
        risk: firstDefined(latestAnalysisBody.riskLevel, latestAnalysis.summary?.risk),
        shadowTrack: firstDefined(latestAnalysisBody.suggestedShadowTrack),
        url: firstDefined(latestMarket.polymarketUrl),
        walletWrite: toBoolean(latestAnalysis.safety?.walletWriteAllowed),
        orderSend: toBoolean(latestAnalysis.safety?.orderSendAllowed),
        historyType: 'latest_analysis',
        source: 'latest_json_api'
      });
    }

    const sections = {
      radar: radarItems.map((item) => compactRadarResult(item, radar?.generatedAt)),
      aiScore: aiScoreItems.map((item) => compactAiScoreResult(item, aiScore?.generatedAt)),
      analyses: [...latestAnalysisRows, ...analysisRows].slice(0, limit).map(compactAnalysisResult),
      history: historyRows.slice(0, limit).map(compactHistoryResult)
    };
    const rawSearchResults = sortSearchResults([
      ...sections.radar,
      ...sections.aiScore,
      ...sections.analyses,
      ...sections.history
    ]);
    const groupedResults = groupSearchResultsByMarket(rawSearchResults, limit);

    sendJson(res, 200, {
      mode: 'POLYMARKET_SEARCH_API_V2_GROUPED_MARKET_EVIDENCE',
      status: errors.length ? 'PARTIAL' : 'OK',
      generatedAt: new Date().toISOString(),
      source: 'quantgod_dashboard_local_api',
      decision: 'READ_ONLY_UNIFIED_SEARCH_NO_WALLET_WRITE',
      query,
      limit,
      summary: {
        totalMatches: groupedResults.length,
        marketGroups: groupedResults.length,
        rawMatches: rawSearchResults.length,
        radarMatches: sections.radar.length,
        aiScoreMatches: sections.aiScore.length,
        analysisMatches: sections.analyses.length,
        historyMatches: sections.history.length,
        historyTotalRows: historyPayload.summary?.totalRows || 0
      },
      results: groupedResults,
      groupedResults,
      rawResults: rawSearchResults,
      sections,
      sources: {
        radarPath,
        aiScorePath,
        latestAnalysisPath,
        historyDatabase: historyPayload.database || null
      },
      errors,
      safety: {
        readsPrivateKey: false,
        walletWriteAllowed: false,
        orderSendAllowed: false,
        startsExecutor: false,
        mutatesMt5: false,
        readOnly: true
      }
    });
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
  if (req.method === 'GET' && (requestUrl.split('?')[0] === '/api/mt5-readonly' || requestUrl.split('?')[0].startsWith('/api/mt5-readonly/'))) {
    const pathPart = requestUrl.split('?')[0];
    const endpoint = pathPart === '/api/mt5-readonly' ? 'snapshot' : path.basename(pathPart);
    handleMt5Readonly(req, res, endpoint);
    return;
  }
  if (req.method === 'GET' && (requestUrl.split('?')[0] === '/api/mt5-symbol-registry' || requestUrl.split('?')[0].startsWith('/api/mt5-symbol-registry/'))) {
    const pathPart = requestUrl.split('?')[0];
    const endpoint = pathPart === '/api/mt5-symbol-registry' ? 'registry' : path.basename(pathPart);
    handleMt5SymbolRegistry(req, res, endpoint);
    return;
  }
  if (req.method === 'GET' && requestUrl.split('?')[0] === '/api/polymarket/history') {
    handlePolymarketHistory(req, res);
    return;
  }
  if (req.method === 'GET' && requestUrl.split('?')[0] === '/api/polymarket/radar') {
    handlePolymarketReadOnlyJson(req, res, polymarketRadarName, '/api/polymarket/radar');
    return;
  }
  if (req.method === 'GET' && requestUrl.split('?')[0] === '/api/polymarket/ai-score') {
    handlePolymarketReadOnlyJson(req, res, polymarketAiScoreName, '/api/polymarket/ai-score');
    return;
  }
  if (req.method === 'GET' && requestUrl.split('?')[0] === '/api/polymarket/analyze/history') {
    handlePolymarketAnalyzeHistory(req, res);
    return;
  }
  if (req.method === 'GET' && requestUrl.split('?')[0] === '/api/polymarket/search') {
    handlePolymarketSearch(req, res);
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
