const JSON_HEADERS = { 'Content-Type': 'application/json' };

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const text = await response.text();
  let payload = {};
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch (error) {
      throw new Error(`Non-JSON response from ${url}: ${text.slice(0, 200)}`);
    }
  }
  if (!response.ok) {
    throw new Error(payload.error || `HTTP ${response.status} for ${url}`);
  }
  return payload;
}

export async function runAiAnalysis({ symbol, timeframes = ['M15', 'H1', 'H4', 'D1'] }) {
  return fetchJson('/api/ai-analysis/run', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ symbol, timeframes }),
  });
}

export function getAiLatest() {
  return fetchJson('/api/ai-analysis/latest');
}

export function getAiHistory({ symbol = '', limit = 20 } = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (symbol) params.set('symbol', symbol);
  return fetchJson(`/api/ai-analysis/history?${params.toString()}`);
}

export function getAiHistoryItem(id) {
  return fetchJson(`/api/ai-analysis/history/${encodeURIComponent(id)}`);
}

export function getAiConfig() {
  return fetchJson('/api/ai-analysis/config');
}

export function getKline({ symbol, tf = 'H1', bars = 200 }) {
  const params = new URLSearchParams({ symbol, tf, bars: String(bars) });
  return fetchJson(`/api/mt5-readonly/kline?${params.toString()}`);
}

export function getChartTrades({ symbol, days = 30 }) {
  const params = new URLSearchParams({ symbol, days: String(days) });
  return fetchJson(`/api/mt5-readonly/trades?${params.toString()}`);
}

export function getShadowSignals({ symbol, days = 7 }) {
  const params = new URLSearchParams({ symbol, days: String(days) });
  return fetchJson(`/api/shadow-signals?${params.toString()}`);
}

export async function getSymbolRegistry() {
  try {
    const payload = await fetchJson('/api/mt5-symbol-registry');
    const items = payload.items || payload.symbols || payload.registry || [];
    if (Array.isArray(items) && items.length) {
      return items
        .map((item) => ({
          symbol: item.brokerSymbol || item.symbol || item.canonicalSymbol || item.name,
          label: item.displayName || item.brokerSymbol || item.symbol || item.canonicalSymbol || item.name,
          assetClass: item.assetClass || item.category || '',
        }))
        .filter((item) => item.symbol);
    }
  } catch (error) {
    // Keep Phase 1 usable even when the MT5 symbol registry is not running.
  }
  return [
    { symbol: 'EURUSDc', label: 'EURUSDc', assetClass: 'Forex' },
    { symbol: 'USDJPYc', label: 'USDJPYc', assetClass: 'Forex' },
    { symbol: 'XAUUSDc', label: 'XAUUSDc', assetClass: 'Metal' },
  ];
}
