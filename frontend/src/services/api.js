const JSON_HEADERS = { Accept: 'application/json' };

async function fetchJson(url, fallback = null, options = {}) {
  try {
    const response = await fetch(url, {
      headers: JSON_HEADERS,
      cache: 'no-store',
      ...options
    });
    if (!response.ok) {
      return fallback;
    }
    return await response.json();
  } catch (_) {
    return fallback;
  }
}

async function fetchText(url, fallback = '', options = {}) {
  try {
    const response = await fetch(url, {
      headers: { Accept: 'text/plain,text/csv,*/*' },
      cache: 'no-store',
      ...options
    });
    if (!response.ok) {
      return fallback;
    }
    return await response.text();
  } catch (_) {
    return fallback;
  }
}

function parseCsv(text) {
  const source = String(text || '').replace(/^\uFEFF/, '');
  if (!source.trim()) return [];

  const rows = [];
  let row = [];
  let field = '';
  let quoted = false;

  for (let i = 0; i < source.length; i += 1) {
    const char = source[i];
    const next = source[i + 1];

    if (quoted) {
      if (char === '"' && next === '"') {
        field += '"';
        i += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        field += char;
      }
      continue;
    }

    if (char === '"') {
      quoted = true;
    } else if (char === ',') {
      row.push(field);
      field = '';
    } else if (char === '\n') {
      row.push(field);
      rows.push(row);
      row = [];
      field = '';
    } else if (char !== '\r') {
      field += char;
    }
  }

  row.push(field);
  rows.push(row);

  const headers = (rows.shift() || []).map((header) => String(header || '').trim());
  if (!headers.length) return [];
  return rows
    .filter((values) => values.some((value) => String(value || '').trim() !== ''))
    .map((values) => Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ''])));
}

async function fetchCsv(url) {
  return parseCsv(await fetchText(url, ''));
}

async function postJson(url, payload, fallback = null) {
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        ...JSON_HEADERS,
        'Content-Type': 'application/json'
      },
      cache: 'no-store',
      body: JSON.stringify(payload || {})
    });
    if (!response.ok) {
      return fallback;
    }
    return await response.json();
  } catch (_) {
    return fallback;
  }
}

export async function loadDashboardState(query = '') {
  const search = new URLSearchParams({
    q: query || '',
    limit: '12'
  });

  const [
    latest,
    mt5Snapshot,
    governance,
    backtest,
    paramStatus,
    paramResults,
    runRecovery,
    strategyRegistry,
    polySearch,
    polyRadar,
    polyWorker,
    polyAiScore,
    polyHistory,
    polyAutoGov,
    polyCanary,
    polyCross,
    polyMarkets,
    polyAssets,
    shadowSignalRows,
    shadowOutcomeRows,
    shadowCandidateRows,
    shadowCandidateOutcomeRows,
    paramLabResultRows,
    tradingAuditRows,
    manualAlphaRows,
    polyRadarRows,
    polyAiScoreRows,
    polyCanaryRows,
    polyAutoGovRows,
    polyCrossRows,
    polySingleAnalysisRows,
    polyWorkerRows
  ] = await Promise.all([
    fetchJson('/api/latest'),
    fetchJson('/api/mt5-readonly/snapshot'),
    fetchJson('/QuantGod_GovernanceAdvisor.json'),
    fetchJson('/QuantGod_BacktestSummary.json'),
    fetchJson('/QuantGod_ParamLabStatus.json'),
    fetchJson('/QuantGod_ParamLabResults.json'),
    fetchJson('/QuantGod_ParamLabRunRecovery.json'),
    fetchJson('/QuantGod_StrategyVersionRegistry.json'),
    fetchJson(`/api/polymarket/search?${search.toString()}`),
    fetchJson('/api/polymarket/radar?limit=12'),
    fetchJson('/api/polymarket/radar-worker'),
    fetchJson('/api/polymarket/ai-score'),
    fetchJson('/api/polymarket/history?table=all&limit=8'),
    fetchJson('/api/polymarket/auto-governance'),
    fetchJson('/api/polymarket/canary-executor-contract'),
    fetchJson('/api/polymarket/cross-linkage'),
    fetchJson('/api/polymarket/markets?limit=10&sort=volume'),
    fetchJson('/api/polymarket/asset-opportunities?limit=10'),
    fetchCsv('/QuantGod_ShadowSignalLedger.csv'),
    fetchCsv('/QuantGod_ShadowOutcomeLedger.csv'),
    fetchCsv('/QuantGod_ShadowCandidateLedger.csv'),
    fetchCsv('/QuantGod_ShadowCandidateOutcomeLedger.csv'),
    fetchCsv('/QuantGod_ParamLabResultsLedger.csv'),
    fetchCsv('/QuantGod_MT5TradingAuditLedger.csv'),
    fetchCsv('/QuantGod_ManualAlphaLedger.csv'),
    fetchCsv('/QuantGod_PolymarketMarketRadar.csv'),
    fetchCsv('/QuantGod_PolymarketAiScoreV1.csv'),
    fetchCsv('/QuantGod_PolymarketCanaryExecutorLedger.csv'),
    fetchCsv('/QuantGod_PolymarketAutoGovernanceLedger.csv'),
    fetchCsv('/QuantGod_PolymarketCrossMarketLinkage.csv'),
    fetchCsv('/QuantGod_PolymarketSingleMarketAnalysisLedger.csv'),
    fetchCsv('/QuantGod_PolymarketRadarWorkerV2.csv')
  ]);

  return {
    mt5: {
      latest,
      snapshot: mt5Snapshot,
      governance,
      backtest,
      paramStatus,
      paramResults,
      runRecovery,
      strategyRegistry,
      ledgers: {
        shadowSignals: shadowSignalRows,
        shadowOutcomes: shadowOutcomeRows,
        shadowCandidates: shadowCandidateRows,
        shadowCandidateOutcomes: shadowCandidateOutcomeRows,
        paramLabResults: paramLabResultRows,
        tradingAudit: tradingAuditRows,
        manualAlpha: manualAlphaRows
      }
    },
    polymarket: {
      search: polySearch,
      radar: polyRadar,
      worker: polyWorker,
      aiScore: polyAiScore,
      history: polyHistory,
      autoGovernance: polyAutoGov,
      canary: polyCanary,
      cross: polyCross,
      markets: polyMarkets,
      assets: polyAssets,
      ledgers: {
        radar: polyRadarRows,
        aiScores: polyAiScoreRows,
        canary: polyCanaryRows,
        autoGovernance: polyAutoGovRows,
        cross: polyCrossRows,
        singleAnalysis: polySingleAnalysisRows,
        worker: polyWorkerRows
      }
    }
  };
}

export async function submitPolymarketRequest(payload) {
  return postJson('/api/polymarket/single-market-request', payload, {
    ok: false,
    error: 'request_failed'
  });
}
