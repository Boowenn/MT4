<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';
import {
  Activity,
  BarChart3,
  Bell,
  CalendarDays,
  ClipboardList,
  Gauge,
  Globe2,
  Layers,
  LineChart,
  Menu,
  Network,
  Plus,
  RefreshCw,
  Search,
  Settings,
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
  { id: 'ai', label: 'AI 工作台', sub: '分析引擎', icon: Activity, desc: '对照 QuantDinger 的 AI 分析入口：即时分析、机会雷达、历史记忆与下一步建议' },
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
  sidebarCollapsed: false,
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

let autoRefreshTimer = null;
const autoRefreshMs = 5000;

const routeFilters = ['全部', 'MA', 'RSI', 'BB', 'MACD', 'SR'];
const activeRoute = ref('全部');
const paramTaskFilter = ref('全部');
const paramRouteFilter = ref('全部');
const paramSortMode = ref('优先级');
const polyCategoryFilter = ref('全部');
const polySortMode = ref('机会评分');
const polyEvidenceMode = ref('综合证据');

const mt5WorkspaceIds = new Set(['mt5', 'paramlab', 'charts', 'reports']);
const mt5DefaultFocus = {
  mt5: 'overview',
  paramlab: 'paramlab',
  charts: 'monitor',
  reports: 'reports'
};

const mt5NavItems = [
  { id: 'mt5', focus: 'overview', label: 'MT5 总览', sub: '执行雷达', icon: Gauge },
  { id: 'mt5', focus: 'strategy', label: '策略路线', sub: '实盘 / 候选', icon: LineChart },
  { id: 'charts', focus: 'monitor', label: '趋势图表', sub: '品种监控', icon: TrendingUp },
  { id: 'paramlab', focus: 'paramlab', label: '参数实验', sub: '回测闭环', icon: ClipboardList },
  { id: 'mt5', focus: 'trades', label: '交易只读', sub: 'EA 与人工单', icon: Activity },
  { id: 'reports', focus: 'reports', label: '证据报表', sub: '审计总览', icon: BarChart3 }
];

const mt5FocusByHash = {
  mt5: 'overview',
  'mt5-overview': 'overview',
  'section-mt5': 'overview',
  'section-mt5-overview': 'overview',
  'mt5-strategy': 'strategy',
  'section-mt5-strategy': 'strategy',
  'mt5-trades': 'trades',
  'section-mt5-trades': 'trades'
};

const mt5HashByFocus = {
  overview: 'mt5',
  strategy: 'mt5-strategy',
  trades: 'mt5-trades'
};

const polymarketNavItems = [
  { id: 'polymarket', focus: 'overview', label: '治理总览', sub: '账户与边界', icon: Network },
  { id: 'polymarket', focus: 'browser', label: '市场浏览', sub: '目录 / 详情', icon: ClipboardList },
  { id: 'polymarket', focus: 'radar', label: '机会雷达', sub: 'Gamma 扫描', icon: Target },
  { id: 'polymarket', focus: 'analysis', label: '单市场分析', sub: 'URL/标题入口', icon: Search },
  { id: 'polymarket', focus: 'execution', label: '执行模拟', sub: '准入 / 模拟', icon: WalletCards },
  { id: 'polymarket', focus: 'ledger', label: '重调账本', sub: '样本与日志', icon: BarChart3 }
];

const polymarketFocusByHash = {
  polymarket: 'overview',
  'polymarket-overview': 'overview',
  'polymarket-market-browser': 'browser',
  'polymarket-browser': 'browser',
  'polymarket-radar': 'radar',
  'polymarket-analysis': 'analysis',
  'polymarket-execution': 'execution',
  'polymarket-ledger': 'ledger',
  'section-polymarket': 'overview',
  'section-polymarket-market-browser': 'browser',
  'section-polymarket-radar': 'radar',
  'section-polymarket-analysis': 'analysis',
  'section-polymarket-execution': 'execution',
  'section-polymarket-ledger': 'ledger'
};

const polymarketHashByFocus = {
  overview: 'polymarket',
  browser: 'polymarket-market-browser',
  radar: 'polymarket-radar',
  analysis: 'polymarket-analysis',
  execution: 'polymarket-execution',
  ledger: 'polymarket-ledger'
};

const routeDisplayMap = {
  MA_CROSS: 'MA',
  RSI_REVERSAL: 'RSI',
  BB_TRIPLE: 'BB',
  MACD_DIVERGENCE: 'MACD',
  SR_BREAKOUT: 'SR'
};

const routeRuntimeKeyMap = {
  MA: 'MA_Cross',
  RSI: 'RSI_Reversal',
  BB: 'BB_Triple',
  MACD: 'MACD_Divergence',
  SR: 'SR_Breakout'
};

function normalizeWorkspace(id) {
  return workspaces.some((item) => item.id === id) ? id : 'home';
}

function parseWorkspaceHash(hash) {
  if (mt5FocusByHash[hash]) {
    return {
      active: 'mt5',
      mt5Focus: mt5FocusByHash[hash]
    };
  }
  if (polymarketFocusByHash[hash]) {
    return {
      active: 'polymarket',
      polymarketFocus: polymarketFocusByHash[hash]
    };
  }
  return { active: normalizeWorkspace(hash || 'home') };
}

function hashForActive(active, focus = '') {
  if (active === 'home') return '';
  if (active === 'polymarket') {
    const polymarketFocus = focus || state.polymarketFocus || 'overview';
    return `#${polymarketHashByFocus[polymarketFocus] || 'polymarket'}`;
  }
  if (active === 'mt5') {
    const mt5Focus = focus || state.mt5Focus || 'overview';
    return `#${mt5HashByFocus[mt5Focus] || 'mt5'}`;
  }
  return `#${active}`;
}

function syncActiveFromHash() {
  const hash = window.location.hash.replace(/^#\/?/, '');
  const parsed = parseWorkspaceHash(hash);
  state.active = parsed.active;
  if (workspaceDomainFor(state.active) === 'mt5') {
    state.mt5Focus = parsed.mt5Focus || mt5DefaultFocus[state.active] || state.mt5Focus || 'overview';
  }
  if (state.active === 'polymarket') {
    state.polymarketFocus = parsed.polymarketFocus || state.polymarketFocus || 'overview';
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
  if (state.active === 'polymarket') {
    state.polymarketFocus = focus || state.polymarketFocus || 'overview';
  }
  const nextHash = hashForActive(state.active, focus);
  if (window.location.hash !== nextHash) {
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}${nextHash}`);
  }
  window.scrollTo({ top: 0, behavior: 'auto' });
}

function navItemActive(item) {
  if (item.focus) {
    if (item.id === 'polymarket') return state.active === item.id && state.polymarketFocus === item.focus;
    return state.active === item.id && state.mt5Focus === item.focus;
  }
  return state.active === item.id;
}

function handleTopAction(action) {
  if (action === 'menu') {
    state.sidebarCollapsed = !state.sidebarCollapsed;
    return;
  }
  if (action === 'notifications') {
    setActive('reports');
    return;
  }
  if (action === 'market') {
    setActive('polymarket', 'browser');
    return;
  }
  if (action === 'settings') {
    setActive('paramlab');
  }
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
  const normalized = typeof value === 'string' ? value.replace(/[$,%\s,]/g, '') : value;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function money(value) {
  const n = asNumber(value);
  return n === null ? '--' : `$${n.toFixed(2)}`;
}

function positionTicket(row) {
  const raw = first(
    row?.ticket,
    row?.Ticket,
    row?.identifier,
    row?.positionId,
    row?.positionTicket,
    row?.position_ticket,
    row?.order,
    row?.Order,
    ''
  );
  return raw === '--' ? '' : raw;
}

function positionProfit(row) {
  return first(row?.profit, row?.pnl, row?.unrealizedPnl, row?.actualProfit, row?.floatingProfit, row?.Profit);
}

function positionDirection(row) {
  const raw = String(first(row?.type, row?.direction, row?.side, row?.cmd, '')).toUpperCase();
  if (raw.includes('SELL') || raw === '1') return '卖出';
  if (raw.includes('BUY') || raw === '0') return '买入';
  return first(row?.type, row?.direction, row?.side, '--');
}

function positionCurrentPrice(row) {
  return first(row?.priceCurrent, row?.price_current, row?.currentPrice, row?.price, row?.closePrice, row?.bid, row?.ask);
}

function booleanish(value) {
  if (value === true) return true;
  if (value === false) return false;
  const raw = String(first(value, '')).trim().toLowerCase();
  return ['true', '1', 'yes', 'y'].includes(raw);
}

function compactId(value, max = 14) {
  const raw = String(first(value, '')).trim();
  if (!raw || raw === '--') return '--';
  return raw;
}

function compactIsoTime(value) {
  const raw = String(first(value, '')).trim();
  if (!raw || raw === '--') return '--';
  return raw.replace('T', ' ').replace(/\.\d+Z?$/, '').replace(/Z$/, '').slice(0, 16);
}

function auditProfit(row) {
  return first(
    row?.Profit,
    row?.profit,
    row?.PnL,
    row?.pnl,
    row?.NetProfit,
    row?.netProfit,
    row?.ProfitUSC,
    row?.profitUSC
  );
}

function auditProfitText(row) {
  const raw = auditProfit(row);
  const numeric = asNumber(raw);
  if (numeric !== null) return money(numeric);
  return cleanInlineStatusText(raw);
}

function pnlTone(value) {
  const numeric = asNumber(value);
  if (numeric === null) return 'pnl-flat';
  if (numeric < 0) return 'pnl-negative';
  if (numeric > 0) return 'pnl-positive';
  return 'pnl-flat';
}

function auditTime(row) {
  return compactIsoTime(first(row?.EventTimeIso, row?.Time, row?.time, row?.timeIso, row?.timestamp));
}

function auditRecordId(row) {
  return compactId(first(row?.Ticket, row?.ticket, row?.BrokerOrderTicket, row?.LedgerId, row?.EventId, row?.eventId, row?.order));
}

function auditScope(row) {
  const endpoint = String(first(row?.Endpoint, row?.endpoint, '')).toLowerCase();
  if (endpoint === 'login') return '账户登录';
  return first(
    row?.BrokerSymbol,
    row?.brokerSymbol,
    row?.Symbol,
    row?.symbol,
    row?.CanonicalSymbol,
    row?.canonicalSymbol,
    row?.Route,
    row?.route,
    '全局审计'
  );
}

function auditActionText(row) {
  const endpoint = String(first(row?.Endpoint, row?.endpoint, '')).toLowerCase();
  const action = String(first(row?.Action, row?.action, '')).toLowerCase();
  const decision = String(first(row?.Decision, row?.decision, '')).toUpperCase();
  const dryRun = booleanish(row?.DryRun);
  if (endpoint === 'login' || action === 'login') return dryRun ? '模拟登录' : '登录请求';
  if (endpoint === 'order' || action === 'order') {
    if (dryRun || decision.includes('DRY_RUN')) return '模拟下单';
    return '下单请求';
  }
  if (endpoint === 'close' || action === 'close') return dryRun ? '模拟平仓' : '平仓请求';
  if (endpoint === 'cancel' || action === 'cancel') return dryRun ? '模拟撤单' : '撤单请求';
  return compactStatusLabel(first(row?.Action, row?.action, row?.Event, row?.event, row?.Endpoint, '--'));
}

function auditDirectionText(row) {
  const raw = String(first(row?.OrderType, row?.orderType, row?.Side, row?.side, row?.Direction, row?.direction, '')).toLowerCase();
  if (raw.includes('buy_limit')) return '买入挂单';
  if (raw.includes('sell_limit')) return '卖出挂单';
  if (raw.includes('buy')) return '买入';
  if (raw.includes('sell')) return '卖出';
  return '--';
}

function auditDecisionText(row) {
  const decision = String(first(row?.Decision, row?.decision, row?.Result, row?.result, '')).toUpperCase();
  if (!decision || decision === '--') return '--';
  const map = {
    DRY_RUN_ACCEPTED: '模拟记录',
    DRY_RUN_REJECTED: '模拟拒绝',
    ACCEPTED: '已接受',
    REJECTED: '已拒绝',
    BLOCKED: '已阻断',
    LIVE_ALLOWED: '实盘允许',
    LIVE_REJECTED: '实盘拒绝',
    ORDER_SENT: '已发送',
    ORDER_FAILED: '发送失败'
  };
  return map[decision] || compactStatusLabel(decision);
}

const auditReasonMap = {
  dry_run: '模拟模式',
  trading_config_disabled: '配置禁用交易',
  trading_env_disabled: '环境禁用交易',
  kill_switch_on: 'Kill switch',
  dashboard_market_orders_disabled: '市价单禁用',
  dashboard_pending_orders_disabled: '挂单禁用',
  owner_mode_blocks_python_trading: 'Owner 仅 EA',
  auth_lock_missing: '授权锁缺失',
  auth_lock_unreadable: '授权锁不可读',
  auth_lock_expiry_missing: '授权锁无过期',
  signature_secret_missing: '签名密钥缺失',
  lots_required: '缺手数',
  route_symbol_daily_order_limit_reached: '路线/品种日限',
  daily_order_limit_reached: '日下单上限',
  route_not_allowed_by_config: '路线未授权',
  login_disabled: '登录禁用',
  order_send_disabled: '发送禁用',
  spread_guard_blocked: '点差拦截',
  session_guard_blocked: '时段拦截',
  cooldown_guard_blocked: '冷却拦截',
  portfolio_guard_blocked: '组合上限',
  kill_switch_required: '需要 Kill switch',
  live_not_allowed: '实盘未允许'
};

function auditReasonText(row, limit = 4) {
  const reason = String(first(row?.Reason, row?.reason, row?.Message, row?.message, row?.Note, row?.note, '')).trim();
  if (!reason || reason === '--') return '--';
  const parts = reason.split(/[,;/]+/).map((part) => part.trim()).filter(Boolean);
  if (!parts.length) return cleanInlineStatusText(reason);
  const labels = parts.map((part) => auditReasonMap[part] || cleanInlineStatusText(part));
  const visible = labels.slice(0, limit).join(' / ');
  return labels.length > limit ? `${visible} +${labels.length - limit}` : visible;
}

function auditLotsText(row) {
  return first(row?.Lots, row?.lots, row?.Volume, row?.volume, '--');
}

function auditPriceText(row) {
  return first(row?.Price, row?.price, row?.OpenPrice, row?.openPrice, '--');
}

function auditRouteText(row) {
  return cleanInlineStatusText(first(row?.Route, row?.route, row?.Strategy, row?.strategy, row?.WorkerVersion, row?.workerVersion, '--'));
}

function pct(value) {
  const n = asNumber(value);
  if (n === null) return '--';
  const normalized = Math.abs(n) <= 1 ? n * 100 : n;
  return `${normalized.toFixed(1)}%`;
}

function pctPoint(value) {
  const n = asNumber(value);
  return n === null ? '--' : `${n.toFixed(1)}%`;
}

function shortText(value, max = 120) {
  const text = String(first(value, '')).replace(/\s+/g, ' ').trim();
  if (!text) return '--';
  return text;
}

const evidenceLabelMap = {
  EVIDENCE_BLOCKED: '证据不足',
  SHADOW_OR_RESEARCH: '仅研究',
  LOCKED: '已锁定',
  BLOCKED: '阻断',
  GLOBAL_LOSS_QUARANTINE: '全局亏损隔离',
  LOSS_QUARANTINE: '亏损隔离',
  EXECUTED_PF_BELOW_1: '实盘 PF < 1',
  EXECUTED_WIN_RATE_LOW: '实盘胜率偏低',
  EXECUTED_REALIZED_PNL_NEGATIVE: '实盘净损',
  SIM_SAMPLE_LT_MIN: '模拟样本不足',
  SIM_WIN_RATE_LT_MIN: '模拟胜率不足',
  SIM_PROFIT_FACTOR_LT_MIN: '模拟 PF 不足',
  SIM_AVG_RETURN_LT_MIN: '模拟均值不足',
  AI_SCORE_LT_REAL_MONEY_MIN: 'AI 分不足',
  AI_COLOR_YELLOW_BLOCKED: 'AI 黄灯阻断',
  COMPOSITE_SCORE_LT_REAL_MONEY_MIN: '综合分不足',
  REAL_EXECUTION_SWITCH_FALSE: '真钱开关关闭',
  LIVE_BETTING_SWITCH_FALSE: '下注开关关闭',
  CANARY_ACK_MISSING: '缺少哨兵确认',
  CANARY_KILL_SWITCH_REQUIRED: '需要熔断开关',
  WALLET_ADAPTER_NOT_VERIFIED: '钱包适配未验证',
  ORDER_AUDIT_REQUIRED: '需要订单审计',
  CONTRACT_ONLY_NO_WALLET_WRITE: '仅契约不写钱包',
  OPERATOR_PROMOTION_REQUIRED: '需要人工晋级',
  RESEARCH_GOVERNANCE_BLOCKS_LIVE: '研究治理阻断',
  LOCAL_PNL_NEGATIVE_QUARANTINE: '本地亏损隔离',
  RETUNE_RED_ROUTES_PRESENT: '存在红灯重调',
  RETUNE_YELLOW_ROUTES_PRESENT: '存在黄灯重调',
  QUARANTINE_NO_PROMOTION: '隔离中不晋级',
  DRY_RUN_BLOCKED_BY_GATE: '模拟被 Gate 阻断',
  GATE_BLOCKED_PRICE_WATCH_ONLY: '仅价格观察',
  KEEP_DRY_RUN_UNTIL_POLICY_PASS: '继续模拟',
  WATCH_SHADOW_AND_COLLECT_OUTCOME: '观察并收集后验',
  RETUNE_BEFORE_NEXT_BATCH: '先重调再跑下一批',
  LIVE_0_01: '0.01 实盘',
  LIVE_GATED: '实盘门控',
  SIMULATION_CANDIDATE: '模拟候选',
  SIM_CANDIDATE: '模拟候选',
  CONFIG_READY: '可运行',
  PENDING_REPORT: '等报告',
  WAIT_REPORT: '等报告',
  RUN_PENDING_REPORT_FIRST: '先跑回测报告',
  RULE_PROXY_NO_LLM: '规则评分',
  WORKER_EVIDENCE: 'Worker 证据',
  SHADOW: 'Shadow 观察',
  SHADOW_REVIEW: 'Shadow 复核',
  MACRO_RISK: '宏观风险',
  WAR_GEOPOLITICS: '战争/地缘',
  RATES: '利率',
  USD: '美元',
  JPY: '日元',
  XAU: '黄金',
  POLITICS: '政治',
  SPORTS: '体育',
  CRYPTO: '加密',
  HIGH: '高',
  MEDIUM: '中',
  LOW: '低',
  GREEN: '绿灯',
  YELLOW: '黄灯',
  RED: '红灯'
};

function humanEvidenceLabel(value) {
  const raw = String(first(value, '')).trim();
  if (!raw || raw === '--') return '--';
  const key = raw.toUpperCase().replace(/[\s/.-]+/g, '_');
  if (evidenceLabelMap[key]) return evidenceLabelMap[key];
  if (/[A-Z0-9]+_[A-Z0-9_]+/.test(raw)) {
    return raw.toLowerCase().replace(/_/g, ' ');
  }
  return raw;
}

function evidenceTokens(...values) {
  const flattened = values.flatMap((value) => {
    if (!value) return [];
    if (Array.isArray(value)) return value;
    if (typeof value === 'object') return Object.keys(value);
    return String(value)
      .split(/[,/|;]+/)
      .map((item) => item.trim())
      .filter(Boolean);
  });
  const seen = new Set();
  return flattened
    .map(humanEvidenceLabel)
    .filter((label) => label && label !== '--')
    .filter((label) => {
      const key = label.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function governanceTitle(row) {
  return shortText(first(row?.question, row?.market, row?.title, row?.marketId, row?.governanceId), 86);
}

function governanceDecisionLabel(row) {
  return humanEvidenceLabel(first(row?.decision, row?.currentState, row?.governanceState, row?.action, row?.canaryState, '观察'));
}

function governanceDetail(row) {
  return shortText(first(row?.nextTest, row?.reason, row?.blocker, row?.marketId, '保持只读/模拟，等待证据改善。'), 96);
}

function crossRiskLabel(row) {
  return humanEvidenceLabel(first(row?.primaryRiskTag, row?.macroRiskState, row?.category, '风险'));
}

function crossAssetLabels(row) {
  return evidenceTokens(row?.linkedMt5Symbols).slice(0, 4);
}

function crossDetail(row) {
  const keywordMap = row?.matchedKeywords || {};
  const keywords = Object.values(keywordMap).flat().slice(0, 4).join(' / ');
  return shortText(first(row?.reason, keywords, row?.riskTags?.join?.(', '), row?.sourceTypes?.join?.(', '), '只做风险联动证据'), 110);
}

function blockerChips(row, max = 3) {
  return evidenceTokens(row?.blockers, row?.globalBlockers, row?.reason, row?.blocker).slice(0, max);
}

function routeName(row) {
  return String(first(row?.key, row?.route, row?.strategy, row?.strategyName, row?.name, row?.candidateId, '')).toUpperCase();
}

function routeShortName(row) {
  const name = routeName(row);
  return Object.entries(routeDisplayMap).find(([key]) => name.includes(key))?.[1] || first(row?.strategy, row?.route, row?.key, '--');
}

function routeRuntimeKey(row) {
  const short = String(routeShortName(row)).toUpperCase();
  return routeRuntimeKeyMap[short] || first(row?.strategyKey, row?.strategy, row?.route, row?.key, '');
}

function strategyToken(value) {
  return String(value || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
}

function routeRuntime(row) {
  const key = routeRuntimeKey(row);
  const latest = mt5.value.latest || {};
  const direct = latest.strategies?.[key] || latest.diagnostics?.[key];
  if (direct) return direct;
  const symbolRows = Array.isArray(latest.symbols) ? latest.symbols : [];
  return symbolRows.find((symbol) => symbol?.strategies?.[key])?.strategies?.[key] || {};
}

function routeHasOpenPosition(row) {
  const key = strategyToken(routeRuntimeKey(row));
  if (!key) return false;
  return mt5Positions.value.some((position) => {
    const strategy = strategyToken(first(position.strategy, position.route, ''));
    const comment = strategyToken(first(position.comment, position.Comment, ''));
    return strategy === key || comment.includes(key) || (key === 'RSIREVERSAL' && comment.includes('RSIREV'));
  });
}

function routeIsRuntimeLive(row) {
  const runtime = routeRuntime(row);
  const risk = asNumber(runtime.riskMultiplier);
  const enabled = runtime.enabled === true || String(first(runtime.runtimeLabel, runtime.state, '')).toUpperCase() === 'ON';
  return enabled && (risk === null || risk > 0);
}

function routeActionLabel(row) {
  if (!row || Object.keys(row).length === 0) return '等待路线';
  if (routeHasOpenPosition(row)) return '实盘持仓';
  const runtime = routeRuntime(row);
  const action = String(first(row?.feedback?.actionLabel, row?.recommendedAction, row?.currentState, row?.state, row?.mode, '')).toUpperCase();
  const risk = asNumber(runtime.riskMultiplier);
  if (routeIsRuntimeLive(row)) return '实盘观察';
  if (runtime.enabled === false || risk === 0) return action.includes('LIVE') ? '实盘暂停' : '模拟候选';
  return cleanInlineStatusText(first(row?.feedback?.actionLabel, row?.recommendedAction, row?.currentState, row?.state, row?.mode, '观察'));
}

function routeBlockerText(row) {
  const blockers = row?.blockers || row?.paramLabResult?.blockers || row?.feedback?.riskAreas;
  if (Array.isArray(blockers)) return blockers.slice(0, 3).join(' / ') || '暂无 blocker';
  return first(blockers, row?.blocker, '暂无 blocker');
}

function routeWhyText(row) {
  const why = row?.feedback?.why;
  if (Array.isArray(why) && why.length) return cleanInlineStatusText(why.slice(0, 2).join(' '));
  const runtime = routeRuntime(row);
  return cleanInlineStatusText(first(runtime.adaptiveReason, runtime.reason, row?.feedback?.nextStep, row?.nextAction, row?.reason, routeBlockerText(row)));
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
  if (routeHasOpenPosition(row) || routeIsRuntimeLive(row)) return 'green';
  const runtime = routeRuntime(row);
  const risk = asNumber(runtime.riskMultiplier);
  if (runtime.enabled === false || risk === 0) return 'amber';
  const action = String(first(row?.recommendedAction, row?.mode, row?.tone, '')).toUpperCase();
  if (action.includes('LIVE') || action.includes('KEEP_LIVE')) return 'green';
  if (action.includes('RETUNE') || action.includes('DEMOTE')) return 'amber';
  if (action.includes('SIM') || action.includes('CANDIDATE')) return 'blue';
  return '';
}

function normalizeParamState(row) {
  return String(first(row?.state, row?.status, row?.resultState, row?.grade, row?.queueState, row?.riskColor, '')).toUpperCase();
}

function compactStatusLabel(value) {
  const raw = String(first(value, '')).trim();
  if (!raw || raw === '--') return '--';
  const key = raw.toUpperCase().replace(/[\s/.-]+/g, '_');
  const exact = {
    CONFIG_ONLY: '仅配置',
    CONFIG_READY: '可运行',
    RUN_PENDING_REPORT_FIRST: '等报告',
    WAIT_REPORT: '等报告',
    WAITING_REPORT: '等报告',
    PENDING_REPORT: '等报告',
    FILE_ONLY_REPORT_WATCHER: '报告文件',
    FILE_ONLY_RUN_HISTORY: '运行历史',
    EVALUATE_ONLY: '只评估',
    MT5_RESEARCH_STATS: 'MT5研究',
    POLYMARKET_AI_SCORE: 'AI评分',
    POLYMARKET_MARKET_RADAR: '市场雷达',
    POLYMARKET_SINGLE_MARKET: '单市场',
    POLYMARKET_HISTORY_API: '历史API',
    EXISTING_PARAMLAB_TASKS: '已有任务',
    OK: '正常',
    READY: '可运行',
    PARSED: '已解析',
    SCORED: '已评分',
    PROMOTION: '可晋级',
    DEMOTION: '降级',
    RETUNE: '重调',
    QUARANTINE: '隔离',
    WATCH_SHADOW_AND_COLLECT_OUTCOME: '观察后验',
    RETUNE_BEFORE_NEXT_BATCH: '先重调',
    LIVE_0_01: '0.01实盘',
    LIVE_GATED: '实盘门控',
    SIMULATION_CANDIDATE: '模拟候选',
    SIM_CANDIDATE: '模拟候选',
    RULE_PROXY_NO_LLM: '规则评分',
    WORKER_EVIDENCE: 'Worker证据',
    SHADOW: 'Shadow观察',
    SHADOW_REVIEW: 'Shadow复核',
    LOCKED: '锁定',
    RED: '红灯',
    YELLOW: '黄灯',
    GREEN: '绿灯'
  };
  if (exact[key]) return exact[key];
  if (key.includes('AI_SCOR')) return 'AI评分';
  if (key.includes('MARKET_RADAR')) return '市场雷达';
  if (key.includes('SINGLE_MARKET')) return '单市场';
  if (key.includes('RESEARCH_STATS')) return '研究统计';
  if (key.includes('REPORT_WATCH')) return '报告文件';
  if (key.includes('RUN_HIST')) return '运行历史';
  if (key.includes('REPORT')) return '等报告';
  if (key.includes('HISTORY')) return '历史';
  if (key.includes('PARAMLAB')) return '参数任务';
  if (key.includes('POLYMARKET')) return 'Polymarket证据';
  if (key.includes('RESEARCH')) return '研究统计';
  if (key.includes('EVALUATE')) return '评估';
  return humanEvidenceLabel(raw);
}

function cleanInlineStatusText(value) {
  const raw = String(first(value, '')).trim();
  if (!raw || raw === '--') return '--';
  const fullKey = raw.toUpperCase().replace(/[\s/.-]+/g, '_');
  if (evidenceLabelMap[fullKey]) return evidenceLabelMap[fullKey];
  return raw.replace(/\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b/g, (token) => {
    const label = compactStatusLabel(token);
    return label && label !== token ? label : humanEvidenceLabel(token);
  });
}

function compactMetricScore(...values) {
  const raw = String(first(...values, '--')).trim();
  if (!raw || raw === '--') return '--';
  const key = raw.toUpperCase();
  if (/^[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+$/.test(key)) return '--';
  if (['CONFIG_READY', 'PENDING_REPORT', 'WAIT_REPORT', 'WAITING_REPORT'].includes(key)) return '--';
  return raw;
}

function aiSourceLabel(value) {
  const raw = String(first(value, '')).trim();
  const key = raw.toUpperCase().replace(/[\s-]+/g, '_');
  if (key.includes('AI_SCORE')) return 'AI';
  if (key.includes('PARAMLAB')) return '参数';
  if (key.includes('SEARCH') || raw.includes('综合')) return '综合';
  if (key.includes('RADAR')) return '雷达';
  if (key.includes('HISTORY')) return '历史';
  return shortText(raw || '证据', 8);
}

function compactInsightDetail(value) {
  const raw = String(first(value, '')).trim();
  if (!raw || raw === '--') return '等待证据';
  const key = raw.toUpperCase().replace(/[\s-]+/g, '_');
  const exact = {
    KEEP_DRY_RUN_UNTIL_POLICY_PASS: '保持模拟，等待策略通过',
    WORKER_EVIDENCE: 'Worker 证据',
    SHADOW_REVIEW: 'Shadow 复核',
    CANARY_LOCKED: '哨兵锁定',
    EVIDENCE_BLOCKED: '证据不足',
    CLOSED_LOSS_QUARANTINE: '亏损隔离'
  };
  if (exact[key]) return exact[key];
  if (/[A-Z0-9]+_[A-Z0-9_]+/.test(raw)) return cleanInlineStatusText(raw);
  return raw;
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

function stopReasonLabel(reason) {
  const key = String(first(reason, '')).toLowerCase();
  const labels = {
    waiting_guard_clearance: '等待守护条件解除',
    wait_auto_tester_window: '等待自动回测窗口',
    outside_strategy_tester_window: '不在 Strategy Tester 时间窗',
    authorization_lock_missing: '缺少授权锁文件',
    authorization_lock_not_authorized: '授权锁未允许执行',
    authorization_lock_not_tester_only: '授权锁不是 tester-only',
    open_live_positions_present: '仍有实盘持仓',
    symbol_open_positions_present: '品种仍有持仓',
    strategy_open_positions_present: '策略仍有持仓',
    live_account_margin_in_use: '实盘账户仍占用保证金',
    report_missing: '报告缺失',
    report_malformed: '报告格式异常'
  };
  if (!key) return '--';
  return labels[key] || key.replace(/_/g, ' ');
}

function recoveryRiskValue(payload) {
  return `红灯 ${summaryValue(payload, 'riskRedCount', 0)} / 黄灯 ${summaryValue(payload, 'riskYellowCount', 0)}`;
}

function recoveryRiskDetail(payload) {
  return `累计重试 ${summaryValue(payload, 'retryCount', 0)} / 最近停止：${stopReasonLabel(summaryValue(payload, 'latestStopReason'))}`;
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
  const latest = mt5.value.latest || {};
  const openKeys = ['items', 'positions', 'openPositions', 'openTrades', 'open_trades'];
  const rows = [
    ...arrayFrom(snap.positions, openKeys),
    ...arrayFrom(snap.openTrades, openKeys),
    ...arrayFrom(snap.snapshot?.positions, openKeys),
    ...arrayFrom(snap.snapshot?.openTrades, openKeys),
    ...arrayFrom(latest.positions, openKeys),
    ...arrayFrom(latest.openPositions, openKeys),
    ...arrayFrom(latest.openTrades, openKeys),
    ...arrayFrom(latest.open_trades, openKeys)
  ];
  const seenTickets = new Set();
  const seenFingerprints = new Set();
  return rows.filter((row, index) => {
    const closedMarker = String(first(row?.status, row?.state, row?.closeTime, row?.close_time, '')).toUpperCase();
    if (/(CLOSED|HISTORY|SETTLED)/.test(closedMarker)) return false;
    const ticketKey = String(positionTicket(row));
    const fingerprint = [
      String(first(row?.symbol, row?.Symbol, 'symbol')).toUpperCase(),
      String(positionDirection(row)).toUpperCase(),
      Number(first(row?.volume, row?.lots, row?.actualLots, row?.Volume, 0)).toFixed(2),
      Number(first(row?.priceOpen, row?.price_open, row?.openPrice, 0)).toFixed(5),
      String(first(row?.comment, row?.route, row?.strategy, `row-${index}`)).toUpperCase()
    ].join('|');
    if (ticketKey && seenTickets.has(ticketKey)) return false;
    if (seenFingerprints.has(fingerprint)) return false;
    if (ticketKey) seenTickets.add(ticketKey);
    seenFingerprints.add(fingerprint);
    return true;
  });
});

const mt5ClosedTrades = computed(() => {
  const snap = mt5.value.snapshot || {};
  const latest = mt5.value.latest || {};
  const closedKeys = ['items', 'closedTrades', 'historyTrades', 'closed_positions', 'closed_trades'];
  const rows = [
    ...arrayFrom(snap.closedTrades, closedKeys),
    ...arrayFrom(snap.historyTrades, closedKeys),
    ...arrayFrom(snap.snapshot?.closedTrades, closedKeys),
    ...arrayFrom(latest.closedTrades, closedKeys),
    ...arrayFrom(latest.historyTrades, closedKeys),
    ...arrayFrom(latest.closed_trades, closedKeys)
  ];
  const seen = new Set();
  return rows.filter((row, index) => {
    const key = String(first(row?.ticket, row?.Ticket, row?.positionId, row?.deal, row?.closeTime, `closed-${index}`));
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 100);
});

const focusedPosition = computed(() => mt5Positions.value[0] || {});

const duplicatedPositionEvidence = computed(() => {
  const latest = mt5.value.latest || {};
  const snap = mt5.value.snapshot || {};
  const openKeys = ['items', 'positions', 'openPositions', 'openTrades', 'open_trades'];
  const rawCount = [
    ...arrayFrom(snap.positions, openKeys),
    ...arrayFrom(snap.openTrades, openKeys),
    ...arrayFrom(latest.openTrades, openKeys)
  ].length;
  return Math.max(rawCount - mt5Positions.value.length, 0);
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
      value: first(snap.serverTime, snap.serverTimeIso, latest.serverTime, '--'),
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
      value: first(route.label, route.route, route.strategy, '等待机会'),
      sub: routeActionLabel(route)
    },
    {
      label: '阻塞摘要',
      value: routeBlockerText(route),
      sub: first(route.feedback?.riskLevel, route.riskLevel, '等待信号')
    },
    {
      label: 'USD 新闻过滤',
      value: news,
      sub: first(snap.calendar?.blocker, latest.newsBlocker, '无新增高危新闻')
    },
    {
      label: '下一条新闻',
      value: first(snap.nextNewsEvent, latest.nextNewsEvent, '--'),
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
const tradingAuditRows = computed(() => arrayFrom(mt5.value.ledgers?.tradingAudit).slice(0, 80));
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
      value: recoveryRiskValue(recovery),
      detail: recoveryRiskDetail(recovery)
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
    eyebrow: 'MT5 总览 / 入场证据',
    title: 'MT5 执行态势与入场证据',
    body: '把旧页总览雷达迁回 Vue：先看连接、行情新鲜度、仓位容量、新闻过滤和下一根评估窗口，再决定是否需要查看路线或持仓详情。',
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
      value: first(route.label, route.route, route.strategy, '--'),
      detail: routeActionLabel(route)
    }
  ];
});

const mt5RouteLaneCards = computed(() => ['MA', 'RSI', 'BB', 'MACD', 'SR'].map((route) => {
  const rows = allMt5Routes.value.filter((row) => routeName(row).includes(route));
  const live = rows.filter((row) => routeHasOpenPosition(row) || routeIsRuntimeLive(row)).length;
  const blocker = rows.find((row) => routeBlockerText(row) !== '暂无 blocker');
  return {
    route,
    count: rows.length,
    live,
    pf: first(rows[0]?.liveForward?.profitFactor, rows[0]?.profitFactor, '--'),
    blocker: blocker ? routeBlockerText(blocker) : '等待样本',
    tone: live ? 'green' : rows.some((row) => routeRuntime(row).enabled === false) ? 'amber' : rows.length ? 'blue' : 'amber'
  };
}));

const paramLaneCards = computed(() => {
  const cards = paramLabDashboardCards.value;
  return [
    { key: 'queue', label: '候选队列', sub: '自动排队', value: cards[0]?.value, detail: cards[0]?.detail, tone: 'blue' },
    { key: 'report', label: '报告回灌', sub: '报告监视', value: cards[1]?.value, detail: cards[1]?.detail, tone: 'green' },
    { key: 'recovery', label: '恢复风险', sub: '失败恢复', value: cards[2]?.value, detail: cards[2]?.detail, tone: summaryValue(mt5.value.runRecovery, 'riskRedCount', 0) > 0 ? 'red' : 'amber' },
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

const polyAccountCards = computed(() => {
  const gov = poly.value.autoGovernance || {};
  const run = poly.value.canaryRun || {};
  const global = gov.globalState || gov.accountSnapshot || {};
  const safety = gov.safety || {};
  const summary = gov.summary || {};
  const env = run.envPreflight || {};
  const cash = first(global.cashUSDC, global.accountCash, global.availableUSDC, global.balanceUSDC, null);
  const bankroll = first(global.configuredBankrollUSDC, global.bankroll, global.maxBankrollUSDC, null);
  const hasCash = asNumber(cash) !== null;
  const walletWrite = first(summary.walletWriteAllowed, safety.walletWriteAllowed, run.summary?.walletWriteAllowed, false);
  const orderSend = first(summary.orderSendAllowed, safety.orderSendAllowed, run.summary?.orderSendAllowed, false);

  return [
    {
      label: '账户现金',
      value: hasCash ? money(cash) : '未连接',
      detail: hasCash ? 'Polymarket USDC 口径' : '未读取到 Polymarket 余额',
      tone: hasCash ? 'green' : 'amber'
    },
    {
      label: '配置本金',
      value: asNumber(bankroll) !== null ? money(bankroll) : '--',
      detail: first(global.authState, 'read-only / no wallet write'),
      tone: 'blue'
    },
    {
      label: '钱包写入',
      value: walletWrite === true ? '已开启' : '关闭',
      detail: orderSend === true ? 'order-send 已允许' : '只读/模拟，未下真钱',
      tone: walletWrite === true ? 'red' : 'green'
    },
    {
      label: '隔离执行',
      value: env.lockFileOk === true ? '锁已就绪' : '锁定',
      detail: `阻断 ${Array.isArray(run.preflightBlockers) ? run.preflightBlockers.length : 0} / orders ${first(run.summary?.ordersSent, 0)}`,
      tone: env.lockFileOk === true ? 'amber' : 'blue'
    }
  ];
});

function parseJsonList(value) {
  if (Array.isArray(value)) return value;
  if (!value || typeof value !== 'string') return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch (_) {
    return [];
  }
}

const polyResearchSnapshot = computed(() => {
  const recent = poly.value.history?.recent || {};
  const research = recent.research || recent.snapshot || {};
  const snapshots = arrayFrom(recent, ['snapshots', 'researchSnapshots']);
  return research && Object.keys(research).length ? research : (snapshots[0] || {});
});

const polyRiskEvents = computed(() => parseJsonList(first(
  polyResearchSnapshot.value.topRiskEventsJson,
  polyResearchSnapshot.value.top_risk_events_json,
  '[]'
)));

function polyTradeStatus(row) {
  return cleanInlineStatusText(first(row?.status, row?.state, row?.entryStatus, row?.positionState, row?.decision, '--'));
}

function polyTradePnl(row) {
  return first(row?.realized_pnl_usdc, row?.realizedPnlUSDC, row?.realizedPnl, row?.pnl, row?.profit, row?.unrealizedPnl);
}

function polyTradeStake(row) {
  return first(row?.stake_usdc, row?.stakeUSDC, row?.stake, row?.amount, row?.size_usdc, row?.size);
}

function polyTradeSide(row) {
  const raw = String(first(row?.side, row?.entry_side, row?.direction, row?.outcome, '--')).trim();
  const upper = raw.toUpperCase();
  if (upper === 'BUY' || upper === 'LONG') return '买入';
  if (upper === 'SELL' || upper === 'SHORT') return '卖出';
  return raw || '--';
}

function polyTradeTime(row) {
  return compactIsoTime(first(row?.opened_at, row?.openedAt, row?.entryIso, row?.entry_timestamp, row?.timestamp, row?.generated_at));
}

function polyTradeClosedTime(row) {
  return compactIsoTime(first(row?.closed_at, row?.closedAt, row?.exitIso, row?.exit_timestamp, row?.settledAt, row?.generated_at));
}

function isPolyTradeOpen(row) {
  const status = String(first(row?.status, row?.state, row?.positionState, row?.decision, '')).toUpperCase();
  if (/(CLOSED|SETTLED|EXITED|FILLED_AND_CLOSED)/.test(status)) return false;
  if (first(row?.closed_at, row?.closedAt, row?.exitIso, row?.exit_timestamp, '') !== '--') return false;
  return true;
}

const polyRealTradeRows = computed(() => {
  const rows = [
    ...arrayFrom(poly.value.realTrades, ['rows', 'trades', 'items']),
    ...arrayFrom(poly.value.ledgers, ['realTrades'])
  ];
  const seen = new Set();
  return rows.filter((row, index) => {
    if (!row || typeof row !== 'object') return false;
    const hasMarket = first(row.question, row.market, row.title, row.market_id, row.marketId, row.slug, '') !== '--';
    const hasEvidence = first(row.trade_id, row.tradeId, row.order_id, row.orderId, row.tx_hash, row.txHash, row.realized_pnl_usdc, row.realizedPnl, '') !== '--';
    if (!hasMarket && !hasEvidence) return false;
    const key = [
      first(row.trade_id, row.tradeId, ''),
      first(row.order_id, row.orderId, ''),
      first(row.tx_hash, row.txHash, ''),
      first(row.market_id, row.marketId, row.question, ''),
      first(row.opened_at, row.openedAt, row.entryIso, row.generated_at, index)
    ].join('|');
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 200);
});

const polyRealSummaryCards = computed(() => {
  const row = polyResearchSnapshot.value || {};
  const realSummary = poly.value.realTrades?.summary || {};
  const summary = poly.value.history?.summary || {};
  const executedPnl = first(realSummary.realizedPnlUSDC, row.executedPnl, row.executed_pnl, '--');
  const pnlNumber = asNumber(executedPnl);
  return [
    {
      label: '真钱已结算',
      value: first(realSummary.closedRows, row.executedClosed, row.executed_closed, summary.executedClosed, 0),
      detail: `胜率 ${pct(first(realSummary.winRatePct, row.executedWinRate, row.executed_win_rate, '--'))}`,
      tone: 'blue'
    },
    {
      label: '真钱 PF',
      value: first(row.executedPf, row.executed_pf, '--'),
      detail: `净收益 ${money(executedPnl)}`,
      tone: pnlNumber === null ? 'blue' : (pnlNumber < 0 ? 'red' : 'green')
    },
    {
      label: '账户现金',
      value: money(first(row.accountCash, row.account_cash, '--')),
      detail: `bankroll ${money(first(row.bankroll, row.configuredBankrollUSDC, '--'))}`,
      tone: 'green'
    },
    {
      label: '认证状态',
      value: cleanInlineStatusText(first(row.authState, row.auth_state, '--')),
      detail: first(row.generatedAt, row.generated_at, '--'),
      tone: 'amber'
    }
  ];
});

const polyCurrentRealRows = computed(() => {
  const direct = [
    ...polyRealTradeRows.value.filter(isPolyTradeOpen),
    ...arrayFrom(poly.value.history, ['openPositions', 'positions', 'activePositions', 'openTrades', 'realOpenPositions']),
    ...arrayFrom(poly.value.canaryRun, ['openPositions', 'positions', 'activePositions', 'plannedOrders']),
    ...arrayFrom(poly.value.canary, ['openPositions', 'positions', 'activePositions']),
    ...arrayFrom(poly.value.ledgers, ['canaryPositions']),
    ...arrayFrom(poly.value.ledgers, ['canaryOrderAudit'])
  ];
  return direct.filter((row) => {
    if (!row || typeof row !== 'object') return false;
    const status = String(first(row.status, row.state, row.positionState, row.position_state, row.decision, '')).toUpperCase();
    const orderSent = String(first(row.orderSent, row.order_sent, row.order_send_allowed, row.orderSendAllowed, '')).toLowerCase();
    const hasStake = asNumber(first(row.stakeUSDC, row.stake_usdc, row.stake, row.amount, row.size, null)) !== null;
    const hasMarket = first(row.question, row.market, row.title, row.marketId, row.market_id, '') !== '--';
    if (!hasMarket) return false;
    if (/(CLOSED|SETTLED|NO_REAL_ORDER_SENT|DRY_RUN|BLOCKED|HEADER)/.test(status)) return false;
    if (orderSent === 'false' && !hasStake) return false;
    return true;
  }).slice(0, 20);
});

const polyRealEvidenceNote = computed(() => {
  if (polyCurrentRealRows.value.length) return `${polyCurrentRealRows.value.length} 条当前真钱进行中记录。`;
  if (polyRealTradeRows.value.length) return `已接入 ${polyRealTradeRows.value.length} 条逐笔真钱交易历史；当前没有进行中的真钱持仓。`;
  const realSource = poly.value.realTrades || {};
  if (realSource.status === 'SOURCE_EMPTY') return 'D:\\polymarket 当前为空目录；逐笔真钱交易导入接口已就绪，恢复 copybot.db / trades.csv 后会自动显示。';
  if (realSource.status === 'SOURCE_MISSING') return '尚未找到逐笔真钱交易源；可运行 tools/import_polymarket_real_trade_ledger.py 做只读导入。';
  const pending = polyRiskEvents.value.find((event) => String(event.event || '').toUpperCase() === 'ACTIVE_EXIT_PENDING');
  const auditRows = first(poly.value.history?.summary?.canaryOrderAuditRows, 0);
  if (pending) {
    return `当前未发现可核验的 row-level 持仓；历史日志曾出现 ACTIVE_EXIT_PENDING ${pending.entries} 次，最近 ${pending.latestIso}。`;
  }
  if (Number(auditRows) === 0) return '当前 canary/order audit 为 0，未发现真钱订单审计行；D:\\polymarket 当前为空目录。';
  return '当前没有可核验的真钱进行中持仓。';
});

function marketTitle(row) {
  return first(row?.market, row?.title, row?.question, row?.eventTitle, row?.slug, row?.marketId);
}

function marketCategory(row) {
  return String(first(row?.category, row?.marketType, row?.source, '其他')).toLowerCase();
}

function marketCategoryLabel(row) {
  const category = marketCategory(row);
  const labels = {
    sports: '体育',
    politics: '政治',
    crypto: '加密',
    finance: '金融',
    elections: '选举',
    macro: '宏观',
    gamma: 'Gamma',
    radar: '雷达',
    history: '历史',
    other: '其他',
    其他: '其他'
  };
  return labels[category] || category.toUpperCase();
}

function marketProbability(row) {
  return asNumber(first(row?.probability, row?.marketProbability, row?.marketProbabilityPct, row?.yesPrice, row?.bestProbability));
}

function marketAiProbability(row) {
  return asNumber(first(row?.aiProbability, row?.aiProbabilityPct, row?.aiPredictedProbability, row?.analysis?.aiProbabilityPct));
}

function marketScore(row) {
  return asNumber(first(row?.aiRuleScore, row?.score, row?.ruleScore, row?.aiScore, row?.opportunityScore)) ?? 0;
}

function marketVolume(row) {
  return asNumber(first(row?.volume24h, row?.volume, row?.volumeUsd, row?.liquidity, row?.liquidityUsd)) ?? 0;
}

function marketDivergence(row) {
  const explicit = asNumber(first(row?.divergence, row?.divergencePct, row?.absDivergence));
  if (explicit !== null) return explicit;
  const ai = marketAiProbability(row);
  const market = marketProbability(row);
  return ai !== null && market !== null ? ai - market : null;
}

function marketRiskTone(row) {
  const risk = String(first(row?.risk, row?.riskLevel, row?.macroRiskState, '')).toLowerCase();
  if (risk.includes('high') || risk.includes('red')) return 'red';
  if (risk.includes('medium') || risk.includes('yellow')) return 'amber';
  if (risk.includes('low') || risk.includes('green')) return 'green';
  return 'blue';
}

function dedupeMarkets(rows) {
  const seen = new Set();
  return rows.filter((row) => {
    const key = String(first(row?.marketId, row?.slug, row?.question, row?.title, row?.market, '')).toLowerCase();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

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

const polyMarketUniverse = computed(() => dedupeMarkets([
  ...arrayFrom(poly.value.markets, ['markets', 'marketCatalog', 'rows']),
  ...arrayFrom(poly.value.radar, ['radar', 'markets', 'rows']),
  ...arrayFrom(poly.value.assets, ['opportunities', 'rows']),
  ...aiScores.value
]));

const polyCategoryOptions = computed(() => {
  const counts = new Map();
  for (const row of polyMarketUniverse.value) {
    const label = marketCategory(row);
    counts.set(label, (counts.get(label) || 0) + 1);
  }
  return ['全部', ...Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 7)
    .map(([label]) => label)]
    .map((label) => ({
      label,
      display: label === '全部' ? '全部' : marketCategoryLabel({ category: label }),
      count: label === '全部' ? polyMarketUniverse.value.length : (counts.get(label) || 0)
    }));
});

const polySortOptions = ['机会评分', '24h 成交', '概率偏离', '流动性'];

const polyVisibleMarkets = computed(() => {
  const rows = polyMarketUniverse.value
    .filter((row) => polyCategoryFilter.value === '全部' || marketCategory(row) === polyCategoryFilter.value);
  const sorted = [...rows].sort((a, b) => {
    if (polySortMode.value === '24h 成交') return marketVolume(b) - marketVolume(a);
    if (polySortMode.value === '概率偏离') return Math.abs(marketDivergence(b) ?? 0) - Math.abs(marketDivergence(a) ?? 0);
    if (polySortMode.value === '流动性') {
      return (asNumber(first(b.liquidity, b.liquidityUsd, b.clobLiquidityUsd)) ?? 0)
        - (asNumber(first(a.liquidity, a.liquidityUsd, a.clobLiquidityUsd)) ?? 0);
    }
    return marketScore(b) - marketScore(a);
  });
  return sorted.slice(0, 12);
});

const singleAnalysis = computed(() => poly.value.singleAnalysis || {});

const singleAnalysisCards = computed(() => {
  const analysis = singleAnalysis.value.analysis || {};
  const market = singleAnalysis.value.market || {};
  return [
    { label: '市场概率', value: pctPoint(first(analysis.marketProbabilityPct, market.probability, market.yesPrice)), detail: first(market.probabilitySource, 'Gamma / CLOB') },
    { label: 'AI 概率', value: pctPoint(first(analysis.aiProbabilityPct, analysis.aiPredictedProbability)), detail: cleanInlineStatusText(first(analysis.aiScoringMode, singleAnalysis.value.mode, '规则/AI')) },
    { label: '偏离度', value: pctPoint(first(analysis.divergencePct, marketDivergence(market))), detail: cleanInlineStatusText(first(analysis.recommendation, '观察')) },
    { label: '信心', value: pctPoint(first(analysis.confidencePct, analysis.confidenceScore)), detail: cleanInlineStatusText(first(analysis.riskLevel, singleAnalysis.value.summary?.risk, 'risk --')) }
  ];
});

const singleHistoryRows = computed(() => [
  ...arrayFrom(poly.value.ledgers?.singleAnalysis),
  ...arrayFrom(poly.value.history?.recent, ['analyses']),
  ...arrayFrom(poly.value.history, ['analyses', 'rows'])
].slice(0, 10));

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
      badge: cleanInlineStatusText(first(latestRoute?.feedback?.actionLabel, latestRoute?.recommendedAction, '--')),
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
      badge: cleanInlineStatusText(first(poly.value.radar?.status, 'OK')),
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
  state: compactStatusLabel(first(card.payload?.status, card.payload?.mode, card.payload?.summary?.status, card.payload?._api?.service, '--')),
  note: first(card.payload?.note, card.payload?.summary?.latestStopReason, card.payload?.summary?.topCandidateId, card.payload?.decisionGate, '--')
})));

const activeWorkspaceMeta = computed(() => workspaces.find((item) => item.id === state.active) || workspaces[0]);

const primaryRoute = computed(() => mt5Routes.value.find((row) => routeHasOpenPosition(row))
  || mt5Routes.value.find((row) => routeIsRuntimeLive(row))
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
      title: first(route.label, route.route, route.strategy, '等待路线'),
      meta: `PF ${first(route.liveForward?.profitFactor, route.profitFactor, '--')} · 胜率 ${pct(first(route.liveForward?.winRatePct, route.winRate))}`,
      tone: routeToneClass(route) || 'blue',
      target: 'mt5'
    },
    {
      label: '参数实验',
      title: first(topTask.candidateId, topTask.versionId, '等待队列'),
      meta: `${compactStatusLabel(first(topTask.state, topTask.status, '仅回测'))} · 评分 ${compactMetricScore(topTask.score, topTask.grade, topTask.profitFactor)}`,
      tone: normalizeParamState(topTask).includes('RED') ? 'red' : normalizeParamState(topTask).includes('WAIT') ? 'amber' : 'blue',
      target: 'paramlab'
    }
  ];
  const polyCards = [
    {
      label: 'Polymarket 雷达',
      title: first(radar.market, radar.title, radar.question, '等待市场'),
      meta: `概率 ${pct(first(radar.probability, radar.marketProbability))} · 评分 ${first(radar.aiRuleScore, radar.score, '--')}`,
      tone: 'green',
      target: 'polymarket'
    },
    {
      label: 'AI 评分',
      title: first(score.market, score.title, score.marketId, '历史评分'),
      meta: `评分 ${first(score.aiScore, score.score, score.grade, '--')} · 风险 ${cleanInlineStatusText(first(score.risk, score.riskLevel, '--'))}`,
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
      title: first(topTask.candidateId, topTask.versionId, '等待队列'),
      meta: `${compactStatusLabel(first(topTask.state, topTask.status, 'tester-only'))} · 评分 ${compactMetricScore(topTask.score, topTask.grade, topTask.profitFactor)}`,
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
      title: recoveryRiskValue(mt5.value.runRecovery),
      meta: recoveryRiskDetail(mt5.value.runRecovery),
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
  if (state.active === 'ai') return [...polyCards.slice(0, 3), ...mt5Cards.slice(0, 2), paramCards[0]];
  return [...mt5Cards, ...polyCards.slice(0, 2), paramCards[paramCards.length - 1]];
});

const aiEngineCards = computed(() => {
  const topScore = aiScores.value[0] || {};
  const topRadar = radarRows.value[0] || {};
  const topRoute = primaryRoute.value;
  const topTask = paramVisibleTasks.value[0] || {};
  return [
    {
      label: 'AI 市场分析',
      value: first(topScore.score, topScore.aiScore, '--'),
      detail: shortText(cleanInlineStatusText(first(topScore.recommendation, topScore.action, topScore.risk, '等待 Polymarket AI 评分')), 42),
      tone: marketRiskTone(topScore)
    },
    {
      label: '机会雷达',
      value: pctPoint(first(topRadar.probability, topRadar.marketProbability)),
      detail: shortText(first(topRadar.market, topRadar.title, topRadar.question, '等待 Gamma 雷达'), 42),
      tone: 'green'
    },
    {
      label: 'MT5 路线',
      value: shortText(first(topRoute.route, topRoute.strategy, topRoute.label, '--'), 18),
      detail: `PF ${first(topRoute.liveForward?.profitFactor, topRoute.profitFactor, '--')} / ${routeActionLabel(topRoute)}`,
      tone: routeToneClass(topRoute) || 'blue'
    },
    {
      label: '回测反馈',
      value: compactMetricScore(topTask.score, topTask.grade, topTask.profitFactor),
      detail: shortText(
        topTask.state || topTask.status
          ? compactStatusLabel(first(topTask.state, topTask.status))
          : first(topTask.candidateId, '等待 ParamLab 候选'),
        42
      ),
      tone: normalizeParamState(topTask).includes('WAIT') ? 'amber' : 'blue'
    }
  ];
});

const aiInsightRows = computed(() => [
  ...searchGroups.value.map((row) => ({
    source: aiSourceLabel(first(row.source, row.type, '综合搜索')),
    title: first(row.title, row.market, row.question, row.marketId),
    detail: compactInsightDetail(first(row.summary, row.reason, row.recommendation, row.decision)),
    tone: marketRiskTone(row),
    target: 'polymarket'
  })),
  ...aiScores.value.map((row) => ({
    source: 'AI',
    title: marketTitle(row),
    detail: `评分 ${first(row.score, row.aiScore, '--')} · ${cleanInlineStatusText(first(row.recommendation, row.action, row.risk, '观察'))}`,
    tone: marketRiskTone(row),
    target: 'polymarket'
  })),
  ...paramVisibleTasks.value.slice(0, 4).map((row) => ({
    source: '参数',
    title: first(row.candidateId, row.versionId, row.taskId),
    detail: `${compactStatusLabel(first(row.state, row.status, 'tester-only'))} · 评分 ${compactMetricScore(row.score, row.grade, row.profitFactor)}`,
    tone: normalizeParamState(row).includes('RED') ? 'red' : normalizeParamState(row).includes('WAIT') ? 'amber' : 'blue',
    target: 'paramlab'
  })),
  ...mt5Routes.value.slice(0, 4).map((row) => ({
    source: routeShortName(row),
    title: first(row.label, row.route, row.strategy, row.versionId),
    detail: `${routeActionLabel(row)} · blocker ${routeBlockerText(row)}`,
    tone: routeToneClass(row) || 'blue',
    target: 'mt5'
  }))
].slice(0, 12));

const aiProviderCards = computed(() => [
  {
    title: '即时分析',
    body: '汇总 MT5 路线、ParamLab 结果、Polymarket Gamma 与历史 AI score，输出可审计建议。',
    tag: 'Instant Analysis',
    target: 'reports'
  },
  {
    title: '机会雷达',
    body: '像 QuantDinger 的 radar 一样横向扫描市场，但当前只做研究和 shadow track，不写钱包。',
    tag: 'Opportunity Radar',
    target: 'polymarket'
  },
  {
    title: '回测反馈',
    body: '把 ParamLab 的 PF、胜率、净收益、回撤和失败原因转成下一轮参数建议。',
    tag: 'Backtest Feedback',
    target: 'paramlab'
  },
  {
    title: '历史记忆',
    body: '保存单市场分析、综合证据卡和执行模拟后验，后续用于评分校准。',
    tag: 'Analysis Memory',
    target: 'polymarket'
  }
]);

const watchlistItems = computed(() => [
  ...mt5Routes.value.slice(0, 5).map((row) => ({
    title: first(row.label, row.route, row.strategy, row.versionId),
    sub: `${routeShortName(row)} · ${routeActionLabel(row)}`,
    value: `PF ${first(row.liveForward?.profitFactor, row.profitFactor, '--')}`,
    tone: routeToneClass(row) || 'blue',
    target: 'mt5'
  })),
  ...radarRows.value.slice(0, 5).map((row) => ({
    title: first(row.market, row.title, row.question),
    sub: cleanInlineStatusText(first(row.category, row.suggestedShadowTrack, 'Polymarket')),
    value: pct(first(row.probability, row.marketProbability)),
    tone: 'green',
    target: 'polymarket'
  }))
].slice(0, 9));

const actionQueueItems = computed(() => [
  ...paramVisibleTasks.value.slice(0, 5).map((row) => ({
    title: first(row.candidateId, row.versionId, row.taskId),
    sub: `${paramRouteLabel(row)} · ${compactStatusLabel(first(row.state, row.status, row.resultState, '等待'))}`,
    value: compactMetricScore(row.score, row.grade, row.profitFactor),
    tone: normalizeParamState(row).includes('RED') ? 'red' : normalizeParamState(row).includes('WAIT') ? 'amber' : 'blue',
    target: 'paramlab'
  })),
  ...governanceRows.value.slice(0, 3).map((row) => ({
    title: governanceTitle(row),
    sub: `${governanceDecisionLabel(row)} · ${blockerChips(row, 1).join(' / ') || '等待证据'}`,
    value: first(row.score, row.aiScore, row.confidence, '--'),
    tone: 'green',
    target: 'polymarket'
  }))
].slice(0, 8));

onMounted(() => {
  syncActiveFromHash();
  window.addEventListener('hashchange', syncActiveFromHash);
  refresh().finally(() => {
    autoRefreshTimer = window.setInterval(() => {
      if (!state.loading) refresh();
    }, autoRefreshMs);
  });
});

onBeforeUnmount(() => {
  window.removeEventListener('hashchange', syncActiveFromHash);
  if (autoRefreshTimer) window.clearInterval(autoRefreshTimer);
});
</script>

<template>
  <div class="app-shell" :class="{ 'sidebar-collapsed': state.sidebarCollapsed }">
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
        <button
          class="nav-item"
          :class="{ active: state.active === 'ai' }"
          type="button"
          @click="setActive('ai')"
        >
          <Activity :size="18" />
          <span>
            <strong>AI 工作台</strong>
            <small>分析引擎</small>
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
        <div class="topbar-left">
          <button class="icon-button" type="button" :title="state.sidebarCollapsed ? '展开菜单' : '折叠菜单'" @click="handleTopAction('menu')">
            <Menu :size="18" />
          </button>
          <div>
            <p class="eyebrow">{{ activeWorkspaceMeta.sub }}</p>
            <h1>{{ activeWorkspaceMeta.label }}</h1>
            <p class="topbar-subtitle">{{ activeWorkspaceMeta.desc }}</p>
          </div>
        </div>
        <div class="top-actions">
          <label class="search-box">
            <Search :size="16" />
            <input v-model="state.query" type="search" placeholder="搜索市场、路线、候选和证据" @keyup.enter="refresh" />
          </label>
          <button class="icon-button refresh-icon" type="button" title="刷新" @click="refresh">
            <RefreshCw :size="16" :class="{ spin: state.loading }" />
          </button>
          <span class="top-divider"></span>
          <button class="icon-button" type="button" title="证据报表 / 通知" @click="handleTopAction('notifications')">
            <Bell :size="16" />
          </button>
          <button class="icon-button" type="button" title="Polymarket 市场浏览" @click="handleTopAction('market')">
            <Globe2 :size="16" />
          </button>
          <button class="icon-button" type="button" title="ParamLab / 设置" @click="handleTopAction('settings')">
            <Settings :size="16" />
          </button>
        </div>
      </header>

      <div v-if="state.active === 'home'" class="operator-strip">
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
        <article class="qd-radar-section">
          <div class="qd-radar-header">
            <div>
              <h2>AI Opportunity Radar</h2>
              <p>按 QuantDinger 的首屏节奏，把 MT5、ParamLab、Polymarket 的可行动证据横向扫一遍。</p>
            </div>
            <button class="ghost-button small" type="button" @click="refresh">
              <RefreshCw :size="14" :class="{ spin: state.loading }" />
              刷新
            </button>
          </div>
          <div class="qd-radar-track">
            <button
              v-for="card in operatorRadarCards"
              :key="`home-${card.label}`"
              type="button"
              class="qd-radar-card"
              :class="card.tone"
              @click="setActive(card.target)"
            >
              <div class="qd-card-head">
                <strong>{{ card.title }}</strong>
                <span>{{ card.label }}</span>
              </div>
              <div class="qd-card-metrics">
                <span>
                  <small>状态</small>
                  <b>{{ card.tone === 'green' ? '强' : card.tone === 'amber' ? '观察' : card.tone === 'red' ? '风险' : '待判定' }}</b>
                </span>
                <span>
                  <small>证据</small>
                  <b>{{ card.meta }}</b>
                </span>
              </div>
              <p>{{ card.meta }}</p>
            </button>
          </div>
        </article>

        <article class="qd-workspace-card">
          <div class="workspace-tabs">
            <button class="active" type="button"><Activity :size="15" />即时分析</button>
            <button type="button" @click="setActive('polymarket', 'radar')"><Target :size="15" />预测市场</button>
            <button type="button" @click="setActive('paramlab')"><ClipboardList :size="15" />回测队列</button>
          </div>
          <div class="qd-analysis-grid">
            <aside class="asset-pool-mini">
              <div class="pool-tabs">
                <span>MT5</span>
                <span>ParamLab</span>
                <span>Poly</span>
              </div>
              <button v-for="item in watchlistItems.slice(0, 6)" :key="`pool-${item.title}`" type="button" :class="item.tone" @click="setActive(item.target)">
                <strong>{{ item.title }}</strong>
                <small>{{ item.sub }}</small>
                <b>{{ item.value }}</b>
              </button>
            </aside>
            <div class="analysis-console qd-console-compact">
              <div class="console-grid-bg"></div>
              <div class="console-core">
                <span>AI-POWERED</span>
                <h2>QuantGod Analysis Engine</h2>
                <p>多源证据驱动：MT5 实盘样本、Strategy Tester、Polymarket Gamma、历史库与治理建议。</p>
                <div class="console-actions">
                  <button type="button" @click="setActive('mt5')"><Plus :size="14" />MT5 详情</button>
                  <button type="button" @click="setActive('polymarket', 'analysis')">单市场分析</button>
                  <button type="button" @click="setActive('reports')">证据报表</button>
                </div>
              </div>
            </div>
            <aside class="qd-watchlist-panel">
              <div class="rail-title">
                <span><Layers :size="15" /> My Watchlist</span>
                <small>{{ watchlistItems.length }} 项</small>
              </div>
              <button v-for="item in watchlistItems.slice(0, 7)" :key="`home-watch-${item.title}`" class="rail-item compact" :class="item.tone" type="button" @click="setActive(item.target)">
                <span>
                  <strong>{{ item.title }}</strong>
                  <small>{{ item.sub }}</small>
                </span>
                <b>{{ item.value }}</b>
              </button>
              <div class="calendar-mini">
                <div class="calendar-mini-title"><CalendarDays :size="14" /> 今日待办</div>
                <button
                  v-for="item in actionQueueItems.slice(0, 3)"
                  :key="`cal-${item.title}`"
                  type="button"
                  class="calendar-mini-item"
                  :class="item.tone"
                  :title="`${item.title} · ${item.sub}`"
                  @click="setActive(item.target)"
                >
                  <strong>{{ item.title }}</strong>
                  <small>
                    {{ item.sub }}
                    <b v-if="item.value && item.value !== '--'">{{ item.value }}</b>
                  </small>
                </button>
              </div>
            </aside>
          </div>
        </article>

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

      <section v-if="state.active === 'ai'" class="stack page-ai">
        <article class="qd-radar-section ai-radar-section">
          <div class="qd-radar-header">
            <div>
              <h2>AI Opportunity Radar</h2>
              <p>像 QuantDinger 首屏一样先看横向机会，再进入单市场、ParamLab 或路线证据。</p>
            </div>
            <button class="ghost-button small" type="button" @click="refresh">
              <RefreshCw :size="14" :class="{ spin: state.loading }" />
              刷新
            </button>
          </div>
          <div class="qd-radar-track ai-radar-track">
            <button
              v-for="card in operatorRadarCards"
              :key="`ai-radar-${card.label}`"
              type="button"
              class="qd-radar-card"
              :class="card.tone"
              @click="setActive(card.target)"
            >
              <div class="qd-card-head">
                <strong>{{ card.title }}</strong>
                <span>{{ card.label }}</span>
              </div>
              <div class="qd-card-metrics">
                <span>
                  <small>状态</small>
                  <b>{{ card.meta }}</b>
                </span>
                <span>
                  <small>动作</small>
                  <b>{{ card.tone === 'red' ? '先处理风险' : card.tone === 'amber' ? '等待证据' : '可继续研究' }}</b>
                </span>
              </div>
              <p>{{ card.target === 'polymarket' ? 'Gamma / AI score / dry-run 证据' : card.target === 'paramlab' ? 'tester-only 参数闭环' : 'MT5 只读与路线治理' }}</p>
            </button>
          </div>
        </article>

        <div class="workbench-hero ai-hero">
          <article class="hero-copy">
            <div class="panel-title split">
              <span class="eyebrow">AI Analysis Engine / 独立工作台</span>
              <b class="pill blue">RESEARCH ONLY</b>
            </div>
            <h2>即时分析、机会雷达、历史记忆与回测反馈</h2>
            <p>
              按 QuantDinger 的 AI 系列入口重排，但保留 QuantGod 边界：AI 只读汇总证据、解释风险、提出下一步参数/市场建议，不直接改 MT5、不写 Polymarket 钱包。
            </p>
            <div class="console-actions left-actions">
              <button type="button" @click="setActive('polymarket', 'radar')"><Target :size="14" />机会雷达</button>
              <button type="button" @click="setActive('polymarket', 'analysis')">单市场分析</button>
              <button type="button" @click="setActive('paramlab')">回测反馈</button>
            </div>
          </article>
          <article class="ai-status-grid">
            <div v-for="card in aiEngineCards" :key="card.label" class="ai-status-card" :class="card.tone">
              <span>{{ card.label }}</span>
              <strong>{{ card.value }}</strong>
              <small>{{ card.detail }}</small>
            </div>
          </article>
        </div>

        <article class="ai-engine-shell">
          <aside class="ai-feature-rail">
            <button
              v-for="item in aiProviderCards"
              :key="item.title"
              type="button"
              class="ai-feature-card"
              @click="setActive(item.target)"
            >
              <span>{{ item.tag }}</span>
              <strong>{{ item.title }}</strong>
              <small>{{ item.body }}</small>
            </button>
          </aside>

          <div class="analysis-console ai-console">
            <div class="console-grid-bg"></div>
            <div class="console-core">
              <span>AI-POWERED</span>
              <h2>QuantGod AI 研究引擎</h2>
              <p>把市场概率、MT5 route blocker、ParamLab 分数、历史分析和执行模拟后验压缩成一张研究决策面板。</p>
              <div class="inline-form ai-query-form">
                <input v-model="state.query" type="search" placeholder="输入市场、品种、路线或候选 ID 后刷新证据" @keyup.enter="refresh" />
                <button type="button" @click="refresh">刷新证据</button>
              </div>
            </div>
          </div>

          <aside class="ai-watch-rail">
            <div class="rail-title">
              <span><Layers :size="15" /> AI Watchlist</span>
              <small>{{ aiInsightRows.length }} 条</small>
            </div>
            <button
              v-for="row in aiInsightRows.slice(0, 7)"
              :key="`${row.source}-${row.title}`"
              type="button"
              class="rail-item compact ai-watch-item"
              :class="row.tone"
              :title="`${row.title} · ${row.detail}`"
              @click="setActive(row.target)"
            >
              <span>
                <strong>{{ row.title }}</strong>
                <small>{{ row.detail }}</small>
                <em>{{ row.source }}</em>
              </span>
            </button>
            <div v-if="!aiInsightRows.length" class="rail-empty">等待 AI 历史、雷达或 ParamLab 证据。</div>
          </aside>
        </article>

        <div class="card-grid three">
          <article class="panel dense">
            <div class="panel-title split">
              <span>Polymarket AI 研究</span>
              <small>{{ aiScores.length }} score</small>
            </div>
            <div class="poly-score-stack">
              <div v-for="row in aiScores.slice(0, 4)" :key="first(row.marketId, row.title, row.question)" class="score-line">
                <strong>{{ shortText(marketTitle(row), 70) }}</strong>
                <span>评分 {{ first(row.score, row.aiScore, '--') }} · {{ cleanInlineStatusText(first(row.recommendation, row.action, row.risk, '观察')) }}</span>
              </div>
              <div v-if="!aiScores.length" class="rail-empty">暂无 AI score。</div>
            </div>
          </article>
          <article class="panel dense">
            <div class="panel-title split">
              <span>MT5 路线解释</span>
              <small>{{ mt5Routes.length }} route</small>
            </div>
            <div class="lane-stack ai-route-stack">
              <button v-for="lane in mt5RouteLaneCards" :key="`ai-${lane.route}`" class="lane-row" :class="lane.tone" type="button" @click="setActive('mt5', 'strategy')">
                <strong>{{ lane.route }}</strong>
                <span>{{ lane.count }} 版本 · live {{ lane.live }}</span>
                <small>{{ lane.blocker }}</small>
              </button>
            </div>
          </article>
          <article class="panel dense">
            <div class="panel-title split">
              <span>下一步队列</span>
              <small>{{ actionQueueItems.length }} item</small>
            </div>
            <div class="history-list">
              <button v-for="item in actionQueueItems.slice(0, 5)" :key="`ai-action-${item.title}`" type="button" @click="setActive(item.target)">
                <strong>{{ item.title }}</strong>
                <span>{{ item.sub }} · {{ item.value }}</span>
              </button>
              <div v-if="!actionQueueItems.length" class="rail-empty">暂无待处理建议。</div>
            </div>
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

        <div v-if="state.mt5Focus === 'strategy'" class="toolbar dense-toolbar">
          <div>
            <p class="eyebrow">路线筛选</p>
            <h2>路线筛选与证据详情</h2>
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

        <div v-if="state.mt5Focus === 'overview'" class="mt5-command-grid">
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

        <div v-if="state.mt5Focus === 'trades'" class="qd-terminal-layout mt5-trade-workbench">
          <aside class="panel dense qd-left-list">
            <div class="panel-title split">
              <span>持仓列表</span>
              <b class="pill green">{{ mt5Positions.length }} 单</b>
            </div>
            <div class="account-strip">
              <span>
                <small>服务器</small>
                <strong>{{ first(mt5Account.server, 'HFM 只读桥') }}</strong>
              </span>
              <span>
                <small>净值</small>
                <strong>{{ money(first(mt5Account.equity, mt5.latest?.equity)) }}</strong>
              </span>
            </div>
            <div class="position-list">
              <button
                v-for="row in mt5Positions"
                :key="first(positionTicket(row), row.timeIso)"
                type="button"
                class="position-row"
              >
                <span>
                  <strong>{{ first(row.symbol, row.Symbol) }}</strong>
                  <small>#{{ positionTicket(row) || 'open' }} · {{ positionDirection(row) }} · {{ first(row.comment, row.route, row.strategy, 'EA / manual') }}</small>
                </span>
                <b :class="{ loss: asNumber(positionProfit(row)) < 0 }">
                  {{ money(positionProfit(row)) }}
                </b>
              </button>
              <div v-if="!mt5Positions.length" class="rail-empty">当前无持仓；实盘历史在下方“平仓记录”表。</div>
            </div>
          </aside>

          <section class="panel dense qd-center-stage trade-focus-card">
            <div class="panel-title split">
              <span>交易只读工作台</span>
              <b class="pill blue">READ ONLY</b>
            </div>
            <div class="trade-ticket-head">
              <div>
                <p class="eyebrow">当前焦点持仓</p>
                <h2>{{ first(focusedPosition.symbol, focusedPosition.Symbol, '暂无持仓') }}</h2>
                <small>{{ first(focusedPosition.comment, focusedPosition.route, focusedPosition.strategy, '等待持仓证据') }}</small>
              </div>
              <strong :class="{ loss: asNumber(positionProfit(focusedPosition)) < 0 }">
                {{ money(positionProfit(focusedPosition)) }}
              </strong>
            </div>
            <div class="trade-metric-grid">
              <span><small>方向</small><b>{{ positionDirection(focusedPosition) }}</b></span>
              <span><small>手数</small><b>{{ first(focusedPosition.volume, focusedPosition.lots, focusedPosition.Volume, '--') }}</b></span>
              <span><small>开仓</small><b>{{ first(focusedPosition.priceOpen, focusedPosition.price_open, focusedPosition.openPrice, '--') }}</b></span>
              <span><small>现价</small><b>{{ positionCurrentPrice(focusedPosition) }}</b></span>
              <span><small>SL</small><b>{{ first(focusedPosition.sl, focusedPosition.stopLoss, '--') }}</b></span>
              <span><small>TP</small><b>{{ first(focusedPosition.tp, focusedPosition.takeProfit, '--') }}</b></span>
            </div>
            <div class="readonly-action-strip">
              <button type="button" class="locked-action">下单锁定</button>
              <button type="button" class="locked-action">手动强平锁定</button>
              <button type="button" class="ghost-button small" @click="setActive('reports')">查看审计报表</button>
            </div>
          </section>

          <aside class="panel dense qd-right-rail trade-audit-rail">
            <div class="panel-title split">
              <span>风险与审计</span>
              <b class="pill amber">ledger</b>
            </div>
            <div class="audit-stack">
              <div class="audit-row">
                <small>交易边界</small>
                <strong>0.01 pilot / 单仓 / 只读页面</strong>
                <span>页面不触发 order-send，也不改变 live switch。已合并重复来源 {{ duplicatedPositionEvidence }} 条。</span>
              </div>
              <div class="audit-row">
                <small>焦点路线</small>
                <strong>{{ routeShortName(primaryRoute) }} · {{ routeActionLabel(primaryRoute) }}</strong>
                <span>{{ shortText(routeWhyText(primaryRoute), 120) }}</span>
              </div>
              <div class="audit-row">
                <small>主要 blocker</small>
                <strong>{{ routeBlockerText(primaryRoute) }}</strong>
                <span>需要回看完整 ledger 时进入证据报表。</span>
              </div>
            </div>
            <div class="history-list compact-history">
              <button v-for="row in tradingAuditRows.slice(0, 4)" :key="first(row.time, row.ticket, row.eventId)" type="button">
                <strong>{{ shortText(`${auditActionText(row)} · ${auditScope(row)}`, 48) }}</strong>
                <span>{{ shortText(`${auditTime(row)} · ${auditReasonText(row, 2)}`, 56) }}</span>
              </button>
              <div v-if="!tradingAuditRows.length" class="rail-empty">暂无交易审计 ledger 行。</div>
            </div>
          </aside>
        </div>

        <div v-if="state.mt5Focus === 'strategy'" class="qd-terminal-layout strategy-workbench">
          <aside class="panel dense qd-left-list route-tree-panel">
            <div class="panel-title split">
              <span>路线树</span>
              <b class="pill blue">MA / RSI / BB / MACD / SR</b>
            </div>
            <div class="lane-stack route-tree">
              <button
                v-for="lane in mt5RouteLaneCards"
                :key="lane.route"
                class="lane-row"
                :class="[lane.tone, { selected: activeRoute === lane.route }]"
                type="button"
                @click="activeRoute = lane.route"
              >
                <strong>{{ lane.route }}</strong>
                <span>{{ lane.count }} 版本 · live {{ lane.live }}</span>
                <small>PF {{ lane.pf }} · {{ lane.blocker }}</small>
              </button>
            </div>
          </aside>

          <section class="panel dense qd-center-stage strategy-stage">
            <div class="panel-title split">
              <span>策略路线工作台</span>
              <b class="pill" :class="routeToneClass(primaryRoute)">{{ routeActionLabel(primaryRoute) }}</b>
            </div>
            <div class="strategy-focus-head">
              <div>
                <p class="eyebrow">{{ routeShortName(primaryRoute) }}</p>
                <h2>{{ first(primaryRoute.label, primaryRoute.route, primaryRoute.strategy, primaryRoute.name, primaryRoute.versionId, '等待路线证据') }}</h2>
                <small>{{ shortText(routeWhyText(primaryRoute), 150) }}</small>
              </div>
              <button class="ghost-button small" type="button" @click="setActive('paramlab')">ParamLab</button>
            </div>
            <div class="strategy-performance-grid">
              <span><small>Forward PF</small><b>{{ first(primaryRoute.liveForward?.profitFactor, primaryRoute.profitFactor, primaryRoute.pf, '--') }}</b></span>
              <span><small>胜率</small><b>{{ pct(first(primaryRoute.liveForward?.winRatePct, primaryRoute.winRate, primaryRoute.win_rate)) }}</b></span>
              <span><small>已平仓样本</small><b>{{ first(primaryRoute.liveForward?.closedTrades, primaryRoute.liveForward?.trades, '--') }}</b></span>
              <span><small>净收益</small><b>{{ money(primaryRoute.liveForward?.netProfitUSC) }}</b></span>
              <span><small>候选样本</small><b>{{ first(primaryRoute.candidateSamples?.rows, primaryRoute.candidateSamples?.ledgerRows, '--') }}</b></span>
              <span><small>阻断</small><b>{{ shortText(routeBlockerText(primaryRoute), 36) }}</b></span>
            </div>
            <div class="strategy-version-strip">
              <span>参数候选：{{ routeParamText(primaryRoute) }}</span>
              <span class="strategy-advice">下一步：{{ cleanInlineStatusText(first(primaryRoute.feedback?.nextStep, primaryRoute.paramLabResult?.promotionReadiness, primaryRoute.recommendedAction, '等待下一步建议')) }}</span>
            </div>
          </section>

          <aside class="panel dense qd-right-rail strategy-evidence-rail">
            <div class="panel-title split">
              <span>证据轨</span>
              <b class="pill amber">只读</b>
            </div>
            <div class="history-list compact-history">
              <button v-for="row in mt5Routes.slice(0, 6)" :key="first(row.versionId, row.route, row.name)" type="button">
                <strong>{{ shortText(first(row.label, row.route, row.strategy, row.name, row.versionId), 52) }}</strong>
                <span>PF {{ first(row.liveForward?.profitFactor, row.profitFactor, row.pf, '--') }} · {{ routeActionLabel(row) }}</span>
              </button>
              <div v-if="!mt5Routes.length" class="rail-empty">当前没有可展示的 MT5 路线证据。</div>
            </div>
          </aside>
        </div>

        <DataTable
          v-if="state.mt5Focus === 'trades'"
          title="EA / 手动持仓快照"
          dense
          :rows="mt5Positions"
          :columns="[
            { label: '品种', key: ['symbol', 'Symbol'], width: '112px', class: 'col-strong' },
            { label: '方向', value: positionDirection, width: '84px', badge: true },
            { label: '手数', value: (r) => first(r.volume, r.lots, r.Volume), width: '74px', class: 'col-number' },
            { label: '开仓价', value: (r) => first(r.price_open, r.openPrice, r.priceOpen), width: '104px', class: 'col-number' },
            { label: '现价', value: positionCurrentPrice, width: '104px', class: 'col-number' },
            {
              label: '浮盈',
              value: (r) => money(positionProfit(r)),
              tone: (r) => {
                const value = asNumber(positionProfit(r));
                if (value < 0) return 'pnl-negative';
                if (value > 0) return 'pnl-positive';
                return 'pnl-flat';
              },
              width: '96px',
              class: 'col-pnl'
            },
            { label: '策略/备注', value: (r) => first(r.comment, r.route, r.strategy), max: 120 }
          ]"
          empty="当前没有 MT5 持仓；查看下方“实盘平仓记录”可回看历史。"
        />

        <DataTable
          v-if="state.mt5Focus === 'trades'"
          title="实盘平仓记录 / Closed Trades"
          dense
          :rows="mt5ClosedTrades"
          :columns="[
            { label: '平仓时间', value: (r) => compactIsoTime(first(r.closeTime, r.CloseTime, r.timeClose, r.close_time)), width: '136px' },
            { label: '票据', value: (r) => compactId(first(r.ticket, r.Ticket, r.positionId, r.deal), 12), width: '96px' },
            { label: '品种', value: (r) => first(r.symbol, r.Symbol), width: '98px', class: 'col-strong' },
            { label: '方向', value: positionDirection, width: '82px', badge: true },
            { label: '手数', value: (r) => first(r.lots, r.actualLots, r.volume, r.Volume), width: '74px', class: 'col-number' },
            { label: '开仓价', value: (r) => first(r.openPrice, r.priceOpen, r.price_open), width: '92px', class: 'col-number' },
            { label: '平仓价', value: (r) => first(r.closePrice, r.priceClose, r.price_close), width: '92px', class: 'col-number' },
            {
              label: '盈亏',
              value: (r) => money(positionProfit(r)),
              tone: (r) => pnlTone(positionProfit(r)),
              width: '86px',
              class: 'col-pnl'
            },
            { label: '策略', value: (r) => cleanInlineStatusText(first(r.strategy, r.route, r.comment)), width: '124px' },
            { label: '持仓时长', value: (r) => first(r.durationMinutes, r.duration, '--') === '--' ? '--' : `${first(r.durationMinutes, r.duration)}m`, width: '92px' },
            { label: '开仓时间', value: (r) => compactIsoTime(first(r.openTime, r.OpenTime, r.timeOpen, r.open_time)), width: '136px' }
          ]"
          empty="当前没有实盘平仓记录；/api/latest closedTrades 暂无返回。"
        />

        <DataTable
          v-if="state.mt5Focus === 'trades'"
          title="MT5 桥接审计 / EA 交易记录"
          dense
          :rows="tradingAuditRows"
          :columns="[
            { label: '时间', value: auditTime, width: '142px' },
            { label: '记录', value: auditRecordId, width: '108px' },
            { label: '范围', value: auditScope, width: '118px', class: 'col-strong' },
            { label: '动作', value: auditActionText, width: '104px', badge: true },
            { label: '方向', value: auditDirectionText, width: '92px', badge: true },
            { label: '手数', value: auditLotsText, width: '76px', class: 'col-number' },
            { label: '价格', value: auditPriceText, width: '86px', class: 'col-number' },
            { label: '路线', value: auditRouteText, width: '118px' },
            {
              label: '盈亏',
              value: auditProfitText,
              tone: (r) => pnlTone(auditProfit(r)),
              width: '94px',
              class: 'col-pnl'
            },
            { label: '决策', value: auditDecisionText, width: '104px', badge: true },
            { label: '主要原因', value: (r) => auditReasonText(r), max: 132 }
          ]"
          empty="暂无 MT5 桥接审计记录；等待 trading audit ledger 刷新。"
        />

        <div v-if="state.mt5Focus === 'trades'" class="card-grid three trade-summary-grid">
          <article class="panel dense">
            <div class="panel-title split">
              <span>交易边界</span>
              <b class="pill green">只读</b>
            </div>
            <p class="summary-line">只看 EA / 人工单快照；不下单、不强平、不改 live switch。</p>
            <div class="mini-row">
              <span>持仓 {{ mt5Positions.length }}</span>
              <span>最大单仓 {{ first(mt5.snapshot?.maxTotalPositions, mt5.snapshot?.risk?.maxTotalPositions, 1) }}</span>
              <span>手数 0.01</span>
            </div>
          </article>
          <article class="panel dense">
            <div class="panel-title split">
              <span>当前焦点路线</span>
              <b class="pill blue">{{ routeActionLabel(primaryRoute) }}</b>
            </div>
            <p class="summary-line">{{ shortText(routeWhyText(primaryRoute), 92) }}</p>
            <div class="mini-row secondary">
              <span>{{ routeShortName(primaryRoute) }}</span>
              <span>PF {{ first(primaryRoute.liveForward?.profitFactor, primaryRoute.profitFactor, '--') }}</span>
              <span>{{ shortText(routeBlockerText(primaryRoute), 42) }}</span>
            </div>
          </article>
          <article class="panel dense">
            <div class="panel-title split">
              <span>审计入口</span>
              <b class="pill amber">ledger</b>
            </div>
            <p class="summary-line">完整 ledger / shadow / outcome 在证据报表；这里保留交易页快照。</p>
            <button class="ghost-button small" type="button" @click="setActive('reports')">打开证据报表</button>
          </article>
        </div>

        <div v-if="state.mt5Focus === 'strategy'" class="strategy-card-grid">
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
              <span>{{ cleanInlineStatusText(first(row.mode, row.live ? 'LIVE_0_01' : 'SIM/CANDIDATE')) }}</span>
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
            <p class="route-param">下一步：{{ cleanInlineStatusText(first(row.feedback?.nextStep, row.paramLabResult?.promotionReadiness, row.recommendedAction, '等待下一步建议')) }}</p>
          </article>
          <article v-if="!mt5Routes.length" class="panel empty">当前没有可展示的 MT5 路线证据，等待运行文件或只读桥刷新。</article>
        </div>

        <Mt5DeepPanels v-if="state.mt5Focus === 'strategy'" :mt5="mt5" :positions="mt5Positions" :routes="mt5Routes" />
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

        <article class="poly-account-strip" aria-label="Polymarket 账户与执行边界">
          <div
            v-for="card in polyAccountCards"
            :key="card.label"
            class="poly-account-card"
            :class="card.tone"
          >
            <span>{{ card.label }}</span>
            <strong>{{ card.value }}</strong>
            <small>{{ card.detail }}</small>
          </div>
        </article>

        <article v-if="state.polymarketFocus === 'browser'" class="poly-filter-shell">
          <div class="poly-filter-head">
            <div>
              <p class="eyebrow">Prediction Market Browser</p>
              <h2>市场机会池</h2>
            </div>
            <div class="route-tabs compact">
              <button
                v-for="option in polyCategoryOptions"
                :key="option.label"
                type="button"
                :class="{ selected: polyCategoryFilter === option.label }"
                @click="polyCategoryFilter = option.label"
              >
                {{ option.display }} {{ option.count }}
              </button>
            </div>
          </div>
          <div class="poly-filter-row">
            <label class="search-box poly-local-search">
              <Search :size="15" />
              <input v-model="state.query" type="search" placeholder="搜索 Polymarket 市场、事件、风险标签" @keyup.enter="refresh" />
            </label>
            <div class="route-tabs compact">
              <button
                v-for="option in polySortOptions"
                :key="option"
                type="button"
                :class="{ selected: polySortMode === option }"
                @click="polySortMode = option"
              >
                {{ option }}
              </button>
            </div>
          </div>
        </article>

        <div v-if="state.polymarketFocus === 'analysis'" class="single-analysis-workspace">
          <article class="panel single-input-card">
            <div class="panel-title split">
              <span>单市场 AI 分析入口</span>
              <b class="pill blue">本地请求</b>
            </div>
            <p>输入 Polymarket URL、标题或 marketId，只生成研究请求和历史证据；不会触发钱包、不会影响 MT5。</p>
            <div class="inline-form">
              <input v-model="state.marketInput" type="text" placeholder="例如：https://polymarket.com/event/... 或 marketId" @keyup.enter="submitSingleMarket" />
              <button type="button" @click="submitSingleMarket">开始分析</button>
            </div>
            <small>{{ first(state.requestStatus, '等待输入。') }}</small>
          </article>

          <article class="panel single-result-card">
            <div class="panel-title split">
              <span>{{ shortText(first(singleAnalysis.market?.question, singleAnalysis.summary?.market, '最近单市场分析'), 82) }}</span>
              <b class="pill" :class="marketRiskTone(singleAnalysis.analysis || singleAnalysis.summary || {})">
                {{ cleanInlineStatusText(first(singleAnalysis.analysis?.recommendation, singleAnalysis.summary?.recommendation, '观察')) }}
              </b>
            </div>
            <div class="probability-comparison">
              <div v-for="card in singleAnalysisCards" :key="card.label" class="prob-card">
                <span>{{ card.label }}</span>
                <strong>{{ card.value }}</strong>
                <small>{{ card.detail }}</small>
              </div>
            </div>
            <div class="reasoning-box">
              <strong>分析理由</strong>
              <p>{{ shortText(first(singleAnalysis.analysis?.rationale?.join?.(' '), singleAnalysis.analysis?.reasoning, singleAnalysis.analysis?.riskNotes?.join?.(' '), '等待单市场分析结果。'), 260) }}</p>
            </div>
            <div class="factor-row">
              <span v-for="factor in (singleAnalysis.analysis?.keyFactors || []).slice(0, 5)" :key="factor">{{ factor }}</span>
              <span v-if="!(singleAnalysis.analysis?.keyFactors || []).length">暂无关键因子</span>
            </div>
          </article>

          <article class="panel single-history-card">
            <div class="panel-title split">
              <span>历史分析</span>
              <small>{{ singleHistoryRows.length }} 条</small>
            </div>
            <div class="history-list">
              <button v-for="row in singleHistoryRows" :key="first(row.generatedAt, row.marketId, row.question)" type="button">
                <strong>{{ shortText(first(row.question, row.marketTitle, row.title, row.marketId), 76) }}</strong>
                <span>{{ cleanInlineStatusText(first(row.recommendation, row.decision, row.risk, '--')) }} · 偏离 {{ pctPoint(first(row.divergence, row.divergencePct)) }}</span>
                <small>{{ first(row.generatedAt, row.createdAt, row.updatedAt, '--') }}</small>
              </button>
              <div v-if="!singleHistoryRows.length" class="rail-empty">暂无单市场历史。</div>
            </div>
          </article>
        </div>

        <div v-else-if="state.polymarketFocus === 'overview'" class="poly-overview-grid">
          <article class="panel poly-governance-overview">
            <div class="panel-title split">
              <span>治理总览</span>
              <small>账户 / 钱包 / 自动治理边界</small>
            </div>
            <div class="governance-lanes">
              <div v-for="row in governanceRows.slice(0, 5)" :key="first(row.governanceId, row.marketId)" class="governance-lane governance-lane-rich">
                <div class="lane-copy">
                  <strong>{{ governanceTitle(row) }}</strong>
                  <small>{{ governanceDetail(row) }}</small>
                </div>
                <div class="lane-chipset">
                  <b class="status-chip amber">{{ governanceDecisionLabel(row) }}</b>
                  <span v-for="chip in blockerChips(row, 2)" :key="chip" class="status-chip">{{ chip }}</span>
                </div>
              </div>
              <div v-if="!governanceRows.length" class="rail-empty">暂无自动治理建议；保持只读与模拟执行。</div>
            </div>
          </article>
          <article class="panel poly-real-summary">
            <div class="panel-title split">
              <span>真钱执行快照</span>
              <b class="pill blue">只读核验</b>
            </div>
            <div class="poly-real-metric-grid">
              <div
                v-for="card in polyRealSummaryCards"
                :key="card.label"
                class="micro-metric poly-real-metric"
                :class="card.tone"
              >
                <span>{{ card.label }}</span>
                <strong>{{ card.value }}</strong>
                <small>{{ card.detail }}</small>
              </div>
            </div>
            <div class="poly-current-real">
              <div class="panel-title split compact-title">
                <span>当前真钱进行中</span>
                <small>{{ polyCurrentRealRows.length }} 条</small>
              </div>
              <div v-if="polyCurrentRealRows.length" class="history-list poly-real-list">
                <button
                  v-for="row in polyCurrentRealRows"
                  :key="first(row.runId, row.run_id, row.marketId, row.market_id, row.question)"
                  type="button"
                >
                  <strong>{{ first(row.question, row.market, row.title, row.marketId, row.market_id) }}</strong>
                  <span>{{ cleanInlineStatusText(first(row.positionState, row.position_state, row.status, row.state, row.decision, 'open')) }} · {{ first(row.side, row.outcome, row.direction, '--') }} · {{ money(first(row.stakeUSDC, row.stake_usdc, row.stake, row.amount, row.size, '--')) }}</span>
                </button>
              </div>
              <p v-else class="summary-line">{{ polyRealEvidenceNote }}</p>
            </div>
          </article>
          <article class="panel">
            <div class="panel-title split">
              <span>跨市场风险联动</span>
              <small>{{ crossRows.length }} 条</small>
            </div>
            <div class="radar-ticker">
              <div v-for="row in crossRows.slice(0, 5)" :key="first(row.eventTitle, row.marketId)" class="radar-ticker-item risk-link-row">
                <span class="risk-title">{{ shortText(first(row.eventTitle, row.question, row.market, row.marketId), 76) }}</span>
                <div class="lane-chipset">
                  <strong class="status-chip red">{{ crossRiskLabel(row) }}</strong>
                  <span v-for="asset in crossAssetLabels(row)" :key="asset" class="status-chip blue">{{ asset }}</span>
                </div>
                <small>{{ crossDetail(row) }}</small>
              </div>
              <div v-if="!crossRows.length" class="rail-empty">暂无 USD / JPY / XAU / 宏观联动证据。</div>
            </div>
          </article>
          <article class="panel">
            <div class="panel-title split">
              <span>批量扫描 Worker</span>
              <small>{{ workerQueue.length }} 条</small>
            </div>
            <div class="history-list">
              <button v-for="row in workerQueue.slice(0, 5)" :key="first(row.candidateId, row.marketId)" type="button" @click="setActive('polymarket', 'radar')">
                <strong>{{ shortText(first(row.market, row.title, row.question, row.marketId), 66) }}</strong>
                <span>评分 {{ first(row.aiRuleScore, row.score, '--') }} · {{ cleanInlineStatusText(first(row.suggestedShadowTrack, row.executionMode, row.category, 'shadow')) }}</span>
              </button>
              <div v-if="!workerQueue.length" class="rail-empty">暂无 worker 队列。</div>
            </div>
          </article>
          <article class="panel">
            <div class="panel-title split">
              <span>最近 AI 评分</span>
              <small>{{ aiScores.length }} score</small>
            </div>
            <div class="poly-score-stack">
              <div v-for="row in aiScores.slice(0, 4)" :key="first(row.marketId, row.title, row.question)" class="score-line">
                <strong>{{ shortText(marketTitle(row), 64) }}</strong>
                <span>评分 {{ first(row.score, row.aiScore, '--') }} · {{ cleanInlineStatusText(first(row.action, row.recommendation, row.risk, '观察')) }}</span>
              </div>
              <div v-if="!aiScores.length" class="rail-empty">暂无 AI score。</div>
            </div>
          </article>
        </div>

        <div v-else-if="state.polymarketFocus === 'browser'" class="poly-cockpit-grid qd-poly-grid">
          <article class="panel poly-market-console">
            <div class="panel-title split">
              <span>市场浏览 / Gamma 目录</span>
              <small>Gamma API + 历史库 + AI score</small>
            </div>
            <div class="market-browser-grid">
              <button
                v-for="market in polyVisibleMarkets"
                :key="first(market.marketId, market.slug, market.question)"
                type="button"
                class="qd-market-card"
                :class="marketRiskTone(market)"
              >
                <div class="qd-market-head">
                  <strong>{{ shortText(marketTitle(market), 88) }}</strong>
                  <span :title="marketCategory(market)">{{ marketCategoryLabel(market) }}</span>
                </div>
                <div class="qd-market-metrics">
                  <span><small>市场概率</small><b>{{ pctPoint(marketProbability(market)) }}</b></span>
                  <span><small>AI/规则</small><b>{{ cleanInlineStatusText(first(market.aiScoringMode, market.source, '规则评分')) }}</b></span>
                  <span><small>机会评分</small><b>{{ first(market.aiRuleScore, market.score, market.ruleScore, '--') }}</b></span>
                </div>
                <div class="qd-market-foot">
                  <span>成交 {{ money(first(market.volume24h, market.volume, market.volumeUsd)) }}</span>
                  <span>流动性 {{ money(first(market.liquidity, market.liquidityUsd, market.clobLiquidityUsd)) }}</span>
                  <b :title="first(market.recommendedAction, market.recommendation, 'SHADOW')">
                    {{ shortText(cleanInlineStatusText(first(market.recommendedAction, market.recommendation, 'SHADOW')), 16) }}
                  </b>
                </div>
              </button>
              <div v-if="!polyVisibleMarkets.length" class="rail-empty">暂无市场目录或 radar 证据。</div>
            </div>
          </article>

          <article class="panel poly-side-console">
            <div class="panel-title split">
              <span>AI 结果 / 关联风险</span>
              <small>只读证据，不下注</small>
            </div>
            <div class="poly-score-stack">
              <div v-for="row in aiScores.slice(0, 4)" :key="first(row.marketId, row.title, row.question)" class="score-line">
                <strong>{{ shortText(marketTitle(row), 64) }}</strong>
                <span>评分 {{ first(row.score, row.aiScore, '--') }} · {{ cleanInlineStatusText(first(row.action, row.recommendation, row.risk, '观察')) }}</span>
              </div>
              <div v-if="!aiScores.length" class="rail-empty">暂无 AI score。</div>
            </div>
            <div class="governance-lanes compact-governance">
              <div v-for="row in governanceRows.slice(0, 4)" :key="first(row.governanceId, row.marketId)" class="governance-lane governance-lane-rich compact">
                <div class="lane-copy">
                  <strong>{{ governanceTitle(row) }}</strong>
                  <small>{{ governanceDetail(row) }}</small>
                </div>
                <div class="lane-chipset">
                  <b class="status-chip amber">{{ governanceDecisionLabel(row) }}</b>
                  <span v-for="chip in blockerChips(row, 1)" :key="chip" class="status-chip">{{ chip }}</span>
                </div>
              </div>
              <div v-if="!governanceRows.length" class="rail-empty">暂无自动治理建议。</div>
            </div>
          </article>
        </div>

        <div v-else-if="state.polymarketFocus === 'radar'" class="poly-radar-workbench">
          <article class="panel poly-radar-main">
            <div class="panel-title split">
              <span>机会雷达 / Gamma 扫描</span>
              <small>{{ radarRows.length }} 条</small>
            </div>
            <div class="poly-radar-grid">
              <article v-for="row in radarRows" :key="first(row.marketId, row.slug, row.title)" class="panel dense radar-evidence-card" :class="marketRiskTone(row)">
                <div class="panel-title split">
                  <span>{{ shortText(marketTitle(row), 74) }}</span>
                  <b class="pill">{{ pctPoint(first(row.probability, row.marketProbability)) }}</b>
                </div>
                <p>{{ shortText(cleanInlineStatusText(first(row.reason, row.summary, row.recommendation, row.suggestedShadowTrack, '等待 shadow-only 研究')), 130) }}</p>
                <div class="mini-row">
                  <span>成交 {{ money(first(row.volume24h, row.volume, row.volumeUsd)) }}</span>
                  <span>流动性 {{ money(first(row.liquidity, row.liquidityUsd, row.clobLiquidityUsd)) }}</span>
                  <span>评分 {{ first(row.aiRuleScore, row.score, '--') }}</span>
                </div>
              </article>
              <article v-if="!radarRows.length" class="panel empty">暂无 Gamma radar 快照。</article>
            </div>
          </article>
          <article class="panel poly-side-console">
            <div class="panel-title split">
              <span>Worker / 趋势缓存</span>
              <small>{{ workerQueue.length }} queue</small>
            </div>
            <div class="history-list">
              <button v-for="row in workerQueue" :key="first(row.candidateId, row.marketId)" type="button">
                <strong>{{ shortText(first(row.market, row.title, row.question, row.candidateId), 72) }}</strong>
                <span>{{ cleanInlineStatusText(first(row.cacheState, row.trendState, row.suggestedShadowTrack, 'shadow queue')) }} · score {{ first(row.aiRuleScore, row.score, '--') }}</span>
              </button>
              <div v-if="!workerQueue.length" class="rail-empty">暂无长期 worker 队列。</div>
            </div>
          </article>
        </div>

        <div v-else-if="state.polymarketFocus === 'execution'" class="poly-cockpit-grid qd-poly-grid">
          <article class="panel poly-market-console">
            <div class="panel-title split">
              <span>执行模拟边界</span>
              <small>Gate + dry-run + watcher</small>
            </div>
            <div class="poly-real-inline">
              <div
                v-for="card in polyRealSummaryCards"
                :key="`execution-${card.label}`"
                class="micro-metric poly-real-metric"
                :class="card.tone"
              >
                <span>{{ card.label }}</span>
                <strong>{{ card.value }}</strong>
                <small>{{ card.detail }}</small>
              </div>
            </div>
            <div class="poly-current-real execution-current">
              <div class="panel-title split compact-title">
                <span>真钱当前进行中</span>
                <small>{{ polyCurrentRealRows.length }} 条</small>
              </div>
              <div v-if="polyCurrentRealRows.length" class="history-list poly-real-list">
                <button
                  v-for="row in polyCurrentRealRows"
                  :key="`execution-current-${first(row.runId, row.run_id, row.marketId, row.market_id, row.question)}`"
                  type="button"
                >
                  <strong>{{ first(row.question, row.market, row.title, row.marketId, row.market_id) }}</strong>
                  <span>{{ cleanInlineStatusText(first(row.positionState, row.position_state, row.status, row.state, row.decision, 'open')) }} · {{ first(row.side, row.outcome, row.direction, '--') }} · {{ money(first(row.stakeUSDC, row.stake_usdc, row.stake, row.amount, row.size, '--')) }}</span>
                </button>
              </div>
              <p v-else class="summary-line">{{ polyRealEvidenceNote }}</p>
            </div>
            <div class="canary-contract-grid">
              <div v-for="row in canaryRows" :key="first(row.canaryContractId, row.marketId)" class="canary-card">
                <div>
                  <strong>{{ shortText(first(row.question, row.market, row.title, row.marketId, row.canaryContractId), 76) }}</strong>
                  <span>{{ humanEvidenceLabel(first(row.canaryState, row.decision, '模拟')) }}</span>
                </div>
                <b>{{ money(first(row.canaryStakeUSDC, row.stake)) }}</b>
                <p>{{ blockerChips(row, 4).join(' / ') || shortText(first(row.exitRule, '钱包锁定，等待模拟后验。'), 120) }}</p>
              </div>
              <div v-if="!canaryRows.length" class="rail-empty">暂无小额哨兵契约；真实钱包仍保持锁定。</div>
            </div>
          </article>
          <article class="panel poly-side-console">
            <div class="panel-title split">
              <span>真钱边界</span>
              <b class="pill red">已锁定</b>
            </div>
            <p>真实钱包 executor 仍未启用。这里只验证准入、单笔金额、止盈止损、最大日亏、撤单/退出和 ledger 审计契约。</p>
            <div class="governance-lanes compact-governance">
              <div v-for="row in governanceRows.slice(0, 4)" :key="first(row.governanceId, row.marketId)" class="governance-lane governance-lane-rich wallet-boundary-row">
                <div class="lane-copy">
                  <strong>{{ governanceTitle(row) }}</strong>
                  <small>{{ governanceDetail(row) }}</small>
                </div>
                <div class="lane-chipset">
                  <b class="status-chip red">{{ governanceDecisionLabel(row) }}</b>
                  <span v-for="chip in blockerChips(row, 2)" :key="chip" class="status-chip">{{ chip }}</span>
                </div>
              </div>
            </div>
          </article>

          <DataTable
            class="poly-real-trade-ledger"
            title="逐笔真钱交易表"
            dense
            :rows="polyRealTradeRows"
            :columns="[
              { label: '开仓时间', value: polyTradeTime, width: '136px' },
              { label: '平仓时间', value: polyTradeClosedTime, width: '136px' },
              { label: '市场 / 问题', value: (r) => first(r.question, r.market, r.title, r.market_id, r.marketId), max: 180 },
              { label: '方向', value: polyTradeSide, width: '76px', badge: true },
              { label: '结果', value: (r) => first(r.outcome, r.asset, '--'), width: '112px' },
              { label: '状态', value: polyTradeStatus, width: '118px', badge: true, max: 32 },
              { label: '入场', value: (r) => first(r.entry_price, r.entryPrice, r.price), width: '76px', class: 'col-number' },
              { label: '出场', value: (r) => first(r.exit_price, r.exitPrice, r.closePrice), width: '76px', class: 'col-number' },
              { label: '金额', value: (r) => money(polyTradeStake(r)), width: '88px', class: 'col-number' },
              {
                label: '盈亏',
                value: (r) => money(polyTradePnl(r)),
                tone: (r) => pnlTone(polyTradePnl(r)),
                width: '88px',
                class: 'col-pnl'
              },
              { label: '退出/订单', value: (r) => cleanInlineStatusText(first(r.exit_reason, r.exitReason, r.order_id, r.orderId, r.tx_hash, r.txHash, r.notes, '--')), width: '180px', max: 110 }
            ]"
            empty="暂无逐笔真钱交易。D:\polymarket 当前没有可读 copybot.db / trades.csv；导入脚本已就绪，恢复数据源后会自动显示。"
          />
        </div>

        <div v-else class="poly-ledger-workbench">
          <div class="panel evidence-console">
            <div class="panel-title split">
              <span>统一搜索综合证据卡</span>
              <small>{{ searchGroups.length }} 条</small>
            </div>
            <div class="route-tabs compact evidence-mode-tabs">
              <button
                v-for="mode in ['综合证据', 'Radar', '历史分析', 'AI Score']"
                :key="mode"
                type="button"
                :class="{ selected: polyEvidenceMode === mode }"
                @click="polyEvidenceMode = mode"
              >
                {{ mode }}
              </button>
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
        </div>
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
                <td><span class="pill" :title="first(task.state, task.status, task.resultState, '--')">{{ compactStatusLabel(first(task.state, task.status, task.resultState, '--')) }}</span></td>
                <td>{{ compactMetricScore(task.score, task.grade, task.profitFactor) }}</td>
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
            <p>{{ shortText(compactStatusLabel(first(card.payload?.decision, card.payload?.status, card.payload?.mode, '等待证据')), 140) }}</p>
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
            { label: '状态', value: (r) => compactStatusLabel(r.state), width: '110px', badge: true },
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
              { label: '状态', value: (r) => compactStatusLabel(first(r.State, r.status, r.Decision)), width: '110px', badge: true }
            ]"
            empty="暂无 Regime 评估切片。"
          />
        </div>

        <div class="card-grid">
          <DataTable
            title="MT5 交易审计"
            :rows="tradingAuditRows"
            :columns="[
              { label: '时间', value: auditTime, width: '142px' },
              { label: '记录', value: auditRecordId, width: '108px' },
              { label: '范围', value: auditScope, width: '118px', class: 'col-strong' },
              { label: '动作', value: auditActionText, width: '104px', badge: true },
              { label: '方向', value: auditDirectionText, width: '92px', badge: true },
              { label: '路线', value: auditRouteText, width: '118px' },
              { label: '决策', value: auditDecisionText, width: '104px', badge: true },
              { label: '主要原因', value: (r) => auditReasonText(r), max: 132 }
            ]"
            empty="暂无 MT5 审计记录。"
          />
          <DataTable
            title="Manual Alpha Ledger"
            :rows="manualAlphaRows"
            :columns="[
              { label: '时间', value: (r) => first(r.Time, r.time, r.OpenTime, r.CloseTime), width: '180px' },
              { label: '品种', value: (r) => first(r.Symbol, r.symbol), width: '100px' },
              { label: '方向', value: (r) => compactStatusLabel(first(r.Direction, r.direction, r.Type)), width: '90px', badge: true },
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
                  <td>{{ humanEvidenceLabel(first(market.category, '--')) }}</td>
                  <td>{{ pct(first(market.probability, market.bestProbability)) }}</td>
                  <td>{{ money(first(market.volume, market.volumeUsd)) }}</td>
                  <td>{{ cleanInlineStatusText(first(market.risk, market.riskLevel, market.status, '--')) }}</td>
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
              :title="`${item.title} · ${item.sub}`"
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
              :title="`${item.title} · ${item.sub}`"
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
