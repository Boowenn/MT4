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
const polymarketRadarWorkerName = 'QuantGod_PolymarketRadarWorkerV2.json';
const polymarketAiScoreName = 'QuantGod_PolymarketAiScoreV1.json';
const polymarketSingleMarketAnalysisName = 'QuantGod_PolymarketSingleMarketAnalysis.json';
const polymarketCrossMarketLinkageName = 'QuantGod_PolymarketCrossMarketLinkage.json';
const polymarketCanaryExecutorContractName = 'QuantGod_PolymarketCanaryExecutorContract.json';
const polymarketAutoGovernanceName = 'QuantGod_PolymarketAutoGovernance.json';
const polymarketHistoryApiScript = path.join(repoRoot, 'tools', 'query_polymarket_history_api.py');
const mt5ReadonlyBridgeScript = path.join(repoRoot, 'tools', 'mt5_readonly_bridge.py');
const mt5SymbolRegistryScript = path.join(repoRoot, 'tools', 'mt5_symbol_registry.py');
const polymarketHistoryTables = new Set([
  'all',
  'opportunities',
  'analyses',
  'simulations',
  'runs',
  'snapshots',
  'worker-runs',
  'worker-trends',
  'worker-queue',
  'cross-linkage',
  'canary-contracts',
  'auto-governance',
]);
const mt5ReadonlyEndpoints = new Set(['status', 'account', 'positions', 'orders', 'symbols', 'quote', 'snapshot']);
const mt5SymbolRegistryEndpoints = new Set(['registry', 'resolve']);
const polymarketReadOnlyJsonFiles = new Set([
  polymarketRadarName,
  polymarketRadarWorkerName,
  polymarketAiScoreName,
  polymarketSingleMarketAnalysisName,
  polymarketCrossMarketLinkageName,
  polymarketCanaryExecutorContractName,
  polymarketAutoGovernanceName
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
      nextStep: item.nextStep || '',
      semanticScore: item.semanticScore,
      semanticConfidence: item.semanticConfidence,
      semanticRecommendation: item.semanticRecommendation,
      semanticRisk: item.semanticRisk,
      llmReviewed: item.llmReviewed,
      llmReason: item.llmReview?.reason || ''
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

function compactCrossLinkageResult(item = {}, generatedAt = '') {
  return {
    sourceType: 'cross-linkage',
    sourceLabel: '跨市场联动',
    title: firstDefined(item.question, item.eventTitle, item.marketId, '--'),
    subtitle: firstDefined(item.primaryRiskTag, item.macroRiskState, item.category),
    marketId: firstDefined(item.marketId),
    url: firstDefined(item.polymarketUrl, item.url),
    generatedAt: firstDefined(item.generatedAt, generatedAt),
    risk: firstDefined(item.macroRiskState, item.sourceRisk),
    recommendation: firstDefined(item.primaryRiskTag, item.macroRiskState, 'AWARENESS_ONLY'),
    track: firstDefined(item.suggestedShadowTrack),
    probability: firstDefined(item.probability),
    divergence: firstDefined(item.divergence),
    score: numericScore(item.confidence, item.sourceScore),
    detail: {
      historyType: 'cross-linkage',
      rawType: 'cross-market-linkage',
      primaryRiskTag: firstDefined(item.primaryRiskTag),
      riskTags: firstDefined(item.riskTags),
      matchedKeywords: firstDefined(item.matchedKeywords),
      linkedMt5Symbols: firstDefined(item.linkedMt5Symbols),
      macroRiskState: firstDefined(item.macroRiskState),
      sourceTypes: firstDefined(item.sourceTypes),
      mt5ExecutionAllowed: firstDefined(item.mt5ExecutionAllowed),
      walletWriteAllowed: firstDefined(item.walletWriteAllowed),
      orderSendAllowed: firstDefined(item.orderSendAllowed)
    }
  };
}

function compactCanaryContractResult(item = {}, generatedAt = '') {
  return {
    sourceType: 'canary-contract',
    sourceLabel: 'Canary 契约',
    title: firstDefined(item.question, item.marketId, item.canaryContractId, '--'),
    subtitle: firstDefined(item.canaryState, item.track, item.side),
    marketId: firstDefined(item.marketId),
    url: firstDefined(item.polymarketUrl, item.url),
    generatedAt: firstDefined(item.generatedAt, generatedAt),
    risk: firstDefined(item.crossRiskTag, item.macroRiskState, item.aiColor),
    recommendation: firstDefined(item.decision, item.canaryState, 'CANARY_CONTRACT_ONLY_NO_WALLET_WRITE'),
    track: firstDefined(item.track),
    probability: null,
    divergence: null,
    score: numericScore(item.aiScore, item.sourceScore),
    detail: {
      historyType: 'canary-contracts',
      rawType: 'canary-contract',
      canaryContractId: firstDefined(item.canaryContractId),
      canaryEligibleNow: firstDefined(item.canaryEligibleNow),
      referenceStakeUSDC: firstDefined(item.referenceStakeUSDC),
      canaryStakeUSDC: firstDefined(item.canaryStakeUSDC),
      maxSingleBetUSDC: firstDefined(item.maxSingleBetUSDC),
      maxDailyLossUSDC: firstDefined(item.maxDailyLossUSDC),
      takeProfitPct: firstDefined(item.takeProfitPct),
      stopLossPct: firstDefined(item.stopLossPct),
      trailingProfitPct: firstDefined(item.trailingProfitPct),
      dryRunState: firstDefined(item.dryRunState),
      outcomeState: firstDefined(item.outcomeState),
      blockers: firstDefined(item.blockers, item.blockersJson),
      walletWriteAllowed: firstDefined(item.walletWriteAllowed),
      orderSendAllowed: firstDefined(item.orderSendAllowed),
      startsExecutor: firstDefined(item.startsExecutor)
    }
  };
}

function compactAutoGovernanceResult(item = {}, generatedAt = '') {
  return {
    sourceType: 'auto-governance',
    sourceLabel: '自动治理',
    title: firstDefined(item.question, item.marketId, item.governanceId, '--'),
    subtitle: firstDefined(item.governanceState, item.track, item.riskLevel),
    marketId: firstDefined(item.marketId),
    url: firstDefined(item.polymarketUrl, item.url),
    generatedAt: firstDefined(item.generatedAt, generatedAt),
    risk: firstDefined(item.riskLevel, item.crossRiskTag, item.macroRiskState, item.aiColor),
    recommendation: firstDefined(item.recommendedAction, item.governanceState, 'AUTO_GOVERNANCE_RECOMMENDATIONS_ONLY_NO_WALLET_WRITE'),
    track: firstDefined(item.track),
    probability: null,
    divergence: null,
    score: numericScore(item.score, item.aiScore, item.sourceScore),
    detail: {
      historyType: 'auto-governance',
      rawType: 'auto-governance',
      governanceId: firstDefined(item.governanceId),
      currentState: firstDefined(item.currentState),
      governanceState: firstDefined(item.governanceState),
      recommendedAction: firstDefined(item.recommendedAction),
      riskLevel: firstDefined(item.riskLevel),
      aiScore: firstDefined(item.aiScore),
      sourceScore: firstDefined(item.sourceScore),
      canaryState: firstDefined(item.canaryState),
      dryRunState: firstDefined(item.dryRunState),
      outcomeState: firstDefined(item.outcomeState),
      wouldExitReason: firstDefined(item.wouldExitReason),
      crossRiskTag: firstDefined(item.crossRiskTag),
      macroRiskState: firstDefined(item.macroRiskState),
      blockers: firstDefined(item.blockers, item.blockersJson),
      sourceTypes: firstDefined(item.sourceTypes, item.sourceTypesJson),
      nextTest: firstDefined(item.nextTest),
      walletWriteAllowed: firstDefined(item.walletWriteAllowed),
      orderSendAllowed: firstDefined(item.orderSendAllowed),
      startsExecutor: firstDefined(item.startsExecutor),
      mutatesMt5: firstDefined(item.mutatesMt5),
      canPromoteToLiveExecution: firstDefined(item.canPromoteToLiveExecution)
    }
  };
}

function isWorkerHistoryType(historyType = '') {
  return ['worker-runs', 'worker-trends', 'worker-queue'].includes(String(historyType || '').trim());
}

function isWorkerHistoryRow(row = {}) {
  return isWorkerHistoryType(row.historyType);
}

function isCrossLinkageHistoryRow(row = {}) {
  return String(row.historyType || '').trim() === 'cross-linkage';
}

function isCanaryContractHistoryRow(row = {}) {
  return String(row.historyType || '').trim() === 'canary-contracts';
}

function isAutoGovernanceHistoryRow(row = {}) {
  return String(row.historyType || '').trim() === 'auto-governance';
}

function getHistorySourceLabel(historyType = '') {
  const normalized = String(historyType || '').trim();
  if (normalized === 'worker-runs') return 'Worker 批次';
  if (normalized === 'worker-trends') return '趋势缓存';
  if (normalized === 'worker-queue') return '雷达队列';
  if (normalized === 'cross-linkage') return '跨市场联动';
  if (normalized === 'canary-contracts') return 'Canary 契约';
  if (normalized === 'auto-governance') return '自动治理';
  if (normalized === 'opportunities') return '机会历史';
  if (normalized === 'analyses') return '分析历史';
  if (normalized === 'simulations') return '模拟历史';
  if (normalized === 'runs') return '构建批次';
  if (normalized === 'snapshots') return '研究快照';
  return '历史库';
}

function compactHistoryResult(row = {}) {
  const historyType = firstDefined(row.historyType, 'history');
  const workerRow = isWorkerHistoryType(historyType);
  const crossRow = isCrossLinkageHistoryRow(row);
  const canaryRow = isCanaryContractHistoryRow(row);
  const autoGovernanceRow = isAutoGovernanceHistoryRow(row);
  const workerSubtitle = firstDefined(
    row.nextAction,
    row.queueState,
    row.trendDirection,
    row.status,
    row.decision,
    row.schemaVersion
  );
  return {
    sourceType: workerRow || crossRow || canaryRow || autoGovernanceRow ? historyType : firstDefined(row.historyType, 'history'),
    sourceLabel: getHistorySourceLabel(historyType),
    title: firstDefined(row.question, row.query, row.topMarket, row.marketId, row.runId, row.mode, '--'),
    subtitle: crossRow
      ? firstDefined(row.primaryRiskTag, row.macroRiskState, row.category)
      : canaryRow
      ? firstDefined(row.canaryState, row.track, row.side)
      : autoGovernanceRow
      ? firstDefined(row.governanceState, row.recommendedAction, row.riskLevel)
      : workerRow
      ? workerSubtitle
      : firstDefined(row.recommendation, row.state, row.decision, row.schemaVersion),
    marketId: firstDefined(row.marketId),
    url: firstDefined(row.polymarketUrl, row.url),
    generatedAt: firstDefined(row.generatedAt, row.seenAt, row.lastSeenAt, row.firstSeenAt),
    risk: firstDefined(row.risk, row.topRisk, row.crossRiskTag, row.macroRiskState, row.aiColor),
    recommendation: crossRow
      ? firstDefined(row.primaryRiskTag, row.macroRiskState, 'AWARENESS_ONLY')
      : canaryRow
      ? firstDefined(row.decision, row.canaryState, 'CANARY_CONTRACT_ONLY_NO_WALLET_WRITE')
      : autoGovernanceRow
      ? firstDefined(row.recommendedAction, row.governanceState, 'AUTO_GOVERNANCE_RECOMMENDATIONS_ONLY_NO_WALLET_WRITE')
      : workerRow
      ? firstDefined(row.nextAction, row.queueState, row.status, row.decision, 'WORKER_EVIDENCE')
      : firstDefined(row.recommendation, row.recommendedAction, row.state, row.decision),
    track: firstDefined(row.suggestedShadowTrack, row.track, row.source),
    probability: firstDefined(row.probability, row.marketProbability, row.lastProbability),
    divergence: firstDefined(row.divergence, row.probabilityDelta),
    score: numericScore(row.score, row.priorityScore, row.aiRuleScore, row.ruleScore, row.bestAiRuleScore, row.lastAiRuleScore, row.topScore, row.confidence, row.sourceScore, row.aiScore, row.executedPf),
    detail: {
      historyType,
      source: firstDefined(row.source),
      rawType: workerRow ? 'worker-history' : (autoGovernanceRow ? 'auto-governance-history' : (canaryRow ? 'canary-history' : 'history')),
      runId: firstDefined(row.runId),
      candidateId: firstDefined(row.candidateId),
      queueState: firstDefined(row.queueState),
      executionMode: firstDefined(row.executionMode),
      nextAction: firstDefined(row.nextAction),
      trendDirection: firstDefined(row.trendDirection),
      seenCount: firstDefined(row.seenCount),
      staleCycles: firstDefined(row.staleCycles),
      probabilityDelta: firstDefined(row.probabilityDelta),
      aiRuleScoreDelta: firstDefined(row.aiRuleScoreDelta),
      volume24hDelta: firstDefined(row.volume24hDelta),
      candidateQueueSize: firstDefined(row.candidateQueueSize),
      uniqueMarkets: firstDefined(row.uniqueMarkets),
      recurringMarkets: firstDefined(row.recurringMarkets),
      newMarkets: firstDefined(row.newMarkets),
      primaryRiskTag: firstDefined(row.primaryRiskTag),
      riskTags: firstDefined(row.riskTagsJson),
      matchedKeywords: firstDefined(row.matchedKeywordsJson),
      linkedMt5Symbols: firstDefined(row.linkedMt5SymbolsJson),
      macroRiskState: firstDefined(row.macroRiskState),
      sourceTypes: firstDefined(row.sourceTypesJson),
      mt5ExecutionAllowed: firstDefined(row.mt5ExecutionAllowed),
      canaryContractId: firstDefined(row.canaryContractId),
      canaryEligibleNow: firstDefined(row.canaryEligibleNow),
      referenceStakeUSDC: firstDefined(row.referenceStakeUSDC),
      canaryStakeUSDC: firstDefined(row.canaryStakeUSDC),
      governanceId: firstDefined(row.governanceId),
      currentState: firstDefined(row.currentState),
      governanceState: firstDefined(row.governanceState),
      recommendedAction: firstDefined(row.recommendedAction),
      riskLevel: firstDefined(row.riskLevel),
      nextTest: firstDefined(row.nextTest),
      canPromoteToLiveExecution: firstDefined(row.canPromoteToLiveExecution),
      maxSingleBetUSDC: firstDefined(row.maxSingleBetUSDC),
      maxDailyLossUSDC: firstDefined(row.maxDailyLossUSDC),
      takeProfitPct: firstDefined(row.takeProfitPct),
      stopLossPct: firstDefined(row.stopLossPct),
      trailingProfitPct: firstDefined(row.trailingProfitPct),
      dryRunState: firstDefined(row.dryRunState),
      outcomeState: firstDefined(row.outcomeState),
      blockers: firstDefined(row.blockersJson),
      walletWriteAllowed: firstDefined(row.walletWriteAllowed),
      orderSendAllowed: firstDefined(row.orderSendAllowed),
      startsExecutor: firstDefined(row.startsExecutor)
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

    let crossLinkage = null;
    let crossLinkagePath = '';
    try {
      const read = readQuantGodJsonFile(polymarketCrossMarketLinkageName);
      crossLinkage = withServiceMeta(read.payload, '/api/polymarket/cross-linkage', read.filePath);
      crossLinkagePath = read.filePath;
    } catch (error) {
      errors.push({ source: 'cross-linkage', error: error.message || String(error) });
    }

    let canaryContract = null;
    let canaryContractPath = '';
    try {
      const read = readQuantGodJsonFile(polymarketCanaryExecutorContractName);
      canaryContract = withServiceMeta(read.payload, '/api/polymarket/canary-executor-contract', read.filePath);
      canaryContractPath = read.filePath;
    } catch (error) {
      errors.push({ source: 'canary-contract', error: error.message || String(error) });
    }

    let autoGovernance = null;
    let autoGovernancePath = '';
    try {
      const read = readQuantGodJsonFile(polymarketAutoGovernanceName);
      autoGovernance = withServiceMeta(read.payload, '/api/polymarket/auto-governance', read.filePath);
      autoGovernancePath = read.filePath;
    } catch (error) {
      errors.push({ source: 'auto-governance', error: error.message || String(error) });
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
    const crossLinkageItems = Array.isArray(crossLinkage?.linkages)
      ? crossLinkage.linkages.filter((item) => matchesSearchQuery(item, query)).slice(0, limit)
      : [];
    const canaryItems = Array.isArray(canaryContract?.candidateContracts)
      ? canaryContract.candidateContracts.filter((item) => matchesSearchQuery(item, query)).slice(0, limit)
      : [];
    const autoGovernanceItems = Array.isArray(autoGovernance?.governanceDecisions)
      ? autoGovernance.governanceDecisions.filter((item) => matchesSearchQuery(item, query)).slice(0, limit)
      : [];

    const historyPayload = historyResult.payload || {};
    const rawHistoryRows = query
      ? (historyPayload.search?.rows || [])
      : [
          ...(historyPayload.recent?.opportunities || []),
          ...(historyPayload.recent?.analyses || []),
          ...(historyPayload.recent?.simulations || []),
        ].slice(0, limit);
    const workerRows = query
      ? rawHistoryRows.filter(isWorkerHistoryRow).slice(0, limit)
      : [
          ...(historyPayload.recent?.['worker-runs'] || historyPayload.recent?.workerRuns || []),
          ...(historyPayload.recent?.['worker-trends'] || historyPayload.recent?.workerTrends || []),
          ...(historyPayload.recent?.['worker-queue'] || historyPayload.recent?.workerQueue || []),
        ].slice(0, limit);
    const crossRows = query
      ? rawHistoryRows.filter(isCrossLinkageHistoryRow).slice(0, limit)
      : [
          ...(historyPayload.recent?.['cross-linkage'] || historyPayload.recent?.crossMarketLinkage || []),
        ].slice(0, limit);
    const canaryRows = query
      ? rawHistoryRows.filter(isCanaryContractHistoryRow).slice(0, limit)
      : [
          ...(historyPayload.recent?.['canary-contracts'] || historyPayload.recent?.canaryContracts || []),
        ].slice(0, limit);
    const autoGovernanceRows = query
      ? rawHistoryRows.filter(isAutoGovernanceHistoryRow).slice(0, limit)
      : [
          ...(historyPayload.recent?.['auto-governance'] || historyPayload.recent?.autoGovernance || []),
        ].slice(0, limit);
    const historyRows = query
      ? rawHistoryRows.filter((row) => !isWorkerHistoryRow(row) && !isCrossLinkageHistoryRow(row) && !isCanaryContractHistoryRow(row) && !isAutoGovernanceHistoryRow(row)).slice(0, limit)
      : rawHistoryRows;
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
      worker: workerRows.slice(0, limit).map(compactHistoryResult),
      crossLinkage: [
        ...crossLinkageItems.map((item) => compactCrossLinkageResult(item, crossLinkage?.generatedAt)),
        ...crossRows.slice(0, limit).map(compactHistoryResult)
      ].slice(0, limit),
      canary: [
        ...canaryItems.map((item) => compactCanaryContractResult(item, canaryContract?.generatedAt)),
        ...canaryRows.slice(0, limit).map(compactHistoryResult)
      ].slice(0, limit),
      autoGovernance: [
        ...autoGovernanceItems.map((item) => compactAutoGovernanceResult(item, autoGovernance?.generatedAt)),
        ...autoGovernanceRows.slice(0, limit).map(compactHistoryResult)
      ].slice(0, limit),
      history: historyRows.slice(0, limit).map(compactHistoryResult)
    };
    const rawSearchResults = sortSearchResults([
      ...sections.radar,
      ...sections.aiScore,
      ...sections.analyses,
      ...sections.worker,
      ...sections.crossLinkage,
      ...sections.canary,
      ...sections.autoGovernance,
      ...sections.history
    ]);
    const groupedResults = groupSearchResultsByMarket(rawSearchResults, limit);

    sendJson(res, 200, {
      mode: 'POLYMARKET_SEARCH_API_V5_AUTO_GOVERNANCE_EVIDENCE_GROUPS',
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
        workerMatches: sections.worker.length,
        crossLinkageMatches: sections.crossLinkage.length,
        canaryMatches: sections.canary.length,
        autoGovernanceMatches: sections.autoGovernance.length,
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
        crossLinkagePath,
        canaryContractPath,
        autoGovernancePath,
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
  if (req.method === 'GET' && requestUrl.split('?')[0] === '/api/polymarket/radar-worker') {
    handlePolymarketReadOnlyJson(req, res, polymarketRadarWorkerName, '/api/polymarket/radar-worker');
    return;
  }
  if (req.method === 'GET' && requestUrl.split('?')[0] === '/api/polymarket/cross-linkage') {
    handlePolymarketReadOnlyJson(req, res, polymarketCrossMarketLinkageName, '/api/polymarket/cross-linkage');
    return;
  }
  if (req.method === 'GET' && requestUrl.split('?')[0] === '/api/polymarket/canary-executor-contract') {
    handlePolymarketReadOnlyJson(req, res, polymarketCanaryExecutorContractName, '/api/polymarket/canary-executor-contract');
    return;
  }
  if (req.method === 'GET' && requestUrl.split('?')[0] === '/api/polymarket/auto-governance') {
    handlePolymarketReadOnlyJson(req, res, polymarketAutoGovernanceName, '/api/polymarket/auto-governance');
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
