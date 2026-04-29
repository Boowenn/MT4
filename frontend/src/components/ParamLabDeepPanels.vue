<script setup>
import { computed } from 'vue';
import DataTable from './DataTable.vue';
import EvidenceDrawer from './EvidenceDrawer.vue';
import { arrayFrom, first, money, pct } from '../utils/format';

const props = defineProps({
  mt5: { type: Object, default: () => ({}) },
  tasks: { type: Array, default: () => [] }
});

const scoredRows = computed(() => arrayFrom(props.mt5.paramResults, ['results', 'scoredResults', 'rows']).slice(0, 16));
const recoveryRows = computed(() => arrayFrom(props.mt5.runRecovery, ['runs', 'recoveryRows', 'candidateRisks', 'rows']).slice(0, 16));
</script>

<template>
  <section class="deep-stack">
    <div class="deep-heading">
      <div>
        <p class="eyebrow">ParamLab 深层细节</p>
        <h3>候选队列、评分结果、失败恢复</h3>
      </div>
      <span class="status-chip">tester-only</span>
    </div>

    <DataTable
      title="执行队列"
      :rows="tasks"
      :columns="[
        { label: '候选', value: (r) => first(r.candidateId, r.taskId, r.versionId), width: '230px' },
        { label: '路线', value: (r) => first(r.route, r.strategy, r.symbol), width: '140px' },
        { label: '状态', value: (r) => first(r.state, r.status, r.resultState), width: '150px', badge: true },
        { label: '评分', value: (r) => first(r.score, r.grade, r.profitFactor), width: '90px' },
        { label: '报告/配置', value: (r) => first(r.reportPath, r.report, r.configPath), max: 120 }
      ]"
      empty="暂无 ParamLab 队列。"
    />

    <div class="card-grid">
      <DataTable
        title="评分回灌"
        :rows="scoredRows"
        :columns="[
          { label: '候选', value: (r) => first(r.candidateId, r.versionId), width: '190px' },
          { label: 'PF', value: (r) => first(r.profitFactor, r.pf), width: '80px' },
          { label: '胜率', value: (r) => pct(first(r.winRate, r.win_rate)), width: '90px' },
          { label: '净收益', value: (r) => money(first(r.netProfit, r.net)), width: '100px' },
          { label: '回撤', value: (r) => first(r.maxDrawdown, r.drawdown), width: '100px' }
        ]"
        empty="暂无评分回灌结果。"
      />
      <DataTable
        title="Retry / Failure Drilldown"
        :rows="recoveryRows"
        :columns="[
          { label: '候选', value: (r) => first(r.candidateId, r.versionId, r.runId), width: '190px' },
          { label: '风险', value: (r) => first(r.riskColor, r.color, r.state), width: '90px', badge: true },
          { label: '重试', value: (r) => first(r.retryCount, r.retries, r.waitReportCount), width: '80px' },
          { label: '原因', value: (r) => first(r.failureReason, r.stopReason, r.reason), max: 120 }
        ]"
        empty="暂无失败恢复聚合。"
      />
    </div>

    <div class="drawer-grid">
      <EvidenceDrawer title="ParamLab status raw" :payload="mt5.paramStatus" />
      <EvidenceDrawer title="ParamLab results raw" :payload="mt5.paramResults" />
      <EvidenceDrawer title="Run recovery raw" :payload="mt5.runRecovery" />
    </div>
  </section>
</template>
