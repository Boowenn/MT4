<script setup>
import { computed } from 'vue';
import BarListChart from './BarListChart.vue';
import SparklineChart from './SparklineChart.vue';
import { arrayFrom, first, shortText } from '../utils/format';

const props = defineProps({
  mt5: { type: Object, default: () => ({}) },
  polymarket: { type: Object, default: () => ({}) },
  routes: { type: Array, default: () => [] },
  positions: { type: Array, default: () => [] },
  paramTasks: { type: Array, default: () => [] },
  radarRows: { type: Array, default: () => [] },
  aiScores: { type: Array, default: () => [] },
  governanceRows: { type: Array, default: () => [] },
  canaryRows: { type: Array, default: () => [] },
  crossRows: { type: Array, default: () => [] },
  workerQueue: { type: Array, default: () => [] }
});

function n(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function pick(row, keys, fallback = '') {
  for (const key of keys) {
    if (row?.[key] !== undefined && row?.[key] !== null && row?.[key] !== '') return row[key];
  }
  return fallback;
}

function rowsFrom(value, keys = []) {
  return arrayFrom(value, keys).filter(Boolean);
}

function countBy(rows, selector) {
  const counts = new Map();
  for (const row of rows) {
    const key = String(selector(row) || '').trim();
    if (!key || key === '--') continue;
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([label, value]) => ({ label, value }));
}

function averageBy(rows, groupSelector, valueSelector) {
  const groups = new Map();
  for (const row of rows) {
    const key = String(groupSelector(row) || '').trim();
    const value = n(valueSelector(row));
    if (!key || value === null) continue;
    const group = groups.get(key) || { total: 0, count: 0 };
    group.total += value;
    group.count += 1;
    groups.set(key, group);
  }
  return [...groups.entries()]
    .map(([label, group]) => ({ label, value: group.total / group.count, detail: `${group.count} 样本` }))
    .sort((a, b) => {
      const numA = Number(a.label);
      const numB = Number(b.label);
      if (Number.isFinite(numA) && Number.isFinite(numB)) return numA - numB;
      return Math.abs(b.value) - Math.abs(a.value);
    });
}

function latestNumbers(rows, keys, limit = 36) {
  return rows
    .map((row) => {
      for (const key of keys) {
        const value = n(row?.[key]);
        if (value !== null) return value;
      }
      return null;
    })
    .filter((value) => value !== null)
    .slice(-limit);
}

const mt5Ledgers = computed(() => props.mt5?.ledgers || {});
const polyLedgers = computed(() => props.polymarket?.ledgers || {});

const shadowSignals = computed(() => rowsFrom(mt5Ledgers.value.shadowSignals));
const shadowOutcomes = computed(() => rowsFrom(mt5Ledgers.value.shadowOutcomes));
const shadowCandidates = computed(() => rowsFrom(mt5Ledgers.value.shadowCandidates));
const shadowCandidateOutcomes = computed(() => rowsFrom(mt5Ledgers.value.shadowCandidateOutcomes));
const paramLabResults = computed(() => rowsFrom(mt5Ledgers.value.paramLabResults));

const radarLedger = computed(() => rowsFrom(polyLedgers.value.radar).length ? rowsFrom(polyLedgers.value.radar) : props.radarRows);
const aiScoreLedger = computed(() => rowsFrom(polyLedgers.value.aiScores).length ? rowsFrom(polyLedgers.value.aiScores) : props.aiScores);
const canaryLedger = computed(() => rowsFrom(polyLedgers.value.canary).length ? rowsFrom(polyLedgers.value.canary) : props.canaryRows);
const autoGovLedger = computed(() => rowsFrom(polyLedgers.value.autoGovernance).length ? rowsFrom(polyLedgers.value.autoGovernance) : props.governanceRows);
const crossLedger = computed(() => rowsFrom(polyLedgers.value.cross).length ? rowsFrom(polyLedgers.value.cross) : props.crossRows);

const mt5Summary = computed(() => [
  { label: 'Shadow 信号', value: shadowSignals.value.length, detail: 'spread/session/range blocker' },
  { label: 'Outcome 后验', value: shadowOutcomes.value.length, detail: '15/30/60 分钟' },
  { label: 'Candidate 候选', value: shadowCandidates.value.length, detail: 'shadow-only 路线' },
  { label: 'ParamLab 结果', value: paramLabResults.value.length || props.paramTasks.length, detail: 'tester-only 队列' }
]);

const shadowBlockerItems = computed(() => countBy(
  shadowSignals.value,
  (row) => pick(row, ['Blocker', 'blocker', 'SignalStatus', 'signalStatus'], 'UNKNOWN')
));

const shadowActionItems = computed(() => countBy(
  shadowSignals.value,
  (row) => pick(row, ['ExecutionAction', 'executionAction', 'SignalStatus'], 'UNKNOWN')
));

const candidateRouteItems = computed(() => countBy(
  shadowCandidates.value,
  (row) => pick(row, ['CandidateRoute', 'candidateRoute', 'Strategy', 'strategy'], 'UNKNOWN')
));

const candidateOutcomeItems = computed(() => countBy(
  shadowCandidateOutcomes.value,
  (row) => pick(row, ['BestOpportunity', 'DirectionalOutcome', 'CandidateRoute'], 'UNKNOWN')
));

const horizonLongItems = computed(() => averageBy(
  shadowOutcomes.value,
  (row) => pick(row, ['HorizonMinutes', 'horizonMinutes'], '--'),
  (row) => pick(row, ['LongClosePips', 'longClosePips'])
).map((item) => ({ ...item, label: `${item.label}m LONG` })));

const horizonShortItems = computed(() => averageBy(
  shadowOutcomes.value,
  (row) => pick(row, ['HorizonMinutes', 'horizonMinutes'], '--'),
  (row) => pick(row, ['ShortClosePips', 'shortClosePips'])
).map((item) => ({ ...item, label: `${item.label}m SHORT` })));

const mfeMaePoints = computed(() => shadowOutcomes.value
  .map((row) => {
    const mfe = n(pick(row, ['LongMFEPips', 'ShortMFEPips']));
    const mae = n(pick(row, ['LongMAEPips', 'ShortMAEPips']));
    return mfe !== null && mae !== null ? mfe - mae : null;
  })
  .filter((value) => value !== null)
  .slice(-42));

const paramScorePoints = computed(() => latestNumbers(
  paramLabResults.value.length ? paramLabResults.value : props.paramTasks,
  ['ResultScore', 'score', 'ProfitFactor', 'profitFactor'],
  36
));

const radarScoreItems = computed(() => radarLedger.value
  .map((row) => ({
    label: shortText(first(row.question, row.market, row.title, row.slug, row.market_id), 42),
    value: n(pick(row, ['ai_rule_score', 'aiRuleScore', 'rule_score', 'score'])) ?? 0,
    detail: `概率 ${first(row.probability, '--')} · 流动性 ${first(row.liquidity, row.clob_liquidity_usd, '--')}`
  }))
  .sort((a, b) => b.value - a.value));

const aiScorePoints = computed(() => latestNumbers(aiScoreLedger.value, ['score', 'history_feature_score', 'semantic_score'], 36));

const probabilityPoints = computed(() => latestNumbers(radarLedger.value, ['probability'], 36));

const canaryStateItems = computed(() => countBy(
  canaryLedger.value,
  (row) => pick(row, ['canary_state', 'canaryState', 'decision'], 'UNKNOWN')
));

const autoGovActionItems = computed(() => countBy(
  autoGovLedger.value,
  (row) => pick(row, ['governance_state', 'governanceState', 'recommended_action', 'recommendedAction'], 'UNKNOWN')
));

const crossRiskItems = computed(() => countBy(
  crossLedger.value,
  (row) => pick(row, ['risk_tag', 'riskTag', 'assetSymbol', 'tag', 'category'], 'UNKNOWN')
));
</script>

<template>
  <section class="stack">
    <div class="toolbar">
      <div>
        <p class="eyebrow">Charts & Trends</p>
        <h2>图表与趋势可视化</h2>
        <p class="muted">从旧单文件页面迁出的只读图表层：MT5 shadow/outcome、ParamLab、Polymarket radar/AI/canary 都在这里集中复盘。</p>
      </div>
      <span class="status-chip locked">只读迁移层</span>
    </div>

    <div class="metric-grid four">
      <div v-for="item in mt5Summary" :key="item.label" class="metric">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
        <small>{{ item.detail }}</small>
      </div>
    </div>

    <div class="viz-grid">
      <BarListChart title="Shadow blocker 分布" subtitle="MT5 Shadow Ledger" :items="shadowBlockerItems" value-label="拦截次数" />
      <BarListChart title="Shadow 执行动作" subtitle="MT5 Shadow Ledger" :items="shadowActionItems" value-label="样本数" />
      <BarListChart title="Candidate 路线速度" subtitle="Shadow Candidate" :items="candidateRouteItems" value-label="候选数" />
      <BarListChart title="Candidate 后验方向" subtitle="Candidate Outcome" :items="candidateOutcomeItems" value-label="后验样本" />
      <BarListChart title="Outcome 15/30/60 LONG" subtitle="平均 close pips" :items="horizonLongItems" value-label="pips" />
      <BarListChart title="Outcome 15/30/60 SHORT" subtitle="平均 close pips" :items="horizonShortItems" value-label="pips" />
      <SparklineChart title="MFE - MAE 近期曲线" subtitle="Shadow Outcome" :points="mfeMaePoints" unit="p" :precision="1" tone="green" />
      <SparklineChart title="ParamLab 分数/PF 趋势" subtitle="Tester-only 结果" :points="paramScorePoints" :precision="2" tone="amber" />
      <BarListChart title="Polymarket 雷达评分" subtitle="Gamma/Radar" :items="radarScoreItems" value-label="score" />
      <SparklineChart title="Polymarket AI score" subtitle="History-aware score" :points="aiScorePoints" :precision="1" tone="blue" />
      <SparklineChart title="市场概率样本" subtitle="Radar probability" :points="probabilityPoints" unit="%" :precision="1" tone="amber" />
      <BarListChart title="Canary 状态分布" subtitle="Execution Gate" :items="canaryStateItems" value-label="contract" />
      <BarListChart title="自动治理动作" subtitle="Polymarket Governance" :items="autoGovActionItems" value-label="market" />
      <BarListChart title="跨市场风险标签" subtitle="USD/JPY/XAU/Macro linkage" :items="crossRiskItems" value-label="link" />
    </div>
  </section>
</template>
