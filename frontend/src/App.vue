<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';
import {
  Activity,
  BarChart3,
  ClipboardList,
  Gauge,
  LineChart,
  Network,
  RefreshCw,
  Search,
  ShieldCheck,
  Target,
  TrendingUp,
  WalletCards
} from 'lucide-vue-next';
import { loadDashboardState, submitPolymarketRequest } from './services/api';
import Mt5DeepPanels from './components/Mt5DeepPanels.vue';
import ParamLabDeepPanels from './components/ParamLabDeepPanels.vue';
import PolymarketDeepPanels from './components/PolymarketDeepPanels.vue';
import TrendVisuals from './components/TrendVisuals.vue';
import DataTable from './components/DataTable.vue';
import EvidenceDrawer from './components/EvidenceDrawer.vue';

const workspaces = [
  { id: 'home', label: '总控台', sub: '机会雷达', icon: Gauge, desc: 'MT5、ParamLab 与 Polymarket 的统一只读操作台' },
  { id: 'mt5', label: 'MT5 策略', sub: '实盘监控', icon: LineChart, desc: '路线、持仓、风控、手动样本与 EA 审计' },
  { id: 'polymarket', label: 'Polymarket', sub: '研究治理', icon: Network, desc: '市场雷达、AI 评分、小额哨兵契约与历史证据' },
  { id: 'paramlab', label: '参数实验', sub: '回测队列', icon: ClipboardList, desc: 'tester-only 队列、报告回灌、恢复风险与守护窗口' },
  { id: 'charts', label: '趋势图表', sub: '可视化', icon: TrendingUp, desc: '路线趋势、样本速度、ParamLab 与 Polymarket 图表' },
  { id: 'reports', label: '证据报表', sub: '审计总览', icon: BarChart3, desc: '统一文件/API 新鲜度与核心 ledger 表格' }
];

const state = reactive({
  active: 'home',
  mt5Focus: 'overview',
  polymarketFocus: 'overview',
  loading: false,
  loadedAt: '',
  error: '',
  query: '',
  marketInput: '',
  requestStatus: '',
  data: {
    mt5: {},
    polymarket: {}
  }
});

const routeFilters = ['全部', 'MA', 'RSI', 'BB', 'MACD', 'SR'];
const activeRoute = ref('全部');
const paramTaskFilter = ref('全部');
const paramRouteFilter = ref('全部');
const paramSortMode = ref('优先级');

const mt5WorkspaceIds = new Set(['mt5', 'paramlab', 'charts', 'reports']);
const mt5DefaultFocus = {
  mt5: 'overview',
  paramlab: 'paramlab',
  charts: 'monitor',
  reports: 'reports'
};

const mt5NavItems = [
  { id: 'mt5', focus: 'overview', label: 'AI 总览', sub: '总览雷达', icon: Gauge },
  { id: 'mt5', focus: 'strategy', label: '策略实盘', sub: '路线与风控', icon: LineChart },
  { id: 'charts', focus: 'monitor', label: '趋势图表', sub: '品种监控', icon: TrendingUp },
  { id: 'paramlab', focus: 'paramlab', label: '参数实验', sub: '回测闭环', icon: ClipboardList },
  { id: 'mt5', focus: 'trades', label: '交易只读', sub: 'EA 与人工单', icon: Activity },
  { id: 'reports', focus: 'reports', label: '证据报表', sub: '审计总览', icon: BarChart3 }
];

const polymarketNavItems = [
  { id: 'polymarket', focus: 'overview', label: '治理总览', sub: '账户与边界', icon: Network },
  { id: 'polymarket', focus: 'browser', label: '市场浏览', sub: '目录 / 详情', icon: ClipboardList },
  { id: 'polymarket', focus: 'radar', label: '机会雷达', sub: 'Gamma 扫描', icon: Target },
  { id: 'polymarket', focus: 'analysis', label: '单市场分析', sub: 'URL/标题入口', icon: Search },
  { id: 'polymarket', focus: 'execution', label: '执行模拟', sub: 'Gate / dry-run', icon: WalletCards },
  { id: 'polymarket', focus: 'ledger', label: '重调账本', sub: '样本与日志', icon: BarChart3 }
];

const routeDisplayMap = {
  MA_CROSS: 'MA',
  RSI_REVERSAL: 'RSI',
  BB_TRIPLE: 'BB',
  MACD_DIVERGENCE: 'MACD',
  SR_BREAKOUT: 'SR'
};

function normalizeWorkspace(id) {
  return workspaces.some((item) => item.id === id) ? id : 'home';
}

