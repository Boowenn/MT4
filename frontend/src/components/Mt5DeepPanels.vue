<script setup>
import { computed } from 'vue';
import DataTable from './DataTable.vue';
import EvidenceDrawer from './EvidenceDrawer.vue';
import { arrayFrom, first, money, pct, shortText } from '../utils/format';

const props = defineProps({
  mt5: { type: Object, default: () => ({}) },
  positions: { type: Array, default: () => [] },
  routes: { type: Array, default: () => [] }
});

const backtestRows = computed(() => {
  const source = props.mt5.backtest || {};
  return [
    ...arrayFrom(source, ['results', 'summaries', 'rows']),
    ...arrayFrom(source.summary, ['results', 'summaries'])
  ].slice(0, 12);
});

const runRecoveryRows = computed(() => {
  const source = props.mt5.runRecovery || {};
  return arrayFrom(source, ['runs', 'recoveryRows', 'candidateRisks', 'rows']).slice(0, 12);
});

const registryRows = computed(() => {
  const source = props.mt5.strategyRegistry || {};
  return arrayFrom(source, ['versions', 'strategyVersions', 'registry']).slice(0, 12);
});
</script>

<template>
  <section class="deep-stack">
    <div class="deep-heading">
      <div>
        <p class="eyebrow">MT5 深层细节</p>
        <h3>持仓、路线治理、回测和恢复证据</h3>
      </div>
      <span class="status-chip">只读展示，不改 EA</span>
    </div>

    <DataTable
      title="当前持仓"
      dense
      :rows="positions"
      :columns="[
        { label: '品种', key: ['symbol', 'Symbol'], width: '112px', class: 'col-strong' },
        { label: '方向', key: ['type', 'direction', 'side'], width: '84px', badge: true },
        { label: '手数', value: (r) => first(r.volume, r.lots, r.Volume), width: '74px', class: 'col-number' },
        { label: '开仓价', value: (r) => first(r.price_open, r.openPrice, r.priceOpen), width: '104px', class: 'col-number' },
        { label: '平仓价', value: (r) => first(r.price_current, r.currentPrice, r.price, r.closePrice), width: '104px', class: 'col-number' },
        { label: '浮盈', value: (r) => money(first(r.profit, r.pnl, r.unrealizedPnl)), width: '96px', class: 'col-pnl' },
        { label: '策略/备注', value: (r) => first(r.comment, r.route, r.strategy), max: 120 }
      ]"
      empty="当前没有 MT5 持仓，或只读桥未返回 positions。"
    />

    <DataTable
      title="路线治理"
      dense
      :rows="routes"
      :columns="[
        { label: '路线', value: (r) => first(r.route, r.strategy, r.name, r.versionId), width: '190px' },
        { label: '状态', value: (r) => first(r.currentState, r.state, r.action), width: '130px', badge: true },
        { label: 'PF', value: (r) => first(r.profitFactor, r.pf), width: '80px' },
        { label: '胜率', value: (r) => pct(first(r.winRate, r.win_rate)), width: '90px' },
        { label: '说明', value: (r) => first(r.reason, r.nextAction, r.blocker, r.readiness), max: 120 }
      ]"
      empty="暂无路线治理证据。"
    />

    <div class="card-grid">
      <DataTable
        title="Backtest Lab"
        dense
        :rows="backtestRows"
        :columns="[
          { label: '策略', value: (r) => first(r.strategy, r.route, r.name), width: '150px' },
          { label: '品种', key: ['symbol', 'Symbol'], width: '100px' },
          { label: '状态', value: (r) => first(r.state, r.status), width: '110px', badge: true },
          { label: 'PF', value: (r) => first(r.profitFactor, r.pf), width: '80px' },
          { label: '净值', value: (r) => money(first(r.netProfit, r.net, r.profit)), width: '100px' }
        ]"
        empty="暂无 backtest 结果。"
      />
      <DataTable
        title="Run Recovery"
        dense
        :rows="runRecoveryRows"
        :columns="[
          { label: '候选', value: (r) => first(r.candidateId, r.versionId, r.runId), width: '190px' },
          { label: '风险', value: (r) => first(r.riskColor, r.color, r.state), width: '90px', badge: true },
          { label: '失败原因', value: (r) => first(r.failureReason, r.stopReason, r.reason), max: 110 }
        ]"
        empty="暂无 guarded run recovery。"
      />
    </div>

    <DataTable
      title="策略版本 Registry"
      dense
      :rows="registryRows"
      :columns="[
        { label: '版本', value: (r) => first(r.versionId, r.id), width: '230px' },
        { label: '路线', value: (r) => first(r.route, r.strategy), width: '130px' },
        { label: '权限', value: (r) => first(r.authority, r.state, r.liveState), width: '120px', badge: true },
        { label: '参数', value: (r) => shortText(first(r.paramsText, r.parameters, r.paramSummary), 130) }
      ]"
      empty="暂无策略版本证据。"
    />

    <div class="drawer-grid">
      <EvidenceDrawer title="Governance Advisor raw" :payload="mt5.governance" />
      <EvidenceDrawer title="Backtest Summary raw" :payload="mt5.backtest" />
      <EvidenceDrawer title="Strategy Registry raw" :payload="mt5.strategyRegistry" />
    </div>
  </section>
</template>
