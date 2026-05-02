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

async function fetchJsonFirst(urls, fallback = null, options = {}) {
  for (const url of urls) {
    const payload = await fetchJson(url, null, options);
    if (payload !== null) {
      return payload;
    }
  }
  return fallback;
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

async function fetchRowsJson(url) {
  const payload = await fetchJson(url, null);
  if (Array.isArray(payload?.data?.rows)) return payload.data.rows;
  if (Array.isArray(payload?.rows)) return payload.rows;
  return [];
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
    paramAutoScheduler,
    paramReportWatcher,
    runRecovery,
    autoTesterWindow,
    dailyReview,
    dailyAutopilot,
    mt5ResearchStats,
    strategyRegistry,
    polySearch,
    polyRadar,
    polyWorker,
    polyAiScore,
    polyHistory,
    polyAutoGov,
    polyCanary,
    polyCanaryRun,
    polyRealTrades,
    polyCross,
    polyMarkets,
    polyAssets,
    polySingleAnalysis,
    shadowSignalRows,
    shadowOutcomeRows,
    shadowCandidateRows,
    shadowCandidateOutcomeRows,
    closeHistoryRows,
    tradeJournalRows,
    paramLabResultRows,
    paramLabAutoSchedulerRows,
    paramLabReportWatcherRows,
    paramLabRunRecoveryRows,
    autoTesterWindowRows,
    mt5ResearchStatsRows,
    strategyEvaluationRows,
    regimeEvaluationRows,
    tradingAuditRows,
    manualAlphaRows,
    polyRadarRows,
    polyAiScoreRows,
    polyCanaryRows,
    polyCanaryPositionRows,
    polyCanaryOrderAuditRows,
    polyCanaryExitRows,
    polyAutoGovRows,
    polyCrossRows,
    polySingleAnalysisRows,
    polyWorkerRows
  ] = await Promise.all([
    fetchJson('/api/latest'),
    fetchJson('/api/mt5-readonly/snapshot'),
    fetchJson('/api/governance/advisor'),
    fetchJson('/api/dashboard/backtest-summary'),
    fetchJson('/api/paramlab/status'),
    fetchJson('/api/paramlab/results'),
    fetchJson('/api/paramlab/scheduler'),
    fetchJson('/api/paramlab/report-watcher'),
    fetchJson('/api/paramlab/recovery'),
    fetchJson('/api/paramlab/tester-window'),
    fetchJsonFirst(['/api/daily-review', '/QuantGod_DailyReview.json']),
    fetchJsonFirst(['/api/daily-autopilot', '/QuantGod_DailyAutopilot.json']),
    fetchJson('/api/research/stats'),
    fetchJson('/api/governance/version-registry'),
    fetchJson(`/api/polymarket/search?${search.toString()}`),
    fetchJson('/api/polymarket/radar?limit=12'),
    fetchJson('/api/polymarket/radar-worker'),
    fetchJson('/api/polymarket/ai-score'),
    fetchJson('/api/polymarket/history?table=all&limit=8'),
    fetchJson('/api/polymarket/auto-governance'),
    fetchJson('/api/polymarket/canary-executor-contract'),
    fetchJson('/api/polymarket/canary-executor-run'),
    fetchJson('/api/polymarket/real-trades'),
    fetchJson('/api/polymarket/cross-linkage'),
    fetchJson('/api/polymarket/markets?limit=10&sort=volume'),
    fetchJson('/api/polymarket/asset-opportunities?limit=10'),
    fetchJson('/api/polymarket/single-market-analysis'),
    fetchRowsJson('/api/shadow/signals?limit=500'),
    fetchRowsJson('/api/shadow/outcomes?limit=500'),
    fetchRowsJson('/api/shadow/candidates?limit=500'),
    fetchRowsJson('/api/shadow/candidate-outcomes?limit=500'),
    fetchRowsJson('/api/trades/close-history?limit=500'),
    fetchRowsJson('/api/trades/journal?limit=500'),
    fetchRowsJson('/api/paramlab/results-ledger?limit=500'),
    fetchRowsJson('/api/paramlab/scheduler-ledger?limit=500'),
    fetchRowsJson('/api/paramlab/report-watcher-ledger?limit=500'),
    fetchRowsJson('/api/paramlab/recovery-ledger?limit=500'),
    fetchRowsJson('/api/paramlab/tester-window-ledger?limit=500'),
    fetchRowsJson('/api/research/stats-ledger?limit=500'),
    fetchRowsJson('/api/research/strategy-evaluation?limit=500'),
    fetchRowsJson('/api/research/regime-evaluation?limit=500'),
    fetchRowsJson('/api/trades/trading-audit?limit=500'),
    fetchRowsJson('/api/research/manual-alpha?limit=500'),
    fetchRowsJson('/api/polymarket/radar-ledger?limit=500'),
    fetchRowsJson('/api/polymarket/ai-score-ledger?limit=500'),
    fetchRowsJson('/api/polymarket/canary-executor-ledger?limit=500'),
    fetchRowsJson('/api/polymarket/canary-position-ledger?limit=500'),
    fetchRowsJson('/api/polymarket/canary-order-audit-ledger?limit=500'),
    fetchRowsJson('/api/polymarket/canary-exit-ledger?limit=500'),
    fetchRowsJson('/api/polymarket/auto-governance-ledger?limit=500'),
    fetchRowsJson('/api/polymarket/cross-market-linkage-ledger?limit=500'),
    fetchRowsJson('/api/polymarket/single-market-analysis-ledger?limit=500'),
    fetchRowsJson('/api/polymarket/radar-worker-ledger?limit=500')
  ]);

  return {
    mt5: {
      latest,
      snapshot: mt5Snapshot,
      governance,
      backtest,
      paramStatus,
      paramResults,
      paramAutoScheduler,
      paramReportWatcher,
      runRecovery,
      autoTesterWindow,
      dailyReview,
      dailyAutopilot,
      mt5ResearchStats,
      strategyRegistry,
      ledgers: {
        shadowSignals: shadowSignalRows,
        shadowOutcomes: shadowOutcomeRows,
        shadowCandidates: shadowCandidateRows,
        shadowCandidateOutcomes: shadowCandidateOutcomeRows,
        closeHistory: closeHistoryRows,
        tradeJournal: tradeJournalRows,
        paramLabResults: paramLabResultRows,
        paramLabAutoScheduler: paramLabAutoSchedulerRows,
        paramLabReportWatcher: paramLabReportWatcherRows,
        paramLabRunRecovery: paramLabRunRecoveryRows,
        autoTesterWindow: autoTesterWindowRows,
        mt5ResearchStats: mt5ResearchStatsRows,
        strategyEvaluation: strategyEvaluationRows,
        regimeEvaluation: regimeEvaluationRows,
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
      canaryRun: polyCanaryRun,
      realTrades: polyRealTrades,
      cross: polyCross,
      markets: polyMarkets,
      assets: polyAssets,
      singleAnalysis: polySingleAnalysis,
      ledgers: {
        radar: polyRadarRows,
        aiScores: polyAiScoreRows,
        canary: polyCanaryRows,
        canaryPositions: polyCanaryPositionRows,
        canaryOrderAudit: polyCanaryOrderAuditRows,
        canaryExits: polyCanaryExitRows,
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

export async function evaluateAutoTesterWindow(payload = {}) {
  return postJson('/api/paramlab/auto-tester/evaluate', payload, {
    ok: false,
    error: 'auto_tester_evaluate_failed'
  });
}

export async function createAutoTesterLock(payload = {}) {
  return postJson('/api/paramlab/auto-tester/lock', payload, {
    ok: false,
    error: 'auto_tester_lock_failed'
  });
}

export async function startAutoTesterWindow(payload = {}) {
  return postJson('/api/paramlab/auto-tester/run', payload, {
    ok: false,
    error: 'auto_tester_run_failed'
  });
}
