<script setup>
import { computed } from 'vue';
import DataTable from './DataTable.vue';
import EvidenceDrawer from './EvidenceDrawer.vue';
import { arrayFrom, first, money, pct } from '../utils/format';

const props = defineProps({
  mt5: { type: Object, default: () => ({}) },
  tasks: { type: Array, default: () => [] },
  autoSchedulerRows: { type: Array, default: () => [] },
  reportWatcherRows: { type: Array, default: () => [] },
  runRecoveryRows: { type: Array, default: () => [] },
  autoTesterRows: { type: Array, default: () => [] },
  researchRows: { type: Array, default: () => [] }
});

const scoredRows = computed(() => arrayFrom(props.mt5.paramResults, ['results', 'scoredResults', 'rows']).slice(0, 16));
const recoveryRows = computed(() => (props.runRecoveryRows.length
  ? props.runRecoveryRows
  : arrayFrom(props.mt5.runRecovery, ['candidateDrilldown', 'recoveryQueue', 'runs', 'recoveryRows', 'candidateRisks', 'rows'])).slice(0, 16));

const autoSchedulerRows = computed(() => (props.autoSchedulerRows.length
  ? props.autoSchedulerRows
  : [
      ...arrayFrom(props.mt5.paramAutoScheduler, ['selectedTasks']),
      ...arrayFrom(props.mt5.paramAutoScheduler, ['backtestTasks'])
    ]).slice(0, 16));

const reportWatcherRows = computed(() => (props.reportWatcherRows.length
  ? props.reportWatcherRows
  : arrayFrom(props.mt5.paramReportWatcher, ['watchedResults', 'reportFiles', 'rows'])).slice(0, 16));

const autoTesterRows = computed(() => (props.autoTesterRows.length
  ? props.autoTesterRows
  : [
      ...arrayFrom(props.mt5.autoTesterWindow, ['selectedTasks']),
      ...arrayFrom(props.mt5.autoTesterWindow, ['excludedTasks'])
    ]).slice(0, 16));

const researchRows = computed(() => (props.researchRows.length
  ? props.researchRows
  : arrayFrom(props.mt5.mt5ResearchStats, ['rows'])).slice(0, 16));
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
        title="Auto Scheduler 安全队列"
        :rows="autoSchedulerRows"
        :columns="[
          { label: '候选', value: (r) => first(r.candidateId, r.versionId, r.taskId), width: '210px' },
          { label: '路线', value: (r) => first(r.route, r.strategy, r.symbol), width: '130px' },
          { label: '触发', value: (r) => first(r.gateDecision, r.reason, r.queueReason, r.state), width: '160px', badge: true },
          { label: '命令', value: (r) => first(r.command, r.testerOnlyCommand, r.configPath), max: 140 }
        ]"
        empty="暂无 Auto Scheduler 队列。"
      />
      <DataTable
        title="Report Watcher 回灌"
        :rows="reportWatcherRows"
        :columns="[
          { label: '候选', value: (r) => first(r.candidateId, r.versionId, r.taskId), width: '210px' },
          { label: '状态', value: (r) => first(r.resultState, r.state, r.status, r.matchType), width: '120px', badge: true },
          { label: 'PF', value: (r) => first(r.profitFactor, r.pf), width: '80px' },
          { label: '报告', value: (r) => first(r.reportPath, r.path, r.source), max: 150 }
        ]"
        empty="暂无 Report Watcher 记录。"
      />
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
      <DataTable
        title="AUTO_TESTER_WINDOW 守护"
        :rows="autoTesterRows"
        :columns="[
          { label: '候选', value: (r) => first(r.candidateId, r.versionId, r.taskId), width: '210px' },
          { label: '状态', value: (r) => first(r.gateState, r.state, r.status, r.reason), width: '150px', badge: true },
          { label: '路线', value: (r) => first(r.route, r.strategy, r.symbol), width: '130px' },
          { label: '阻断/备注', value: (r) => first(r.blocker, r.stopReason, r.reason, r.excludedReason), max: 140 }
        ]"
        empty="暂无守护窗口任务。"
      />
      <DataTable
        title="MT5 闭环研究统计"
        :rows="researchRows"
        :columns="[
          { label: '路线', value: (r) => first(r.route, r.Route, r.strategy), width: '160px' },
          { label: '品种', value: (r) => first(r.canonicalSymbol, r.symbol, r.Symbol), width: '110px' },
          { label: 'Regime', value: (r) => first(r.marketRegime, r.regime, r.Regime), width: '130px' },
          { label: '样本', value: (r) => first(r.closedTrades, r.samples, r.tradeCount), width: '80px' },
          { label: 'PF / Win', value: (r) => `${first(r.profitFactor, r.pf, '--')} / ${pct(first(r.winRate, r.winRatePct))}`, width: '120px' },
          { label: '状态', value: (r) => first(r.state, r.status, r.recommendation), badge: true }
        ]"
        empty="暂无 MT5 研究切片。"
      />
    </div>

    <div class="drawer-grid">
      <EvidenceDrawer title="ParamLab status raw" :payload="mt5.paramStatus" />
      <EvidenceDrawer title="ParamLab results raw" :payload="mt5.paramResults" />
      <EvidenceDrawer title="Auto scheduler raw" :payload="mt5.paramAutoScheduler" />
      <EvidenceDrawer title="Report watcher raw" :payload="mt5.paramReportWatcher" />
      <EvidenceDrawer title="Run recovery raw" :payload="mt5.runRecovery" />
      <EvidenceDrawer title="Auto tester window raw" :payload="mt5.autoTesterWindow" />
    </div>
  </section>
</template>
