<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';
import {
  Activity,
  BarChart3,
  Bot,
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

const workspaces = [
  { id: 'home', label: '入口', sub: '双工作台', icon: Gauge },
  { id: 'mt5', label: 'MT5', sub: '策略与实盘', icon: LineChart },
  { id: 'polymarket', label: 'Polymarket', sub: '研究与治理', icon: Network },
  { id: 'paramlab', label: '参数实验', sub: '回测队列', icon: ClipboardList },
  { id: 'charts', label: '趋势图表', sub: '可视化迁移', icon: TrendingUp },
  { id: 'reports', label: '证据报表', sub: '审计总览', icon: BarChart3 }
];

const state = reactive({
  active: 'home',
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
}

function setActive(id) {
  state.active = normalizeWorkspace(id);
  const nextHash = state.active === 'home' ? '' : `#${state.active}`;
  if (window.location.hash !== nextHash) {
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}${nextHash}`);
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

const mt5Routes = computed(() => {
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
    if (activeRoute.value === '全部') return true;
    return routeName(row).includes(activeRoute.value);
  }).slice(0, 10);
});

const paramTasks = computed(() => {
  const status = mt5.value.paramStatus || {};
  const results = mt5.value.paramResults || {};
  return [
    ...arrayFrom(status, ['tasks', 'queue', 'candidates', 'batch']),
    ...arrayFrom(results, ['results', 'scoredResults'])
  ].slice(0, 12);
});

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
      foot: `雷达 ${radarRows.value.length} / AI ${aiScores.value.length} / Canary ${canaryRows.value.length}`
    }
  ];
});

const reportCards = computed(() => [
  { name: 'ParamLab', payload: mt5.value.paramStatus, count: paramTasks.value.length },
  { name: '回测结果', payload: mt5.value.backtest, count: arrayFrom(mt5.value.backtest, ['results', 'summaries']).length },
  { name: 'Run Recovery', payload: mt5.value.runRecovery, count: arrayFrom(mt5.value.runRecovery, ['runs', 'recoveryRows']).length },
  { name: 'Polymarket History', payload: poly.value.history, count: first(poly.value.history?.summary?.totalRows, poly.value.history?.rows?.length, '--') },
  { name: 'AI Score', payload: poly.value.aiScore, count: aiScores.value.length },
  { name: 'Canary Contract', payload: poly.value.canary, count: canaryRows.value.length }
]);

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

      <nav>
        <button
          v-for="item in workspaces"
          :key="item.id"
          class="nav-item"
          :class="{ active: state.active === item.id }"
          type="button"
          @click="setActive(item.id)"
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
        <small>默认只读 / dry-run / canary locked</small>
      </div>
    </aside>

    <main class="workspace">
      <header class="topbar">
        <div>
          <p class="eyebrow">Vue Workbench</p>
          <h1>{{ workspaces.find((item) => item.id === state.active)?.label }}</h1>
        </div>
        <div class="top-actions">
          <label class="search-box">
            <Search :size="16" />
            <input v-model="state.query" type="search" placeholder="搜索 Polymarket 证据" @keyup.enter="refresh" />
          </label>
          <button class="ghost-button" type="button" @click="refresh">
            <RefreshCw :size="16" :class="{ spin: state.loading }" />
            刷新
          </button>
        </div>
      </header>

      <section v-if="state.error" class="notice danger">{{ state.error }}</section>

      <section v-if="state.active === 'home'" class="stack">
        <div class="section-grid">
          <article class="hero-panel compact-hero">
            <p class="eyebrow">系统入口</p>
            <h2>MT5 与 Polymarket 分开管理，同一证据层复盘</h2>
            <p>
              Vue 现在是默认入口，但旧页不会马上冻结。先把监盘、ParamLab、趋势图和 Polymarket 细节补到不输旧页，再进入真正只读归档。
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

      <section v-if="state.active === 'mt5'" class="stack">
        <div class="toolbar">
          <div>
            <p class="eyebrow">MT5 Workbench</p>
            <h2>策略与实盘证据</h2>
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

        <div class="metric-grid four">
          <div class="metric"><span>账号</span><strong>{{ first(mt5Account.login, mt5Account.account, '--') }}</strong><small>{{ first(mt5Account.server, 'server --') }}</small></div>
          <div class="metric"><span>净值</span><strong>{{ money(first(mt5Account.equity, mt5.latest?.equity)) }}</strong><small>余额 {{ money(mt5Account.balance) }}</small></div>
          <div class="metric"><span>持仓</span><strong>{{ mt5Positions.length }}</strong><small>单仓和 0.01 约束由 EA 控制</small></div>
          <div class="metric"><span>状态</span><strong>{{ first(mt5.snapshot?.status, mt5.snapshot?.ok ? '已连接' : '未连接') }}</strong><small>只读桥 / dashboard snapshot</small></div>
        </div>

        <div class="card-grid">
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

      <section v-if="state.active === 'polymarket'" class="stack">
        <div class="toolbar">
          <div>
            <p class="eyebrow">Polymarket Workbench</p>
            <h2>机会雷达、历史库、AI 评分与 canary 治理</h2>
          </div>
          <div class="status-chip locked">
            <WalletCards :size="16" />
            钱包写操作默认关闭
          </div>
        </div>

        <div class="section-grid">
          <article class="panel">
            <div class="panel-title"><Target :size="18" />单市场分析入口</div>
            <p class="muted">输入 URL、标题或 marketId，只生成本地研究请求和历史证据，不下注。</p>
            <div class="inline-form">
              <input v-model="state.marketInput" type="text" placeholder="Polymarket URL / 标题 / marketId" @keyup.enter="submitSingleMarket" />
              <button type="button" @click="submitSingleMarket">生成请求</button>
            </div>
            <small>{{ state.requestStatus }}</small>
          </article>

          <article class="panel">
            <div class="panel-title"><Activity :size="18" />治理摘要</div>
            <div class="metric-grid">
              <div class="metric"><span>AI 评分</span><strong>{{ aiScores.length }}</strong><small>history-aware</small></div>
              <div class="metric"><span>Canary</span><strong>{{ canaryRows.length }}</strong><small>contract only</small></div>
              <div class="metric"><span>跨市场</span><strong>{{ crossRows.length }}</strong><small>风险联动</small></div>
              <div class="metric"><span>队列</span><strong>{{ workerQueue.length }}</strong><small>shadow only</small></div>
            </div>
          </article>
        </div>

        <div class="card-grid">
          <article v-for="row in radarRows" :key="first(row.marketId, row.slug, row.title)" class="panel dense">
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

        <div class="panel">
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

      <section v-if="state.active === 'paramlab'" class="stack">
        <div class="toolbar">
          <div>
            <p class="eyebrow">ParamLab</p>
            <h2>参数候选、回测队列与恢复状态</h2>
          </div>
          <div class="status-chip">tester-only / guarded</div>
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
              <tr v-for="task in paramTasks" :key="first(task.candidateId, task.taskId, task.versionId)">
                <td>{{ shortText(first(task.candidateId, task.versionId, task.name), 42) }}</td>
                <td>{{ first(task.route, task.strategy, task.symbol, '--') }}</td>
                <td><span class="pill">{{ first(task.state, task.status, task.resultState, '--') }}</span></td>
                <td>{{ first(task.score, task.grade, task.profitFactor, '--') }}</td>
                <td>{{ shortText(first(task.reportPath, task.report, task.configPath), 64) }}</td>
              </tr>
              <tr v-if="!paramTasks.length"><td colspan="5">暂无 ParamLab 队列或结果。</td></tr>
            </tbody>
          </table>
        </div>

        <ParamLabDeepPanels :mt5="mt5" :tasks="paramTasks" />
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
            <small>generatedAt: {{ first(card.payload?.generatedAt, '--') }}</small>
          </article>
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
      </section>
    </main>
  </div>
</template>
