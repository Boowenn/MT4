const jsonHeaders = { 'Content-Type': 'application/json' }

async function requestJson(url, options = {}) {
  const res = await fetch(url, options)
  const text = await res.text()
  let payload = {}
  try {
    payload = text ? JSON.parse(text) : {}
  } catch (error) {
    payload = { ok: false, error: `Invalid JSON response: ${error.message}`, raw: text }
  }
  if (!res.ok && payload.ok !== false) {
    payload.ok = false
    payload.error = payload.error || `HTTP ${res.status}`
  }
  return payload
}

export const phase3Api = {
  vibeConfig: () => requestJson('/api/vibe-coding/config'),
  generateStrategy: (body) => requestJson('/api/vibe-coding/generate', { method: 'POST', headers: jsonHeaders, body: JSON.stringify(body || {}) }),
  iterateStrategy: (body) => requestJson('/api/vibe-coding/iterate', { method: 'POST', headers: jsonHeaders, body: JSON.stringify(body || {}) }),
  backtestStrategy: (body) => requestJson('/api/vibe-coding/backtest', { method: 'POST', headers: jsonHeaders, body: JSON.stringify(body || {}) }),
  analyzeBacktest: (body) => requestJson('/api/vibe-coding/analyze', { method: 'POST', headers: jsonHeaders, body: JSON.stringify(body || {}) }),
  listStrategies: () => requestJson('/api/vibe-coding/strategies'),
  getStrategy: (strategyId, version) => requestJson(`/api/vibe-coding/strategy/${encodeURIComponent(strategyId)}${version ? `?version=${encodeURIComponent(version)}` : ''}`),
  aiV2Config: () => requestJson('/api/ai-analysis-v2/config'),
  runAiV2: (body) => requestJson('/api/ai-analysis-v2/run', { method: 'POST', headers: jsonHeaders, body: JSON.stringify(body || {}) }),
  aiV2Latest: () => requestJson('/api/ai-analysis-v2/latest'),
  aiV2History: (params = {}) => requestJson(`/api/ai-analysis-v2/history?${new URLSearchParams(params).toString()}`),
  klineAiOverlays: (params = {}) => requestJson(`/api/kline/ai-overlays?${new URLSearchParams(params).toString()}`),
  klineVibeIndicators: (params = {}) => requestJson(`/api/kline/vibe-indicators?${new URLSearchParams(params).toString()}`),
  klineRealtimeConfig: () => requestJson('/api/kline/realtime-config'),
}

export default phase3Api