function syncActiveFromHash() {
  const hash = window.location.hash.replace(/^#\/?/, '');
  state.active = normalizeWorkspace(hash || 'home');
  if (workspaceDomainFor(state.active) === 'mt5') {
    state.mt5Focus = mt5DefaultFocus[state.active] || state.mt5Focus || 'overview';
  }
  if (state.active === 'polymarket') {
    state.polymarketFocus = state.polymarketFocus || 'overview';
  }
}

function workspaceDomainFor(id) {
  if (id === 'polymarket') return 'polymarket';
  if (mt5WorkspaceIds.has(id)) return 'mt5';
  return 'home';
}

function setActive(id, focus = '') {
  state.active = normalizeWorkspace(id);
  if (workspaceDomainFor(state.active) === 'mt5') {
    state.mt5Focus = focus || mt5DefaultFocus[state.active] || state.mt5Focus || 'overview';
  }
  if (state.active === 'polymarket' && focus) {
    state.polymarketFocus = focus;
  }
  const nextHash = state.active === 'home' ? '' : `#${state.active}`;
  if (window.location.hash !== nextHash) {
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}${nextHash}`);
  }
}

function navItemActive(item) {
  if (item.focus) {
    if (item.id === 'polymarket') return state.active === item.id && state.polymarketFocus === item.focus;
    return state.active === item.id && state.mt5Focus === item.focus;
  }
  return state.active === item.id;
}

function arrayFrom(value, keys = []) {
  if (Array.isArray(value)) return value;
  for (const key of keys) {
    if (Array.isArray(value?.[key])) return value[key];
  }
  return [];
}

function first(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== '') ?? '--';
}

function asNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function money(value) {
  const n = asNumber(value);
  return n === null ? '--' : `$${n.toFixed(2)}`;
}

function pct(value) {
  const n = asNumber(value);
  if (n === null) return '--';
  const normalized = Math.abs(n) <= 1 ? n * 100 : n;
  return `${normalized.toFixed(1)}%`;
}

function shortText(value, max = 120) {
  const text = String(first(value, '')).replace(/\s+/g, ' ').trim();
  if (!text) return '--';
  return text.length > max ? `${text.slice(0, max - 1)}...` : text;
}

function routeName(row) {
  return String(first(row?.key, row?.route, row?.strategy, row?.strategyName, row?.name, row?.candidateId, '')).toUpperCase();
}

function routeShortName(row) {
  const name = routeName(row);
  return Object.entries(routeDisplayMap).find(([key]) => name.includes(key))?.[1] || first(row?.strategy, row?.route, row?.key, '--');
}

function routeActionLabel(row) {
  return first(row?.feedback?.actionLabel, row?.recommendedAction, row?.currentState, row?.state, row?.mode, '观察');
}

function routeBlockerText(row) {
  const blockers = row?.blockers || row?.paramLabResult?.blockers || row?.feedback?.riskAreas;
  if (Array.isArray(blockers)) return blockers.slice(0, 3).join(' / ') || '暂无 blocker';
  return first(blockers, row?.blocker, '暂无 blocker');
}

function routeWhyText(row) {
  const why = row?.feedback?.why;
  if (Array.isArray(why) && why.length) return why.slice(0, 2).join(' ');
  return first(row?.feedback?.nextStep, row?.nextAction, row?.reason, routeBlockerText(row));
}

function routeParamText(row) {
  return shortText(
    first(
      row?.paramOptimization?.candidateId,
      row?.paramLab?.candidateId,
      row?.paramLabResult?.candidateId,
      row?.candidateRoute,
      '等待候选'
    ),
    64
  );
}

function routeToneClass(row) {
  const action = String(first(row?.recommendedAction, row?.mode, row?.tone, '')).toUpperCase();
  if (action.includes('LIVE') || action.includes('KEEP_LIVE')) return 'green';
  if (action.includes('RETUNE') || action.includes('DEMOTE')) return 'amber';
  if (action.includes('SIM') || action.includes('CANDIDATE')) return 'blue';
  return '';
}

function normalizeParamState(row) {
  return String(first(row?.state, row?.status, row?.resultState, row?.grade, row?.queueState, row?.riskColor, '')).toUpperCase();
}

function paramRowText(row) {
  return [
    normalizeParamState(row),
    row?.candidateId,
    row?.versionId,
    row?.taskId,
    row?.route,
    row?.strategy,
    row?.symbol,
    row?.failureReason,
    row?.stopReason,
    row?.reason,
    row?.reportPath,
    row?.configPath,
    row?.riskColor,
    row?.color
  ].filter(Boolean).join(' ').toUpperCase();
}

function paramRouteLabel(row) {
  const text = paramRowText(row);
  const route = Object.entries(routeDisplayMap).find(([needle]) => text.includes(needle))?.[1];
  if (route) return route;
  if (text.includes('MA_') || text.includes('MA CROSS') || text.includes('MA-CROSS')) return 'MA';
  if (text.includes('RSI')) return 'RSI';
  if (text.includes('BB') || text.includes('BOLLINGER')) return 'BB';
  if (text.includes('MACD')) return 'MACD';
  if (text.includes('SR_') || text.includes('BREAKOUT')) return 'SR';
  return '其他';
}

function paramMatchesFilter(row, filter) {
  if (filter === '全部') return true;
  const text = paramRowText(row);
  if (filter === '等待报告') return text.includes('WAIT') || text.includes('PENDING_REPORT') || text.includes('REPORT');
  if (filter === '已评分') return text.includes('SCORED') || text.includes('PARSED') || text.includes('PROMOTION') || text.includes('GRADE');
  if (filter === '可运行') return text.includes('CONFIG_READY') || text.includes('RUN_PENDING') || text.includes('READY');
  if (filter === '红灯') return text.includes('RED') || text.includes('EXHAUSTED') || text.includes('MALFORMED');
  if (filter === '黄灯') return text.includes('YELLOW') || text.includes('WAIT') || text.includes('RETRY');
  return true;
}

function paramMatchesRoute(row, filter) {
  return filter === '全部' || paramRouteLabel(row) === filter;
}

function paramTaskScore(row) {
  return asNumber(first(row?.score, row?.grade, row?.resultScore, row?.profitFactor, row?.pf)) ?? Number.NEGATIVE_INFINITY;
}

function paramTaskTime(row) {
  const value = first(row?.updatedAt, row?.generatedAt, row?.createdAt, row?.time, row?.timestamp, row?.lastSeenAt, '');
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function paramTaskPriority(row) {
  const text = paramRowText(row);
  if (text.includes('RED') || text.includes('EXHAUSTED') || text.includes('MALFORMED')) return 0;
  if (text.includes('CONFIG_READY') || text.includes('RUN_PENDING') || text.includes('READY')) return 1;
  if (text.includes('WAIT') || text.includes('PENDING_REPORT') || text.includes('REPORT')) return 2;
  if (text.includes('RETUNE') || text.includes('QUARANTINE')) return 3;
  if (text.includes('PARSED') || text.includes('SCORED') || text.includes('GRADE')) return 4;
  return 5;
}

function sortParamTasks(rows, mode) {
  return [...rows].sort((a, b) => {
    if (mode === '评分高') return paramTaskScore(b) - paramTaskScore(a);
    if (mode === '最近') return paramTaskTime(b) - paramTaskTime(a);
    if (mode === '路线') return paramRouteLabel(a).localeCompare(paramRouteLabel(b));
    return paramTaskPriority(a) - paramTaskPriority(b)
      || paramRouteLabel(a).localeCompare(paramRouteLabel(b))
      || paramTaskTime(b) - paramTaskTime(a);
  });
}

function summaryValue(payload, key, fallback = '--') {
  return first(payload?.summary?.[key], payload?.[key], fallback);
}

function nextWindowLabel(minutes) {
  const now = new Date();
  const next = new Date(now);
  if (minutes >= 60) {
    next.setHours(now.getHours() + 1, 0, 0, 0);
  } else {
    const nextMinute = Math.ceil((now.getMinutes() + 1) / minutes) * minutes;
    next.setMinutes(nextMinute, 0, 0);
  }
  return next.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
}

async function refresh() {
  state.loading = true;
  state.error = '';
  try {
    state.data = await loadDashboardState(state.query);
    state.loadedAt = new Date().toLocaleString('zh-CN', { hour12: false });
  } catch (error) {
    state.error = error.message || String(error);
  } finally {
    state.loading = false;
  }
}

async function submitSingleMarket() {
  const raw = state.marketInput.trim();
  if (!raw) {
    state.requestStatus = '请输入 Polymarket URL、标题或 marketId';
    return;
  }
  state.requestStatus = '正在生成研究请求...';
  const payload = raw.startsWith('http')
    ? { url: raw, source: 'vue_workbench' }
    : { query: raw, title: raw, source: 'vue_workbench' };
  const result = await submitPolymarketRequest(payload);
  state.requestStatus = result?.ok ? '已生成单市场研究请求' : `生成失败：${first(result?.error, 'unknown')}`;
  await refresh();
}

const mt5 = computed(() => state.data.mt5 || {});
const poly = computed(() => state.data.polymarket || {});

const mt5Account = computed(() => {
  const snap = mt5.value.snapshot || {};
  return snap.account || snap.snapshot?.account || mt5.value.latest?.account || {};
});

const mt5Positions = computed(() => {
  const snap = mt5.value.snapshot || {};
  return arrayFrom(snap.positions, ['positions', 'openPositions'])
    .concat(arrayFrom(snap.snapshot?.positions, ['positions']))
    .concat(arrayFrom(mt5.value.latest?.positions, ['positions']));
});

const allMt5Routes = computed(() => {
  const gov = mt5.value.governance || {};
  const registry = mt5.value.strategyRegistry || {};
  const rows = [
    ...arrayFrom(gov, ['governanceDecisions', 'routeDecisions', 'routes', 'strategyRoutes']),
    ...arrayFrom(registry, ['versions', 'strategyVersions', 'registry'])
  ];
  const seen = new Set();
  return rows.filter((row) => {
    const key = first(row?.route, row?.strategy, row?.versionId, row?.name);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
});

const mt5Routes = computed(() => {
  return allMt5Routes.value
    .filter((row) => activeRoute.value === '全部' || routeName(row).includes(activeRoute.value))
    .slice(0, 10);
});

const mt5ExecutionRadarItems = computed(() => {
  const snap = mt5.value.snapshot || {};
  const latest = mt5.value.latest || {};
  const account = mt5Account.value;
  const route = primaryRoute.value;
  const news = first(latest.newsStatus, snap.newsStatus, snap.calendar?.status, '等待日历');
  return [
    {
      label: '运行状态',
      value: first(snap.status, snap.ok === true ? '已连接' : '未连接'),
      sub: first(snap.mode, snap.permissions?.mode, latest.mode, '只读监控')
    },
    {
      label: '服务器时钟',
      value: shortText(first(snap.serverTime, snap.serverTimeIso, latest.serverTime, '--'), 18),
      sub: `本地 ${first(state.loadedAt, '--')}`
    },
    {
      label: '行情新鲜度',
      value: first(snap.tickAgeSeconds, latest.tickAgeSeconds, latest.tickAge, '--'),
      sub: `点差 ${first(snap.spread, latest.spread, latest.spreadPoints, '--')}`
    },
    {
      label: '仓位容量',
      value: `${mt5Positions.value.length}/${first(snap.maxTotalPositions, snap.risk?.maxTotalPositions, latest.maxTotalPositions, 1)}`,
      sub: `净值 ${money(first(account.equity, latest.equity))}`
    },
    {
      label: 'M15 评估窗口',
      value: nextWindowLabel(15),
      sub: 'MA / SR / 短周期候选'
    },
    {
      label: 'H1 评估窗口',
      value: nextWindowLabel(60),
      sub: 'RSI / BB / MACD'
    },
    {
      label: '机会焦点',
      value: shortText(first(route.label, route.route, route.strategy, '等待机会'), 22),
      sub: routeActionLabel(route)
    },
    {
      label: '阻塞摘要',
      value: shortText(routeBlockerText(route), 24),
      sub: first(route.feedback?.riskLevel, route.riskLevel, '等待信号')
    },
    {
      label: 'USD 新闻过滤',
      value: news,
      sub: first(snap.calendar?.blocker, latest.newsBlocker, '无新增高危新闻')
    },
    {
      label: '下一条新闻',
      value: shortText(first(snap.nextNewsEvent, latest.nextNewsEvent, '--'), 22),
      sub: first(snap.nextNewsTime, latest.nextNewsTime, '服务器时间 --')
    }
  ];
});

const rawParamTasks = computed(() => {
  const status = mt5.value.paramStatus || {};
  const results = mt5.value.paramResults || {};
  const scheduler = mt5.value.paramAutoScheduler || {};
  const watcher = mt5.value.paramReportWatcher || {};
  return [
    ...arrayFrom(status, ['tasks', 'queue', 'candidates', 'batch']),
    ...arrayFrom(results, ['results', 'scoredResults']),
    ...arrayFrom(scheduler, ['selectedTasks', 'backtestTasks']),
    ...arrayFrom(watcher, ['watchedResults', 'reportFiles'])
  ].slice(0, 80);
});

const paramTasks = computed(() => rawParamTasks.value.slice(0, 12));

const paramFilterOptions = computed(() => ['全部', '等待报告', '已评分', '可运行', '红灯', '黄灯'].map((filter) => ({
  label: filter,
  count: rawParamTasks.value.filter((row) => paramMatchesRoute(row, paramRouteFilter.value) && paramMatchesFilter(row, filter)).length
})));

const paramRouteOptions = computed(() => {
  const baseRows = rawParamTasks.value.filter((row) => paramMatchesFilter(row, paramTaskFilter.value));
  const counts = new Map();
  for (const row of baseRows) {
    const label = paramRouteLabel(row);
    counts.set(label, (counts.get(label) || 0) + 1);
  }
  return ['全部', 'MA', 'RSI', 'BB', 'MACD', 'SR', '其他']
    .map((label) => ({
      label,
      count: label === '全部' ? baseRows.length : (counts.get(label) || 0)
    }))
    .filter((item) => item.label === '全部' || item.count > 0);
});

const paramVisibleTasks = computed(() => sortParamTasks(rawParamTasks.value
  .filter((row) => paramMatchesFilter(row, paramTaskFilter.value))
  .filter((row) => paramMatchesRoute(row, paramRouteFilter.value)), paramSortMode.value)
  .slice(0, 18));

const autoSchedulerRows = computed(() => {
  const scheduler = mt5.value.paramAutoScheduler || {};
  return [
    ...arrayFrom(scheduler, ['selectedTasks']),
    ...arrayFrom(scheduler, ['backtestTasks'])
  ].slice(0, 16);
});

const reportWatcherRows = computed(() => arrayFrom(mt5.value.paramReportWatcher, ['watchedResults', 'reportFiles', 'rows']).slice(0, 16));
const runRecoveryRows = computed(() => arrayFrom(mt5.value.runRecovery, ['candidateDrilldown', 'recoveryQueue', 'runs', 'rows']).slice(0, 16));
const autoTesterRows = computed(() => [
  ...arrayFrom(mt5.value.autoTesterWindow, ['selectedTasks']),
  ...arrayFrom(mt5.value.autoTesterWindow, ['excludedTasks'])
].slice(0, 16));
const mt5ResearchRows = computed(() => arrayFrom(mt5.value.mt5ResearchStats, ['rows']).slice(0, 16));
const tradingAuditRows = computed(() => arrayFrom(mt5.value.ledgers?.tradingAudit).slice(0, 12));
const manualAlphaRows = computed(() => arrayFrom(mt5.value.ledgers?.manualAlpha).slice(0, 12));
const strategyEvaluationRows = computed(() => arrayFrom(mt5.value.ledgers?.strategyEvaluation).slice(0, 12));
const regimeEvaluationRows = computed(() => arrayFrom(mt5.value.ledgers?.regimeEvaluation).slice(0, 12));

const paramLabDashboardCards = computed(() => {
  const status = mt5.value.paramStatus || {};
  const results = mt5.value.paramResults || {};
  const scheduler = mt5.value.paramAutoScheduler || {};
  const watcher = mt5.value.paramReportWatcher || {};
  const recovery = mt5.value.runRecovery || {};
  const tester = mt5.value.autoTesterWindow || {};
  return [
    {
      label: '候选队列',
      value: summaryValue(scheduler, 'queueCount', rawParamTasks.value.length),
      detail: `等待报告 ${summaryValue(scheduler, 'waitReportQueueCount')} / 重调 ${summaryValue(scheduler, 'retuneQueueCount')}`
    },
    {
      label: '结果回灌',
      value: summaryValue(results, 'parsedReportCount', summaryValue(watcher, 'parsedReportCount')),
      detail: `待报告 ${summaryValue(results, 'pendingReportCount', summaryValue(watcher, 'pendingReportCount'))} / malformed ${summaryValue(results, 'malformedReportCount', summaryValue(watcher, 'malformedReportCount'))}`
    },
    {
      label: '恢复风险',
      value: `${summaryValue(recovery, 'riskRedCount', 0)}R / ${summaryValue(recovery, 'riskYellowCount', 0)}Y`,
      detail: `重试 ${summaryValue(recovery, 'retryCount', 0)} / 最近停止 ${summaryValue(recovery, 'latestStopReason')}`
    },
    {
      label: '守护窗口',
      value: summaryValue(tester, 'canRunTerminal', false) ? '可运行' : '锁定',
      detail: `blocker ${summaryValue(tester, 'blockerCount', 0)} / 持仓 ${summaryValue(tester, 'openLivePositions', 0)}`
    },
    {
      label: 'Config 状态',
      value: summaryValue(status, 'configReadyCount', 0),
      detail: `runTerminal=${first(status?.runTerminal, status?.summary?.runTerminal, false)} / selected ${summaryValue(status, 'selectedTaskCount', status?.selectedTaskCount)}`
    },
    {
      label: '研究切片',
      value: summaryValue(mt5.value.mt5ResearchStats, 'sliceCount', mt5ResearchRows.value.length),
      detail: `closed ${summaryValue(mt5.value.mt5ResearchStats, 'closedTrades', '--')} / ready ${summaryValue(mt5.value.mt5ResearchStats, 'readySlices', '--')}`
    }
  ];
});

const mt5FocusMeta = computed(() => ({
  overview: {
    eyebrow: 'AI 总览 / 入场证据',
    title: 'MT5 执行态势与入场证据',
    body: '把旧页总览雷达迁回 Vue：先看连接、行情新鲜度、仓位容量、新闻过滤和下一根评估窗口，再决定是否需要下钻到路线或持仓。',
    badge: '只读'
  },
  strategy: {
    eyebrow: '策略实盘 / 路线工作台',
    title: 'MA / RSI / BB / MACD / SR 路线工作台',
    body: '按旧页路线卡结构查看 live、candidate、ParamLab、blocker 和下一步。这里仍只展示证据，不改变 EA 风控或 live switch。',
    badge: '0.01 门控'
  },
  trades: {
    eyebrow: '交易只读 / EA 审计',
    title: '持仓、保护状态与交易审计',
    body: '优先看当前持仓、浮盈、EA 注释、手数和审计 ledger。人工单与 EA 单仍分开统计，Vue 只读展示。',
    badge: '只读审计'
  }
}[state.mt5Focus] || {
  eyebrow: 'MT5 工作台',
  title: '策略与实盘证据',
  body: 'MT5 只读工作台。',
  badge: '只读'
}));

const mt5FocusMetrics = computed(() => {
  const account = mt5Account.value;
  const route = primaryRoute.value;
  return [
    {
      label: '连接',
      value: first(mt5.value.snapshot?.status, mt5.value.snapshot?.ok === true ? '已连接' : '未连接'),
      detail: first(account.server, 'HFM 只读桥')
    },
    {
      label: '净值',
      value: money(first(account.equity, mt5.value.latest?.equity)),
      detail: `余额 ${money(account.balance)}`
    },
    {
      label: '持仓',
      value: `${mt5Positions.value.length}/${first(mt5.value.snapshot?.maxTotalPositions, mt5.value.snapshot?.risk?.maxTotalPositions, 1)}`,
      detail: '0.01 / 单仓限制'
    },
    {
      label: '焦点路线',
      value: shortText(first(route.label, route.route, route.strategy, '--'), 24),
      detail: routeActionLabel(route)
    }
  ];
});

const mt5RouteLaneCards = computed(() => ['MA', 'RSI', 'BB', 'MACD', 'SR'].map((route) => {
  const rows = allMt5Routes.value.filter((row) => routeName(row).includes(route));
  const live = rows.filter((row) => String(first(row.mode, row.recommendedAction, row.currentState, '')).toUpperCase().includes('LIVE')).length;
  const blocker = rows.find((row) => routeBlockerText(row) !== '暂无 blocker');
  return {
    route,
    count: rows.length,
    live,
    pf: first(rows[0]?.liveForward?.profitFactor, rows[0]?.profitFactor, '--'),
    blocker: blocker ? routeBlockerText(blocker) : '等待样本',
    tone: live ? 'green' : rows.length ? 'blue' : 'amber'
  };
}));

const paramLaneCards = computed(() => {
  const cards = paramLabDashboardCards.value;
  return [
    { key: 'queue', label: '候选队列', sub: '自动排队', value: cards[0]?.value, detail: cards[0]?.detail, tone: 'blue' },
    { key: 'report', label: '报告回灌', sub: '报告监视', value: cards[1]?.value, detail: cards[1]?.detail, tone: 'green' },
    { key: 'recovery', label: '恢复风险', sub: '失败恢复', value: cards[2]?.value, detail: cards[2]?.detail, tone: String(cards[2]?.value).includes('0R') ? 'amber' : 'red' },
    { key: 'guard', label: '守护窗口', sub: '自动回测窗口', value: cards[3]?.value, detail: cards[3]?.detail, tone: cards[3]?.value === '可运行' ? 'green' : 'amber' },
    { key: 'research', label: '研究切片', sub: '策略工作台', value: cards[5]?.value, detail: cards[5]?.detail, tone: 'blue' }
  ];
});

const polymarketFocusMeta = computed(() => ({
  overview: {
    eyebrow: 'Polymarket / 治理总览',
    title: '账户边界、研究队列和执行锁',
    body: 'Polymarket 与 MT5 分开管理：这里只读读取研究证据、模拟订单、小额哨兵契约和治理建议，不写钱包。',
    badge: '钱包锁定'
  },
  browser: {
    eyebrow: 'Market Browser / 市场浏览',
    title: '市场目录、概率、成交量与风险',
    body: '对照 QuantDinger 的市场浏览体验，把目录、概率、成交量、流动性和风险标签放在同一个首屏。',
    badge: `${marketRows.value.length} MARKETS`
  },
  radar: {
    eyebrow: 'Opportunity Radar / 机会雷达',
    title: 'Gamma 扫描与规则/AI 综合评分',
    body: '优先展示 active market 的概率偏离、成交量、流动性和 shadow track，不进入真实下注。',
    badge: `${radarRows.value.length} RADAR`
  },
  analysis: {
    eyebrow: 'Single Market / 单市场分析',
    title: 'URL / 标题 / marketId 研究入口',
    body: '本地生成研究请求，沉淀到历史库与 AI score，不需要手写 request 文件。',
    badge: 'LOCAL REQUEST'
  },
  execution: {
    eyebrow: 'Execution Simulation / 执行模拟',
    title: '准入、模拟订单、小额哨兵与退出后验',
    body: '只展示“如果允许下注会怎么做”的模拟契约：金额上限、止盈止损、熔断、退出监视和审计账本。',
    badge: '模拟执行'
  },
  ledger: {
    eyebrow: 'Retune Ledger / 重调账本',
    title: '历史库、批量扫描、治理和联动证据',
    body: '把雷达、AI 评分、跨市场联动、批量扫描队列和治理建议作为可审计证据沉淀。',
    badge: 'AUDIT'
  }
}[state.polymarketFocus] || {
  eyebrow: 'Polymarket Workbench',
    title: '机会雷达、历史库、AI 评分与小额哨兵治理',
  body: 'Polymarket 研究工作台。',
  badge: 'RESEARCH'
}));

const polyFocusMetrics = computed(() => [
  { label: '市场目录', value: marketRows.value.length, detail: 'Gamma / 本地缓存' },
  { label: '机会雷达', value: radarRows.value.length, detail: '概率 / 流动性 / 评分' },
  { label: 'AI 评分', value: aiScores.value.length, detail: '历史感知 V1' },
  { label: '小额哨兵', value: canaryRows.value.length, detail: '仅契约，不写钱包' },
  { label: '跨市场', value: crossRows.value.length, detail: 'USD / JPY / XAU / 宏观' },
  { label: '批量队列', value: workerQueue.value.length, detail: 'shadow-only 队列' }
]);

const radarRows = computed(() => {
  const rows = arrayFrom(poly.value.radar, ['radar', 'markets', 'rows']);
  return rows.slice(0, 8);
});

const searchGroups = computed(() => {
  const search = poly.value.search || {};
  return arrayFrom(search, ['groups', 'evidenceGroups', 'results']).slice(0, 8);
});

const aiScores = computed(() => arrayFrom(poly.value.aiScore, ['scores', 'rows']).slice(0, 8));
const governanceRows = computed(() => arrayFrom(poly.value.autoGovernance, ['governanceDecisions', 'rows']).slice(0, 8));
const canaryRows = computed(() => arrayFrom(poly.value.canary, ['candidateContracts', 'contracts']).slice(0, 8));
const crossRows = computed(() => arrayFrom(poly.value.cross, ['linkages', 'rows']).slice(0, 8));
const marketRows = computed(() => arrayFrom(poly.value.markets, ['markets', 'marketCatalog', 'rows']).slice(0, 8));
const workerQueue = computed(() => arrayFrom(poly.value.worker, ['candidateQueue', 'queue']).slice(0, 8));

const healthCards = computed(() => {
  const acct = mt5Account.value;
  const polySummary = poly.value.autoGovernance?.summary || {};
  return [
    {
      label: 'MT5 连接',
      value: first(mt5.value.snapshot?.status, mt5.value.snapshot?.ok === true ? '已连接' : '未连接'),
      detail: first(acct.server, acct.company, 'HFM 只读桥')
    },
    {
      label: 'MT5 净值',
      value: money(first(acct.equity, mt5.value.latest?.equity)),
      detail: `持仓 ${mt5Positions.value.length}`
    },
    {
      label: 'Polymarket',
      value: first(poly.value.radar?.status, poly.value.worker?.status, '研究中'),
      detail: `雷达 ${radarRows.value.length} / 队列 ${workerQueue.value.length}`
    },
    {
      label: '自动治理',
      value: first(polySummary.autoCanary, polySummary.auto_canary, 0),
      detail: `隔离执行保持锁定`
    }
  ];
});

const archiveGateCards = computed(() => [
  {
    label: '旧页冻结',
    value: '暂缓',
    detail: 'Vue 缺陷修复完成前不冻结旧页'
  },
  {
    label: '正常监盘',
    value: '待确认',
    detail: '需要一轮 Vue 监盘无缺口'
  },
  {
    label: 'ParamLab 复盘',
    value: '待确认',
    detail: '需要一次 /vue/#paramlab 与 /vue/#charts 复盘'
  },
  {
    label: '新功能入口',
    value: 'Vue only',
    detail: '旧 HTML 只做 fallback 显示修复'
  }
]);

const homeFocusCards = computed(() => {
  const govSummary = mt5.value.governance?.summary || {};
  const latestRoute = mt5Routes.value.find((row) => first(row.recommendedAction, row.feedback?.actionLabel));
  const latestRadar = radarRows.value[0] || {};
  return [
    {
      title: 'MT5 路线焦点',
      badge: first(latestRoute?.feedback?.actionLabel, latestRoute?.recommendedAction, '--'),
      body: latestRoute
        ? `${first(latestRoute.label, latestRoute.strategy, latestRoute.key)} · PF ${first(latestRoute.liveForward?.profitFactor, '--')} · 胜率 ${pct(first(latestRoute.liveForward?.winRatePct, latestRoute.liveForward?.winRate))}`
        : '等待 Governance Advisor 路线证据。',
      foot: `路线 ${first(govSummary.routeCount, mt5Routes.value.length)} / open ${first(govSummary.openPositions, mt5Positions.value.length)}`
    },
    {
      title: 'ParamLab 队列',
      badge: first(govSummary.paramLabReportWatcherPending, paramTasks.value.length),
      body: `待报告 ${first(govSummary.paramLabReportWatcherPending, '--')} · 已解析 ${first(govSummary.paramLabReportWatcherParsed, '--')} · recovery 红灯 ${first(govSummary.paramLabRunRecoveryRiskRed, '--')}`,
      foot: '仅 tester-only，不写 live preset'
    },
    {
      title: 'Polymarket 研究',
      badge: first(poly.value.radar?.status, 'OK'),
      body: latestRadar
        ? `${shortText(first(latestRadar.market, latestRadar.title, latestRadar.question), 82)} · 评分 ${first(latestRadar.aiRuleScore, latestRadar.score, '--')}`
        : '等待 Radar / AI score 证据。',
      foot: `雷达 ${radarRows.value.length} / AI ${aiScores.value.length} / 小额哨兵 ${canaryRows.value.length}`
    }
  ];
});

const reportCards = computed(() => [
  { name: 'ParamLab 队列', payload: mt5.value.paramStatus, count: paramTasks.value.length, file: 'QuantGod_ParamLabStatus.json' },
  { name: 'Report Watcher', payload: mt5.value.paramReportWatcher, count: reportWatcherRows.value.length, file: 'QuantGod_ParamLabReportWatcher.json' },
  { name: 'Run Recovery', payload: mt5.value.runRecovery, count: runRecoveryRows.value.length, file: 'QuantGod_ParamLabRunRecovery.json' },
  { name: '自动回测守护', payload: mt5.value.autoTesterWindow, count: autoTesterRows.value.length, file: 'QuantGod_AutoTesterWindow.json' },
  { name: 'MT5 研究统计', payload: mt5.value.mt5ResearchStats, count: mt5ResearchRows.value.length, file: 'QuantGod_MT5ResearchStats.json' },
  { name: 'Governance Advisor', payload: mt5.value.governance, count: mt5Routes.value.length, file: 'QuantGod_GovernanceAdvisor.json' },
  { name: 'Polymarket History', payload: poly.value.history, count: first(poly.value.history?.summary?.totalRows, poly.value.history?.rows?.length, '--'), file: 'SQLite/API' },
  { name: 'AI Score', payload: poly.value.aiScore, count: aiScores.value.length, file: 'QuantGod_PolymarketAiScoreV1.json' },
  { name: '小额哨兵契约', payload: poly.value.canary, count: canaryRows.value.length, file: 'QuantGod_PolymarketCanaryExecutorContract.json' }
]);

const reportEvidenceRows = computed(() => reportCards.value.map((card) => ({
  name: card.name,
  file: card.file,
  generatedAt: first(card.payload?.generatedAtIso, card.payload?.generatedAt, card.payload?._api?.filePath, '--'),
  count: card.count,
  state: first(card.payload?.status, card.payload?.mode, card.payload?.summary?.status, card.payload?._api?.service, '--'),
  note: first(card.payload?.note, card.payload?.summary?.latestStopReason, card.payload?.summary?.topCandidateId, card.payload?.decisionGate, '--')
})));

const activeWorkspaceMeta = computed(() => workspaces.find((item) => item.id === state.active) || workspaces[0]);

const primaryRoute = computed(() => mt5Routes.value.find((row) => String(first(row?.mode, row?.recommendedAction, '')).toUpperCase().includes('LIVE'))
  || mt5Routes.value[0]
  || {});

const operatorRadarCards = computed(() => {
  const acct = mt5Account.value;
  const route = primaryRoute.value;
  const radar = radarRows.value[0] || {};
  const topTask = paramVisibleTasks.value[0] || {};
  const score = aiScores.value[0] || {};
  const mt5Cards = [
    {
      label: 'MT5 净值',
      title: money(first(acct.equity, mt5.value.latest?.equity)),
      meta: `${first(acct.server, 'HFM 只读桥')} · 持仓 ${mt5Positions.value.length}`,
      tone: mt5Positions.value.length ? 'green' : 'blue',
      target: 'mt5'
    },
    {
      label: '实盘路线',
      title: shortText(first(route.label, route.route, route.strategy, '等待路线'), 28),
      meta: `PF ${first(route.liveForward?.profitFactor, route.profitFactor, '--')} · 胜率 ${pct(first(route.liveForward?.winRatePct, route.winRate))}`,
      tone: routeToneClass(route) || 'blue',
      target: 'mt5'
    },
    {
      label: '参数实验',
      title: shortText(first(topTask.candidateId, topTask.versionId, '等待队列'), 30),
      meta: `${first(topTask.state, topTask.status, '仅回测')} · 评分 ${first(topTask.score, topTask.grade, '--')}`,
      tone: normalizeParamState(topTask).includes('RED') ? 'red' : normalizeParamState(topTask).includes('WAIT') ? 'amber' : 'blue',
      target: 'paramlab'
    }
  ];
  const polyCards = [
    {
      label: 'Polymarket 雷达',
      title: shortText(first(radar.market, radar.title, radar.question, '等待市场'), 34),
      meta: `概率 ${pct(first(radar.probability, radar.marketProbability))} · 评分 ${first(radar.aiRuleScore, radar.score, '--')}`,
      tone: 'green',
      target: 'polymarket'
    },
    {
      label: 'AI 评分',
      title: shortText(first(score.market, score.title, score.marketId, '历史评分'), 30),
      meta: `评分 ${first(score.aiScore, score.score, score.grade, '--')} · 风险 ${first(score.risk, score.riskLevel, '--')}`,
      tone: 'blue',
      target: 'polymarket'
    },
    {
      label: '跨市场风险',
      title: `${crossRows.value.length} 条联动`,
      meta: 'USD / JPY / XAU / 宏观风险只读映射',
      tone: 'amber',
      target: 'polymarket'
    },
    {
      label: '小额哨兵契约',
      title: `${canaryRows.value.length} 个候选`,
      meta: '只定义边界，不接钱包写操作',
      tone: 'blue',
      target: 'polymarket'
    },
    {
      label: '治理建议',
      title: `${governanceRows.value.length} 条`,
      meta: `批量队列 ${workerQueue.value.length} / 历史 ${first(poly.value.history?.summary?.totalRows, '--')}`,
      tone: 'green',
      target: 'polymarket'
    }
  ];
  const paramCards = [
    {
      label: '候选队列',
      title: shortText(first(topTask.candidateId, topTask.versionId, '等待队列'), 30),
      meta: `${first(topTask.state, topTask.status, 'tester-only')} · 评分 ${first(topTask.score, topTask.grade, '--')}`,
      tone: normalizeParamState(topTask).includes('RED') ? 'red' : normalizeParamState(topTask).includes('WAIT') ? 'amber' : 'blue',
      target: 'paramlab'
    },
    {
      label: '报告回灌',
      title: `${reportWatcherRows.value.length} 条`,
      meta: `已解析 ${summaryValue(mt5.value.paramReportWatcher, 'parsedReportCount', '--')} / 待报告 ${summaryValue(mt5.value.paramReportWatcher, 'pendingReportCount', '--')}`,
      tone: 'blue',
      target: 'paramlab'
    },
    {
      label: '恢复风险',
      title: `${summaryValue(mt5.value.runRecovery, 'riskRedCount', 0)}R / ${summaryValue(mt5.value.runRecovery, 'riskYellowCount', 0)}Y`,
      meta: `重试 ${summaryValue(mt5.value.runRecovery, 'retryCount', 0)} · ${summaryValue(mt5.value.runRecovery, 'latestStopReason')}`,
      tone: summaryValue(mt5.value.runRecovery, 'riskRedCount', 0) > 0 ? 'red' : 'amber',
      target: 'paramlab'
    },
    {
      label: '守护窗口',
      title: summaryValue(mt5.value.autoTesterWindow, 'canRunTerminal', false) ? '可运行' : '锁定',
      meta: `阻断 ${summaryValue(mt5.value.autoTesterWindow, 'blockerCount', 0)} / 持仓 ${summaryValue(mt5.value.autoTesterWindow, 'openLivePositions', 0)}`,
      tone: 'amber',
      target: 'paramlab'
    },
    {
      label: '守护边界',
      title: '只读 / 模拟',
      meta: 'MT5 不改执行，Polymarket 不写钱包',
      tone: 'amber',
      target: 'reports'
    }
  ];
  if (state.active === 'polymarket') return [...polyCards, paramCards[paramCards.length - 1]];
  if (state.active === 'paramlab') return [...paramCards, mt5Cards[1]];
  if (state.active === 'mt5') return [...mt5Cards, paramCards[1], paramCards[2], paramCards[paramCards.length - 1]];
  return [...mt5Cards, ...polyCards.slice(0, 2), paramCards[paramCards.length - 1]];
});

const watchlistItems = computed(() => [
  ...mt5Routes.value.slice(0, 5).map((row) => ({
    title: shortText(first(row.label, row.route, row.strategy, row.versionId), 32),
    sub: `${routeShortName(row)} · ${routeActionLabel(row)}`,
    value: `PF ${first(row.liveForward?.profitFactor, row.profitFactor, '--')}`,
    tone: routeToneClass(row) || 'blue',
    target: 'mt5'
  })),
  ...radarRows.value.slice(0, 5).map((row) => ({
    title: shortText(first(row.market, row.title, row.question), 34),
    sub: first(row.category, row.suggestedShadowTrack, 'Polymarket'),
    value: pct(first(row.probability, row.marketProbability)),
    tone: 'green',
    target: 'polymarket'
  }))
].slice(0, 9));

const actionQueueItems = computed(() => [
  ...paramVisibleTasks.value.slice(0, 5).map((row) => ({
    title: shortText(first(row.candidateId, row.versionId, row.taskId), 34),
    sub: `${paramRouteLabel(row)} · ${first(row.state, row.status, row.resultState, '等待')}`,
    value: first(row.score, row.grade, row.profitFactor, '--'),
    tone: normalizeParamState(row).includes('RED') ? 'red' : normalizeParamState(row).includes('WAIT') ? 'amber' : 'blue',
    target: 'paramlab'
  })),
  ...governanceRows.value.slice(0, 3).map((row) => ({
    title: shortText(first(row.market, row.title, row.marketId, row.decision), 34),
    sub: first(row.action, row.recommendation, row.state, 'Polymarket 治理'),
    value: first(row.score, row.aiScore, row.confidence, '--'),
    tone: 'green',
    target: 'polymarket'
  }))
].slice(0, 8));

onMounted(() => {
  syncActiveFromHash();
  window.addEventListener('hashchange', syncActiveFromHash);
  refresh();
});

onBeforeUnmount(() => {
  window.removeEventListener('hashchange', syncActiveFromHash);
});
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">Q</div>
        <div>
          <strong>QuantGod</strong>
          <span>证据驱动工作台</span>
        </div>
      </div>

      <nav class="nav-structured">
        <button
          class="nav-item"
          :class="{ active: state.active === 'home' }"
          type="button"
          @click="setActive('home')"
        >
          <Gauge :size="18" />
          <span>
            <strong>Entry</strong>
            <small>系统入口</small>
          </span>
        </button>

        <div class="nav-separator">MT5</div>
        <button
          v-for="item in mt5NavItems"
          :key="`${item.id}-${item.focus}`"
          class="nav-item"
          :class="{ active: navItemActive(item) }"
          type="button"
          @click="setActive(item.id, item.focus)"
        >
          <component :is="item.icon" :size="18" />
          <span>
            <strong>{{ item.label }}</strong>
            <small>{{ item.sub }}</small>
          </span>
        </button>

        <div class="nav-separator">Polymarket</div>
        <button
          v-for="item in polymarketNavItems"
          :key="`${item.id}-${item.focus}`"
          class="nav-item"
          :class="{ active: navItemActive(item) }"
          type="button"
          @click="setActive(item.id, item.focus)"
        >
          <component :is="item.icon" :size="18" />
          <span>
            <strong>{{ item.label }}</strong>
            <small>{{ item.sub }}</small>
          </span>
        </button>
      </nav>

      <div class="sidebar-footer">
        <span>执行边界</span>
        <strong>MT5 与 Polymarket 分离</strong>
        <small>默认只读 / 模拟订单 / 钱包锁定</small>
      </div>
    </aside>

    <main class="workspace">
      <header class="topbar">
        <div>
          <p class="eyebrow">{{ activeWorkspaceMeta.sub }}</p>
          <h1>{{ activeWorkspaceMeta.label }}</h1>
          <p class="topbar-subtitle">{{ activeWorkspaceMeta.desc }}</p>
        </div>
        <div class="top-actions">
          <label class="search-box">
            <Search :size="16" />
            <input v-model="state.query" type="search" placeholder="搜索市场、路线、候选和证据" @keyup.enter="refresh" />
          </label>
          <button class="ghost-button" type="button" @click="refresh">
            <RefreshCw :size="16" :class="{ spin: state.loading }" />
            刷新
          </button>
        </div>
      </header>

      <div class="operator-strip">
        <button
          v-for="card in operatorRadarCards"
          :key="card.label"
          class="operator-card"
          :class="card.tone"
          type="button"
          @click="setActive(card.target)"
        >
          <span>{{ card.label }}</span>
          <strong>{{ card.title }}</strong>
          <small>{{ card.meta }}</small>
        </button>
      </div>

      <div class="workspace-layout">
        <div class="workspace-main">
          <section v-if="state.error" class="notice danger">{{ state.error }}</section>

      <section v-if="state.active === 'home'" class="stack">
        <div class="section-grid">
          <article class="hero-panel compact-hero">
            <p class="eyebrow">AI Opportunity Radar</p>
            <h2>MT5 与 Polymarket 分开管理，同一证据层复盘</h2>
            <p>
              这里按 QuantDinger 的操作台思路重排：顶部看机会雷达，中间处理监盘与研究队列，右侧保留 Watchlist 和待办。旧页先继续作为 fallback，不冻结。
            </p>
            <div class="route-tabs">
              <button type="button" @click="setActive('mt5')">进入 MT5 工作台</button>
              <button type="button" @click="setActive('polymarket')">进入 Polymarket 工作台</button>
              <button type="button" @click="setActive('paramlab')">进入 ParamLab</button>
              <button type="button" @click="setActive('charts')">查看趋势图表</button>
            </div>
          </article>

          <article class="panel">
            <div class="panel-title">
              <ShieldCheck :size="18" />
              <span>运行快照</span>
            </div>
            <div class="metric-grid">
              <div v-for="card in healthCards" :key="card.label" class="metric">
                <span>{{ card.label }}</span>
                <strong>{{ card.value }}</strong>
                <small>{{ card.detail }}</small>
              </div>
            </div>
            <p class="muted">最后刷新：{{ first(state.loadedAt, '尚未刷新') }}</p>
          </article>
        </div>

        <article class="analysis-console">
          <div class="console-grid-bg"></div>
          <div class="console-core">
            <span>AI-POWERED</span>
            <h2>QuantGod 分析引擎</h2>
            <p>MT5 forward、ParamLab tester-only、Polymarket research 和审计 ledger 全部从同一证据层读取。</p>
            <div class="console-actions">
              <button type="button" @click="setActive('mt5')">策略监盘</button>
              <button type="button" @click="setActive('paramlab')">参数队列</button>
              <button type="button" @click="setActive('polymarket')">市场研究</button>
            </div>
          </div>
        </article>

        <article class="panel">
          <div class="panel-title split">
            <span>Vue 替代旧页缺口追踪</span>
            <small>未达标前不冻结旧 HTML</small>
          </div>
          <div class="metric-grid four compact">
            <div v-for="card in archiveGateCards" :key="card.label" class="metric">
              <span>{{ card.label }}</span>
              <strong>{{ card.value }}</strong>
              <small>{{ card.detail }}</small>
            </div>
          </div>
        </article>

        <div class="card-grid three">
          <article v-for="card in homeFocusCards" :key="card.title" class="panel dense focus-card">
            <div class="panel-title split">
              <span>{{ card.title }}</span>
              <b class="pill blue">{{ card.badge }}</b>
            </div>
            <p>{{ card.body }}</p>
            <small>{{ card.foot }}</small>
          </article>
        </div>
      </section>

      <section v-if="state.active === 'mt5'" class="stack page-mt5" :data-focus="state.mt5Focus">
        <div class="workbench-hero mt5-hero">
          <article class="hero-copy">
            <div class="panel-title split">
              <span class="eyebrow">{{ mt5FocusMeta.eyebrow }}</span>
              <b class="pill blue">{{ mt5FocusMeta.badge }}</b>
            </div>
            <h2>{{ mt5FocusMeta.title }}</h2>
            <p>{{ mt5FocusMeta.body }}</p>
          </article>
          <article class="hero-metrics">
            <div v-for="card in mt5FocusMetrics" :key="card.label" class="micro-metric">
              <span>{{ card.label }}</span>
              <strong>{{ card.value }}</strong>
              <small>{{ card.detail }}</small>
            </div>
          </article>
        </div>

        <div class="toolbar dense-toolbar">
          <div>
            <p class="eyebrow">路线筛选</p>
            <h2>路线筛选与证据下钻</h2>
          </div>
          <div class="route-tabs compact">
            <button
              v-for="route in routeFilters"
              :key="route"
              type="button"
              :class="{ selected: activeRoute === route }"
              @click="activeRoute = route"
            >
              {{ route }}
            </button>
          </div>
        </div>

        <div class="mt5-command-grid">
          <article class="panel overview-radar mt5-radar-board">
            <div class="panel-title split">
              <span>执行雷达</span>
              <small>旧页总览雷达口径</small>
            </div>
            <div class="radar-grid dense-radar">
              <div v-for="item in mt5ExecutionRadarItems" :key="item.label" class="radar-item">
                <span class="radar-label">{{ item.label }}</span>
                <strong class="radar-value">{{ item.value }}</strong>
                <small class="radar-sub">{{ item.sub }}</small>
              </div>
            </div>
          </article>

          <article class="panel mt5-lane-board">
            <div class="panel-title split">
              <span>路线工作台</span>
              <small>MA / RSI / BB / MACD / SR</small>
            </div>
            <div class="lane-stack">
              <button
                v-for="lane in mt5RouteLaneCards"
                :key="lane.route"
                class="lane-row"
                :class="lane.tone"
                type="button"
                @click="activeRoute = lane.route"
              >
                <strong>{{ lane.route }}</strong>
                <span>{{ lane.count }} 版本 · live {{ lane.live }}</span>
                <small>PF {{ lane.pf }} · {{ lane.blocker }}</small>
              </button>
            </div>
          </article>
        </div>

        <DataTable
          v-if="state.mt5Focus === 'trades'"
          title="EA / 手动持仓快照"
          dense
          :rows="mt5Positions"
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

        <div class="strategy-card-grid">
          <article v-for="row in mt5Routes" :key="first(row.versionId, row.route, row.name)" class="panel dense">
            <div class="panel-title split">
              <span>{{ first(row.label, row.route, row.strategy, row.name, row.versionId) }}</span>
              <b class="pill" :class="routeToneClass(row)">{{ routeActionLabel(row) }}</b>
            </div>
            <p>{{ shortText(routeWhyText(row), 170) }}</p>
            <div class="mini-row">
              <span>{{ routeShortName(row) }}</span>
              <span>PF {{ first(row.liveForward?.profitFactor, row.profitFactor, row.pf, '--') }}</span>
              <span>胜率 {{ pct(first(row.liveForward?.winRatePct, row.winRate, row.win_rate)) }}</span>
              <span>{{ first(row.mode, row.live ? 'LIVE_0_01' : 'SIM/CANDIDATE') }}</span>
            </div>
            <div class="mini-row secondary">
              <span>实盘 {{ first(row.liveForward?.closedTrades, '--') }} 笔 / 净 {{ money(row.liveForward?.netProfitUSC) }}</span>
              <span>候选 {{ first(row.candidateSamples?.rows, row.candidateSamples?.ledgerRows, '--') }}</span>
              <span>后验 {{ first(row.candidateSamples?.horizonRows, '--') }}</span>
              <span>阻断 {{ routeBlockerText(row) }}</span>
            </div>
            <p class="route-param">参数候选：{{ routeParamText(row) }}</p>
            <p v-if="row.openPosition?.openTrades" class="route-warning">
              当前持仓 {{ row.openPosition.openTrades }}，浮动 {{ money(row.openPosition.floatingProfitUSC) }}，先按原风控与保护处理。
            </p>
            <p v-else class="route-param">当前无该路线持仓。</p>
            <p class="route-param">下一步：{{ shortText(first(row.feedback?.nextStep, row.paramLabResult?.promotionReadiness, row.recommendedAction), 130) }}</p>
          </article>
          <article v-if="!mt5Routes.length" class="panel empty">当前没有可展示的 MT5 路线证据，等待运行文件或只读桥刷新。</article>
        </div>

        <Mt5DeepPanels :mt5="mt5" :positions="mt5Positions" :routes="mt5Routes" />
      </section>

      <section v-if="state.active === 'polymarket'" class="stack page-polymarket" :data-focus="state.polymarketFocus">
        <div class="workbench-hero poly-hero">
          <article class="hero-copy">
            <div class="panel-title split">
              <span class="eyebrow">{{ polymarketFocusMeta.eyebrow }}</span>
              <b class="pill green">{{ polymarketFocusMeta.badge }}</b>
            </div>
            <h2>{{ polymarketFocusMeta.title }}</h2>
            <p>{{ polymarketFocusMeta.body }}</p>
            <div v-if="state.polymarketFocus === 'analysis'" class="inline-form hero-form">
              <input v-model="state.marketInput" type="text" placeholder="Polymarket URL / 标题 / marketId" @keyup.enter="submitSingleMarket" />
              <button type="button" @click="submitSingleMarket">生成请求</button>
            </div>
            <small v-if="state.polymarketFocus === 'analysis'">{{ state.requestStatus }}</small>
          </article>
          <article class="hero-metrics poly-metrics">
            <div v-for="card in polyFocusMetrics" :key="card.label" class="micro-metric">
              <span>{{ card.label }}</span>
              <strong>{{ card.value }}</strong>
              <small>{{ card.detail }}</small>
            </div>
          </article>
        </div>

        <div class="poly-cockpit-grid">
          <article class="panel poly-market-console">
            <div class="panel-title split">
              <span>{{ state.polymarketFocus === 'browser' ? '市场目录' : state.polymarketFocus === 'execution' ? '执行模拟边界' : '机会雷达' }}</span>
              <small>研究驾驶舱</small>
            </div>
            <div v-if="state.polymarketFocus === 'browser'" class="compact-market-list">
              <div v-for="market in marketRows" :key="first(market.marketId, market.slug)" class="market-line">
                <strong>{{ shortText(first(market.title, market.question, market.slug), 72) }}</strong>
                <span>{{ first(market.category, '--') }}</span>
                <b>{{ pct(first(market.probability, market.bestProbability)) }}</b>
              </div>
              <div v-if="!marketRows.length" class="rail-empty">暂无市场目录证据。</div>
            </div>
            <div v-else-if="state.polymarketFocus === 'execution'" class="compact-market-list">
              <div v-for="row in canaryRows" :key="first(row.canaryContractId, row.marketId)" class="market-line">
                <strong>{{ shortText(first(row.market, row.title, row.marketId, row.canaryContractId), 72) }}</strong>
                <span>{{ first(row.canaryState, row.decision, '模拟') }}</span>
                <b>{{ money(first(row.canaryStakeUSDC, row.stake)) }}</b>
              </div>
              <div v-if="!canaryRows.length" class="rail-empty">暂无小额哨兵契约；真实钱包仍保持锁定。</div>
            </div>
            <div v-else class="radar-ticker">
              <div v-for="row in radarRows.slice(0, 6)" :key="first(row.marketId, row.slug, row.title)" class="radar-ticker-item">
                <span>{{ shortText(first(row.market, row.title, row.question, row.slug), 52) }}</span>
                <strong>{{ pct(first(row.probability, row.marketProbability)) }}</strong>
                <small>评分 {{ first(row.aiRuleScore, row.score, '--') }} · 成交量 {{ money(first(row.volume, row.volumeUsd)) }}</small>
              </div>
              <div v-if="!radarRows.length" class="rail-empty">暂无 radar 快照。</div>
            </div>
          </article>

          <article class="panel poly-governance-console">
            <div class="panel-title split">
              <span>治理/联动摘要</span>
              <small>只读证据，不下注</small>
            </div>
            <div class="governance-lanes">
              <div v-for="row in governanceRows.slice(0, 4)" :key="first(row.governanceId, row.marketId)" class="governance-lane">
                <b>{{ first(row.decision, row.currentState, row.action, '观察') }}</b>
                <span>{{ shortText(first(row.market, row.title, row.marketId, row.reason), 86) }}</span>
              </div>
              <div v-if="!governanceRows.length" class="rail-empty">暂无自动治理建议。</div>
            </div>
          </article>
        </div>

        <div class="poly-radar-grid">
          <article v-for="row in radarRows" :key="first(row.marketId, row.slug, row.title)" class="panel dense radar-evidence-card">
            <div class="panel-title split">
              <span>{{ shortText(first(row.market, row.title, row.question, row.slug), 78) }}</span>
              <b class="pill blue">评分 {{ first(row.aiRuleScore, row.score, '--') }}</b>
            </div>
            <p>{{ shortText(first(row.reason, row.suggestedShadowTrack, row.category), 150) }}</p>
            <div class="mini-row">
              <span>概率 {{ pct(first(row.probability, row.marketProbability)) }}</span>
              <span>成交量 {{ money(first(row.volume, row.volumeUsd)) }}</span>
              <span>流动性 {{ money(first(row.liquidity, row.liquidityUsd, row.clobLiquidityUsd)) }}</span>
            </div>
          </article>
        </div>

        <div class="panel evidence-console">
          <div class="panel-title split">
            <span>统一搜索综合证据卡</span>
            <small>{{ searchGroups.length }} 条</small>
          </div>
          <div class="evidence-list">
            <div v-for="group in searchGroups" :key="first(group.marketId, group.id, group.title)" class="evidence-row">
              <strong>{{ shortText(first(group.title, group.market, group.question, group.marketId), 92) }}</strong>
              <span>{{ shortText(first(group.summary, group.reason, group.recommendation, group.decision), 180) }}</span>
              <small>{{ first(group.source, group.sources?.join?.(', '), group.type, '综合证据') }}</small>
            </div>
            <div v-if="!searchGroups.length" class="empty">没有搜索结果；可以在右上角输入关键词后刷新。</div>
          </div>
        </div>

        <PolymarketDeepPanels
          :polymarket="poly"
          :radar-rows="radarRows"
          :search-groups="searchGroups"
          :ai-scores="aiScores"
          :governance-rows="governanceRows"
          :canary-rows="canaryRows"
          :cross-rows="crossRows"
          :worker-queue="workerQueue"
        />
      </section>

      <section v-if="state.active === 'paramlab'" class="stack page-paramlab">
        <div class="workbench-hero paramlab-hero">
          <article class="hero-copy">
            <div class="panel-title split">
              <span class="eyebrow">ParamLab / 回测闭环</span>
              <b class="pill amber">TESTER-ONLY</b>
            </div>
            <h2>候选参数、批次队列、报告回灌与恢复风险</h2>
            <p>对照旧页和 QuantDinger 的 worker/queue 体验，把“可运行、等待报告、已评分、失败恢复、守护窗口”放成一张批次看板；这里只生成和展示 tester-only 证据，不启动 Strategy Tester。</p>
          </article>
          <article class="param-lane-board">
            <button
              v-for="lane in paramLaneCards"
              :key="lane.key"
              class="param-lane"
              :class="lane.tone"
              type="button"
              @click="paramTaskFilter = lane.label === '恢复风险' ? '红灯' : lane.label === '报告回灌' ? '等待报告' : '全部'"
            >
              <span>{{ lane.sub }}</span>
              <strong>{{ lane.label }} · {{ lane.value }}</strong>
              <small>{{ lane.detail }}</small>
            </button>
          </article>
        </div>

        <div class="panel dense split-panel">
          <div>
            <div class="panel-title">周末执行清单筛选</div>
            <p class="muted">按旧页的批次口径聚合 queue / results / watcher；红灯 candidate 只显示风险，不消耗自动重试次数。</p>
          </div>
          <div class="filter-stack">
            <div class="route-tabs compact">
              <button
                v-for="filter in paramFilterOptions"
                :key="filter.label"
                type="button"
                :class="{ selected: paramTaskFilter === filter.label }"
                @click="paramTaskFilter = filter.label"
              >
                {{ filter.label }} {{ filter.count }}
              </button>
            </div>
            <div class="route-tabs compact">
              <button
                v-for="route in paramRouteOptions"
                :key="route.label"
                type="button"
                :class="{ selected: paramRouteFilter === route.label }"
                @click="paramRouteFilter = route.label"
              >
                {{ route.label }} {{ route.count }}
              </button>
              <label class="select-control">
                <span>排序</span>
                <select v-model="paramSortMode">
                  <option>优先级</option>
                  <option>评分高</option>
                  <option>最近</option>
                  <option>路线</option>
                </select>
              </label>
            </div>
          </div>
        </div>

        <div class="table-panel">
          <table>
            <thead>
              <tr>
                <th>候选</th>
                <th>路线</th>
                <th>状态</th>
                <th>评分</th>
                <th>报告</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="task in paramVisibleTasks" :key="first(task.candidateId, task.taskId, task.versionId)">
                <td>{{ shortText(first(task.candidateId, task.versionId, task.name), 42) }}</td>
                <td>{{ first(task.route, task.strategy, task.symbol, '--') }}</td>
                <td><span class="pill">{{ first(task.state, task.status, task.resultState, '--') }}</span></td>
                <td>{{ first(task.score, task.grade, task.profitFactor, '--') }}</td>
                <td>{{ shortText(first(task.reportPath, task.report, task.configPath), 64) }}</td>
              </tr>
              <tr v-if="!paramVisibleTasks.length"><td colspan="5">当前筛选没有 ParamLab 队列或结果。</td></tr>
            </tbody>
          </table>
        </div>

        <ParamLabDeepPanels
          :mt5="mt5"
          :tasks="paramVisibleTasks"
          :auto-scheduler-rows="autoSchedulerRows"
          :report-watcher-rows="reportWatcherRows"
          :run-recovery-rows="runRecoveryRows"
          :auto-tester-rows="autoTesterRows"
          :research-rows="mt5ResearchRows"
        />
      </section>

      <section v-if="state.active === 'charts'" class="stack">
        <TrendVisuals
          :mt5="mt5"
          :polymarket="poly"
          :routes="mt5Routes"
          :positions="mt5Positions"
          :param-tasks="paramTasks"
          :radar-rows="radarRows"
          :ai-scores="aiScores"
          :governance-rows="governanceRows"
          :canary-rows="canaryRows"
          :cross-rows="crossRows"
          :worker-queue="workerQueue"
          :auto-scheduler="mt5.paramAutoScheduler"
          :report-watcher="mt5.paramReportWatcher"
          :auto-tester-window="mt5.autoTesterWindow"
          :research-stats="mt5.mt5ResearchStats"
        />
      </section>

      <section v-if="state.active === 'reports'" class="stack">
        <div class="toolbar">
          <div>
            <p class="eyebrow">Reports</p>
            <h2>证据文件与服务化状态</h2>
          </div>
        </div>
        <div class="card-grid">
          <article v-for="card in reportCards" :key="card.name" class="panel dense">
            <div class="panel-title split">
              <span>{{ card.name }}</span>
              <b class="pill">{{ card.count }}</b>
            </div>
            <p>{{ shortText(first(card.payload?.decision, card.payload?.status, card.payload?.mode, '等待证据'), 140) }}</p>
            <small>{{ card.file }} · generatedAt: {{ first(card.payload?.generatedAtIso, card.payload?.generatedAt, '--') }}</small>
          </article>
        </div>

        <DataTable
          title="证据文件新鲜度"
          :rows="reportEvidenceRows"
          :columns="[
            { label: '证据', value: (r) => r.name, width: '180px' },
            { label: '文件/API', value: (r) => r.file, width: '260px' },
            { label: '时间', value: (r) => r.generatedAt, width: '220px' },
            { label: '数量', value: (r) => r.count, width: '90px' },
            { label: '状态', value: (r) => r.state, width: '160px', badge: true },
            { label: '备注', value: (r) => r.note, max: 160 }
          ]"
          empty="暂无证据文件。"
        />

        <div class="card-grid">
          <DataTable
            title="策略评估表"
            :rows="strategyEvaluationRows"
            :columns="[
              { label: '策略', value: (r) => first(r.Strategy, r.strategy, r.Route), width: '170px' },
              { label: '品种', value: (r) => first(r.Symbol, r.symbol), width: '110px' },
              { label: '样本', value: (r) => first(r.Trades, r.trades, r.Samples), width: '80px' },
              { label: 'PF', value: (r) => first(r.ProfitFactor, r.PF, r.pf), width: '90px' },
              { label: '胜率', value: (r) => first(r.WinRate, r.winRate), width: '90px' },
              { label: '净收益', value: (r) => first(r.NetProfit, r.netProfit), width: '100px' }
            ]"
            empty="暂无策略评估表。"
          />
          <DataTable
            title="Regime 评估切片"
            :rows="regimeEvaluationRows"
            :columns="[
              { label: '策略', value: (r) => first(r.Strategy, r.strategy, r.Route), width: '150px' },
              { label: '品种', value: (r) => first(r.Symbol, r.symbol), width: '110px' },
              { label: 'Regime', value: (r) => first(r.Regime, r.regime, r.MarketRegime), width: '150px' },
              { label: '样本', value: (r) => first(r.Samples, r.Trades, r.samples), width: '80px' },
              { label: 'PF / Win', value: (r) => `${first(r.PF, r.ProfitFactor, '--')} / ${first(r.WinRate, r.winRate, '--')}`, width: '120px' },
              { label: '状态', value: (r) => first(r.State, r.status, r.Decision), badge: true }
            ]"
            empty="暂无 Regime 评估切片。"
          />
        </div>

        <div class="card-grid">
          <DataTable
            title="MT5 交易审计"
            :rows="tradingAuditRows"
            :columns="[
              { label: '时间', value: (r) => first(r.Time, r.time, r.timestamp), width: '180px' },
              { label: '票据', value: (r) => first(r.Ticket, r.ticket), width: '100px' },
              { label: '品种', value: (r) => first(r.Symbol, r.symbol), width: '100px' },
              { label: '动作', value: (r) => first(r.Action, r.action, r.Event), width: '120px', badge: true },
              { label: '策略', value: (r) => first(r.Strategy, r.strategy, r.Route), max: 100 },
              { label: '备注', value: (r) => first(r.Reason, r.reason, r.Message), max: 130 }
            ]"
            empty="暂无 MT5 审计记录。"
          />
          <DataTable
            title="Manual Alpha Ledger"
            :rows="manualAlphaRows"
            :columns="[
              { label: '时间', value: (r) => first(r.Time, r.time, r.OpenTime, r.CloseTime), width: '180px' },
              { label: '品种', value: (r) => first(r.Symbol, r.symbol), width: '100px' },
              { label: '方向', value: (r) => first(r.Direction, r.direction, r.Type), width: '90px', badge: true },
              { label: '净值', value: (r) => first(r.NetProfit, r.Profit, r.netProfit), width: '100px' },
              { label: 'Regime', value: (r) => first(r.Regime, r.regime), width: '120px' },
              { label: '备注', value: (r) => first(r.Note, r.note, r.Reason), max: 130 }
            ]"
            empty="暂无人工交易样本。"
          />
        </div>

        <div class="panel">
          <div class="panel-title">Polymarket 市场浏览</div>
          <div class="table-panel embedded">
            <table>
              <thead>
                <tr><th>市场</th><th>分类</th><th>概率</th><th>成交量</th><th>风险</th></tr>
              </thead>
              <tbody>
                <tr v-for="market in marketRows" :key="first(market.marketId, market.slug)">
                  <td>{{ shortText(first(market.title, market.question, market.slug), 56) }}</td>
                  <td>{{ first(market.category, '--') }}</td>
                  <td>{{ pct(first(market.probability, market.bestProbability)) }}</td>
                  <td>{{ money(first(market.volume, market.volumeUsd)) }}</td>
                  <td>{{ first(market.risk, market.riskLevel, market.status, '--') }}</td>
                </tr>
                <tr v-if="!marketRows.length"><td colspan="5">暂无市场目录证据。</td></tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="drawer-grid">
          <EvidenceDrawer title="Governance Advisor raw" :payload="mt5.governance" />
          <EvidenceDrawer title="AutoTesterWindow raw" :payload="mt5.autoTesterWindow" />
          <EvidenceDrawer title="MT5ResearchStats raw" :payload="mt5.mt5ResearchStats" />
          <EvidenceDrawer title="Polymarket AI raw" :payload="poly.aiScore" />
        </div>
      </section>
        </div>

        <aside class="command-rail">
          <section class="rail-card">
            <div class="rail-title">
              <span>我的 Watchlist</span>
              <small>{{ watchlistItems.length }} 项</small>
            </div>
            <button
              v-for="item in watchlistItems"
              :key="`${item.target}-${item.title}`"
              type="button"
              class="rail-item"
              :class="item.tone"
              @click="setActive(item.target)"
            >
              <span>
                <strong>{{ item.title }}</strong>
                <small>{{ item.sub }}</small>
              </span>
              <b>{{ item.value }}</b>
            </button>
            <div v-if="!watchlistItems.length" class="rail-empty">等待 MT5 路线或 Polymarket 雷达刷新。</div>
          </section>

          <section class="rail-card">
            <div class="rail-title">
              <span>待处理队列</span>
              <small>{{ actionQueueItems.length }} 条</small>
            </div>
            <button
              v-for="item in actionQueueItems"
              :key="`${item.target}-${item.title}`"
              type="button"
              class="rail-item compact"
              :class="item.tone"
              @click="setActive(item.target)"
            >
              <span>
                <strong>{{ item.title }}</strong>
                <small>{{ item.sub }}</small>
              </span>
              <b>{{ item.value }}</b>
            </button>
            <div v-if="!actionQueueItems.length" class="rail-empty">暂无需要处理的候选或治理项。</div>
          </section>

          <section class="rail-card boundary">
            <div class="rail-title">
              <span>执行边界</span>
              <small>锁定</small>
            </div>
            <p>MT5 只读展示与既有 EA 风控分离；Polymarket 保持模拟订单/小额哨兵契约，不触发钱包写操作。</p>
          </section>
        </aside>
      </div>
    </main>
  </div>
</template>
