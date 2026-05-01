<template>
  <section class="ai-workspace">
    <header class="ai-workspace__top">
      <div>
        <h2>AI 多智能体分析 V1</h2>
        <p>Technical / Risk 并行，Decision 串行；输出仅作为 Governance evidence。</p>
      </div>
      <div class="ai-workspace__controls">
        <SymbolSelector v-model="symbol" :symbols="symbols" />
        <label>
          周期
          <input v-model="timeframesText" placeholder="M15,H1,H4,D1" />
        </label>
        <button :disabled="loading || !symbol" @click="runAnalysis">
          {{ loading ? '分析中…' : '开始分析' }}
        </button>
      </div>
    </header>

    <p v-if="error" class="ai-workspace__error">{{ error }}</p>

    <div class="ai-workspace__grid">
      <div class="ai-workspace__agents">
        <AgentStatusCard title="TechnicalAgent" :report="report?.technical" :status="loading ? 'running' : 'idle'" />
        <AgentStatusCard title="RiskAgent" :report="report?.risk" :status="loading ? 'running' : 'idle'" />
        <AgentStatusCard title="DecisionAgent" :report="report?.decision" :status="loading ? 'running' : 'idle'" />
      </div>
      <DecisionCard :decision="report?.decision || {}" />
    </div>

    <div class="ai-workspace__bottom">
      <ReasoningTabs :report="report" />
      <AnalysisHistory :items="history" @refresh="loadHistory" @select="loadHistoryItem" />
    </div>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue';
import {
  getAiHistory,
  getAiHistoryItem,
  getAiLatest,
  getSymbolRegistry,
  runAiAnalysis,
} from '../../services/phase1Api';
import AgentStatusCard from './AgentStatusCard.vue';
import AnalysisHistory from './AnalysisHistory.vue';
import DecisionCard from './DecisionCard.vue';
import ReasoningTabs from './ReasoningTabs.vue';
import SymbolSelector from './SymbolSelector.vue';

const symbols = ref([]);
const symbol = ref('EURUSDc');
const timeframesText = ref('M15,H1,H4,D1');
const loading = ref(false);
const error = ref('');
const report = ref(null);
const history = ref([]);

async function bootstrap() {
  symbols.value = await getSymbolRegistry();
  if (!symbols.value.find((item) => item.symbol === symbol.value) && symbols.value[0]) {
    symbol.value = symbols.value[0].symbol;
  }
  try {
    const latest = await getAiLatest();
    if (latest && latest.mode) report.value = latest;
  } catch (latestError) {
    // No latest report yet is normal on a fresh runtime.
  }
  await loadHistory();
}

async function runAnalysis() {
  loading.value = true;
  error.value = '';
  try {
    const timeframes = timeframesText.value.split(',').map((item) => item.trim()).filter(Boolean);
    report.value = await runAiAnalysis({ symbol: symbol.value, timeframes });
    await loadHistory();
  } catch (runError) {
    error.value = runError.message || String(runError);
  } finally {
    loading.value = false;
  }
}

async function loadHistory() {
  try {
    const payload = await getAiHistory({ symbol: symbol.value, limit: 20 });
    history.value = payload.items || [];
  } catch (historyError) {
    history.value = [];
  }
}

async function loadHistoryItem(id) {
  if (!id) return;
  try {
    report.value = await getAiHistoryItem(id);
  } catch (historyItemError) {
    error.value = historyItemError.message || String(historyItemError);
  }
}

onMounted(bootstrap);
</script>

<style scoped>
.ai-workspace {
  box-sizing: border-box;
  display: grid;
  gap: 16px;
  width: 100%;
  min-width: 0;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 22px;
  padding: 18px;
  background: rgba(2, 6, 23, 0.72);
}
.ai-workspace__top,
.ai-workspace__controls,
.ai-workspace__grid,
.ai-workspace__bottom {
  display: grid;
  gap: 14px;
  min-width: 0;
}
.ai-workspace__top {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
}
.ai-workspace h2 {
  margin: 0 0 6px;
  color: #f8fafc;
}
.ai-workspace p {
  margin: 0;
  color: #94a3b8;
}
.ai-workspace__controls {
  grid-template-columns: auto auto auto;
  align-items: end;
}
.ai-workspace__controls label {
  display: grid;
  gap: 6px;
  min-width: 0;
  color: #94a3b8;
  font-size: 13px;
}
.ai-workspace__controls input {
  box-sizing: border-box;
  width: min(140px, 100%);
  min-width: 0;
  border: 1px solid rgba(148, 163, 184, 0.28);
  border-radius: 10px;
  padding: 9px 10px;
  background: rgba(15, 23, 42, 0.9);
  color: #e5eefc;
}
.ai-workspace__controls button {
  min-width: 0;
  border: 0;
  border-radius: 12px;
  padding: 11px 16px;
  background: #2563eb;
  color: white;
  cursor: pointer;
  font-weight: 700;
}
.ai-workspace__controls button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
.ai-workspace__grid {
  grid-template-columns: minmax(280px, 1fr) minmax(300px, 0.9fr);
}
.ai-workspace__agents {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  min-width: 0;
}
.ai-workspace__bottom {
  grid-template-columns: minmax(0, 1fr) 320px;
}
.ai-workspace__error {
  border: 1px solid rgba(239, 68, 68, 0.28);
  border-radius: 12px;
  padding: 10px 12px;
  color: #fecaca !important;
  background: rgba(127, 29, 29, 0.22);
}
@media (max-width: 1100px) {
  .ai-workspace__top,
  .ai-workspace__grid,
  .ai-workspace__bottom,
  .ai-workspace__agents,
  .ai-workspace__controls {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .ai-workspace {
    padding: 12px;
    border-radius: 16px;
  }

  .ai-workspace h2 {
    font-size: 20px;
    line-height: 1.2;
  }
}
</style>
