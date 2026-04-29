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
    polyAssets
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
    fetchJson('/api/polymarket/asset-opportunities?limit=10')
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
      strategyRegistry
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
      assets: polyAssets
    }
  };
}

export async function submitPolymarketRequest(payload) {
  return postJson('/api/polymarket/single-market-request', payload, {
    ok: false,
    error: 'request_failed'
  });
}
