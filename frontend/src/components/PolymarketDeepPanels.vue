<script setup>
import { computed } from 'vue';
import DataTable from './DataTable.vue';
import EvidenceDrawer from './EvidenceDrawer.vue';
import { arrayFrom, first, money, pct } from '../utils/format';

const props = defineProps({
  polymarket: { type: Object, default: () => ({}) },
  radarRows: { type: Array, default: () => [] },
  searchGroups: { type: Array, default: () => [] },
  aiScores: { type: Array, default: () => [] },
  governanceRows: { type: Array, default: () => [] },
  canaryRows: { type: Array, default: () => [] },
  crossRows: { type: Array, default: () => [] },
  workerQueue: { type: Array, default: () => [] }
});

const historyRows = computed(() => {
  const source = props.polymarket.history || {};
  return [
    ...arrayFrom(source, ['rows', 'recent']),
    ...arrayFrom(source.recent, ['analyses', 'opportunities', 'simulations', 'workerQueue'])
  ].slice(0, 12);
});
</script>

<template>
  <section class="deep-stack">
    <div class="deep-heading">
      <div>
        <p class="eyebrow">Polymarket 深层细节</p>
        <h3>雷达、AI、canary、治理、跨市场联动</h3>
      </div>
      <span class="status-chip locked">默认不写钱包</span>
    </div>

    <DataTable
      title="机会雷达"
      :rows="radarRows"
      :columns="[
        { label: '市场', value: (r) => first(r.market, r.title, r.question, r.slug), max: 82 },
        { label: '概率', value: (r) => pct(first(r.probability, r.marketProbability)), width: '90px' },
        { label: '量', value: (r) => money(first(r.volume, r.volumeUsd)), width: '110px' },
        { label: '流动性', value: (r) => money(first(r.liquidity, r.liquidityUsd, r.clobLiquidityUsd)), width: '120px' },
        { label: '评分', value: (r) => first(r.aiRuleScore, r.score), width: '90px', badge: true }
      ]"
      empty="暂无 radar 快照。"
    />

    <div class="card-grid">
      <DataTable
        title="AI 评分"
        :rows="aiScores"
        :columns="[
          { label: '市场', value: (r) => first(r.market, r.title, r.question, r.marketId), max: 70 },
          { label: '评分', value: (r) => first(r.score, r.aiScore), width: '80px', badge: true },
          { label: '动作', value: (r) => first(r.action, r.recommendation), width: '120px' },
          { label: '风险', value: (r) => first(r.risk, r.riskLevel, r.color), width: '100px' }
        ]"
        empty="暂无 AI score。"
      />
      <DataTable
        title="Worker V2 队列"
        :rows="workerQueue"
        :columns="[
          { label: '候选', value: (r) => first(r.candidateId, r.marketId), width: '190px' },
          { label: '评分', value: (r) => first(r.aiRuleScore, r.score), width: '80px' },
          { label: '轨道', value: (r) => first(r.suggestedShadowTrack, r.executionMode, r.category), max: 110 }
        ]"
        empty="暂无 worker 队列。"
      />
    </div>

    <div class="card-grid">
      <DataTable
        title="Canary 契约"
        :rows="canaryRows"
        :columns="[
          { label: '合约', value: (r) => first(r.canaryContractId, r.marketId), width: '190px' },
          { label: '状态', value: (r) => first(r.canaryState, r.decision), width: '120px', badge: true },
          { label: '金额', value: (r) => money(first(r.canaryStakeUSDC, r.stake)), width: '90px' },
          { label: '阻断', value: (r) => first(r.blockers?.join?.(', '), r.blocker), max: 120 }
        ]"
        empty="暂无 canary 契约。"
      />
      <DataTable
        title="自动治理"
        :rows="governanceRows"
        :columns="[
          { label: '治理 ID', value: (r) => first(r.governanceId, r.marketId), width: '190px' },
          { label: '建议', value: (r) => first(r.decision, r.currentState), width: '150px', badge: true },
          { label: '可执行', value: (r) => first(r.canPromoteToLiveExecution, r.autoExecutorPermission), width: '90px' },
          { label: '原因', value: (r) => first(r.reason, r.blockers?.join?.(', ')), max: 120 }
        ]"
        empty="暂无 auto governance。"
      />
    </div>

    <DataTable
      title="跨市场风险联动"
      :rows="crossRows"
      :columns="[
        { label: '事件', value: (r) => first(r.eventTitle, r.market, r.marketId), max: 92 },
        { label: '标签', value: (r) => first(r.primaryRiskTag, r.macroRiskState, r.category), width: '150px', badge: true },
        { label: '关联品种', value: (r) => first(r.linkedMt5Symbols?.join?.(', '), r.symbols), width: '150px' },
        { label: '信心', value: (r) => pct(first(r.confidence, r.score)), width: '90px' },
        { label: '说明', value: (r) => first(r.reason, r.matchedKeywords?.join?.(', ')), max: 120 }
      ]"
      empty="暂无跨市场联动证据。"
    />

    <DataTable
      title="历史库最近证据"
      :rows="historyRows"
      :columns="[
        { label: '类型', value: (r) => first(r.source, r.tableName, r.type), width: '140px', badge: true },
        { label: '市场', value: (r) => first(r.marketTitle, r.title, r.question, r.marketId), max: 92 },
        { label: '结论', value: (r) => first(r.decision, r.recommendation, r.action, r.state), width: '150px' },
        { label: '时间', value: (r) => first(r.generatedAt, r.createdAt, r.updatedAt), width: '180px' }
      ]"
      empty="暂无历史库行。"
    />

    <div class="drawer-grid">
      <EvidenceDrawer title="Polymarket search raw" :payload="polymarket.search" />
      <EvidenceDrawer title="Radar worker raw" :payload="polymarket.worker" />
      <EvidenceDrawer title="Canary contract raw" :payload="polymarket.canary" />
      <EvidenceDrawer title="Auto governance raw" :payload="polymarket.autoGovernance" />
    </div>
  </section>
</template>
