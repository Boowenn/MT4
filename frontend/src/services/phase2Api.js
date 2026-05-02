const JSON_HEADERS = { Accept: 'application/json' };

export const PHASE2_ENDPOINTS = Object.freeze({
  governance: [
    ['/api/governance/advisor', 'Governance Advisor'],
    ['/api/governance/version-registry', 'Version Registry'],
    ['/api/governance/promotion-gate', 'Promotion Gate'],
    ['/api/governance/optimizer-v2', 'Optimizer V2'],
  ],
  paramlab: [
    ['/api/paramlab/status', 'Status'],
    ['/api/paramlab/results', 'Results'],
    ['/api/paramlab/scheduler', 'Scheduler'],
    ['/api/paramlab/recovery', 'Recovery'],
    ['/api/paramlab/report-watcher', 'Report Watcher'],
    ['/api/paramlab/tester-window', 'Tester Window'],
  ],
  trades: [
    ['/api/trades/journal?limit=200', 'Trade Journal'],
    ['/api/trades/close-history?limit=200', 'Close History'],
    ['/api/trades/outcome-labels?limit=200', 'Outcome Labels'],
    ['/api/trades/trading-audit?limit=200', 'Trading Audit'],
  ],
  research: [
    ['/api/research/stats', 'Research Stats'],
    ['/api/research/stats-ledger?limit=200', 'Research Stats Ledger'],
    ['/api/research/strategy-evaluation?limit=200', 'Strategy Evaluation'],
    ['/api/research/regime-evaluation?limit=200', 'Regime Evaluation'],
    ['/api/research/manual-alpha?limit=200', 'Manual Alpha'],
  ],
  shadow: [
    ['/api/shadow/signals?days=7&limit=200', 'Shadow Signals'],
    ['/api/shadow/candidates?limit=200', 'Shadow Candidates'],
    ['/api/shadow/outcomes?limit=200', 'Shadow Outcomes'],
    ['/api/shadow/candidate-outcomes?limit=200', 'Candidate Outcomes'],
  ],
  dashboard: [
    ['/api/dashboard/state', 'Dashboard State'],
    ['/api/dashboard/backtest-summary', 'Backtest Summary'],
  ],
});

export async function apiGet(url, fallback = null) {
  try {
    const response = await fetch(url, { headers: JSON_HEADERS, cache: 'no-store' });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      return payload || fallback || { ok: false, error: `HTTP ${response.status}`, endpoint: url };
    }
    return payload;
  } catch (error) {
    return fallback || { ok: false, error: error?.message || String(error), endpoint: url };
  }
}

export async function apiPost(url, payload = {}, fallback = null) {
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { ...JSON_HEADERS, 'Content-Type': 'application/json' },
      cache: 'no-store',
      body: JSON.stringify(payload || {}),
    });
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      return body || fallback || { ok: false, error: `HTTP ${response.status}`, endpoint: url };
    }
    return body;
  } catch (error) {
    return fallback || { ok: false, error: error?.message || String(error), endpoint: url };
  }
}

export function extractRows(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.rows)) return payload.rows;
  if (Array.isArray(payload?.data?.rows)) return payload.data.rows;
  if (Array.isArray(payload?.data?.items)) return payload.data.items;
  if (Array.isArray(payload?.items)) return payload.items;
  if (payload?.data && typeof payload.data === 'object') return [payload.data];
  if (payload && typeof payload === 'object') return [payload];
  return [];
}

export function tableColumns(rows) {
  const keys = [...new Set(rows.flatMap((row) => Object.keys(row || {})))].filter((key) => !key.startsWith('_')).slice(0, 8);
  return keys.map((key) => ({ title: key, dataIndex: key, key, ellipsis: true, sorter: (a, b) => String(a?.[key] ?? '').localeCompare(String(b?.[key] ?? '')) }));
}

export function endpointSummary(payload) {
  const source = payload?.source || payload?._api || payload?._phase2 || {};
  return {
    ok: payload?.ok !== false,
    endpoint: payload?.endpoint || source.endpoint || '--',
    fileName: source.fileName || '--',
    mtimeIso: source.mtimeIso || '--',
    returnedRows: payload?.data?.returnedRows ?? extractRows(payload).length,
  };
}

export function loadNotifyConfig() {
  return apiGet('/api/notify/config', { ok: false, error: 'notify_config_failed' });
}

export function loadNotifyHistory(limit = 50) {
  return apiGet(`/api/notify/history?limit=${Number(limit) || 50}`, { ok: false, items: [] });
}

export function sendNotifyTest(message, dryRun = false) {
  return apiPost('/api/notify/test', { message, dryRun }, { ok: false, error: 'notify_test_failed' });
}
