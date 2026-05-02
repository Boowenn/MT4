<template>
  <section class="phase2-workspace">
    <header class="phase2-hero">
      <div>
        <p>PHASE 2 / API + PUSH NOTIFY</p>
        <h2>统一 API、Telegram 通知与 CI 集成</h2>
      </div>
      <a-tag color="blue">read-only / push-only</a-tag>
    </header>

    <nav class="phase2-nav" aria-label="Phase 2 groups">
      <a-button
        v-for="item in groups"
        :key="item.key"
        :type="selectedKeys[0] === item.key ? 'primary' : 'default'"
        @click="selectedKeys = [item.key]"
      >
        {{ item.label }}
      </a-button>
    </nav>

    <div class="phase2-grid">
      <a-card :title="activeGroup.label" :bordered="false" class="phase2-card phase2-data-card">
        <template #extra>
          <a-space class="phase2-actions">
            <a-button size="small" @click="loadActive" :loading="loading">刷新</a-button>
            <a-tag v-if="lastLoaded">{{ lastLoaded }}</a-tag>
          </a-space>
        </template>

        <label class="phase2-field">
          <span>Endpoint</span>
          <a-select
            v-model:value="activeEndpoint"
            :options="endpointOptions"
            class="phase2-select"
          />
        </label>

        <a-alert
          v-if="error"
          type="error"
          show-icon
          :message="error"
          class="phase2-alert"
        />

        <div v-if="rows.length" class="phase2-record-list">
          <article v-for="row in rows.slice(0, 12)" :key="row._phase2RowId" class="phase2-record">
            <div v-for="column in columns.slice(0, 8)" :key="column.key" class="phase2-kv">
              <span>{{ column.title }}</span>
              <strong>{{ formatCell(row[column.dataIndex]) }}</strong>
            </div>
          </article>
        </div>
        <a-alert
          v-else
          type="info"
          show-icon
          message="暂无数据"
          description="对应的运行时 JSON/CSV 还没有生成，或文件为空。"
        />
      </a-card>

      <aside class="phase2-side">
        <a-card title="统一 API 状态" :bordered="false" class="phase2-card">
          <dl class="phase2-summary">
            <div><dt>Endpoint</dt><dd>{{ summary.endpoint }}</dd></div>
            <div><dt>文件</dt><dd>{{ summary.fileName }}</dd></div>
            <div><dt>更新时间</dt><dd>{{ summary.mtimeIso }}</dd></div>
            <div><dt>返回行数</dt><dd>{{ summary.returnedRows }}</dd></div>
          </dl>
          <a-alert
            class="phase2-alert"
            type="info"
            show-icon
            message="只读数据面"
            description="Phase 2 API 只读读取 runtime 文件；通知端点只推送消息，不接受 Telegram 命令，也不触发交易。"
          />
        </a-card>

        <a-card title="Telegram 通知" :bordered="false" class="phase2-card">
          <div class="phase2-notify">
            <a-button @click="loadNotify" :loading="notifyLoading">读取配置</a-button>
            <a-alert
              v-if="notifyConfig"
              :type="notifyConfig.telegramConfigured ? 'success' : 'warning'"
              show-icon
              :message="notifyConfig.telegramConfigured ? 'Telegram 已配置' : 'Telegram Token / Chat ID 未配置'"
            />
            <a-input v-model:value="testMessage" placeholder="测试消息" />
            <div class="phase2-button-row">
              <a-button type="primary" @click="sendTest(false)" :loading="notifyLoading">发送测试</a-button>
              <a-button @click="sendTest(true)" :loading="notifyLoading">Dry-run</a-button>
            </div>
            <div class="phase2-notify-list">
              <article v-for="row in notifyRows.slice(0, 6)" :key="row.key" class="phase2-notify-item">
                <strong>{{ row.eventType || 'EVENT' }}</strong>
                <small>{{ row.timestamp || '--' }}</small>
                <span>{{ row.sent ? 'sent' : row.error || 'pending' }}</span>
              </article>
              <p v-if="!notifyRows.length" class="phase2-empty">暂无通知历史。</p>
            </div>
          </div>
        </a-card>
      </aside>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import {
  PHASE2_ENDPOINTS,
  apiGet,
  endpointSummary,
  extractRows,
  loadNotifyConfig,
  loadNotifyHistory,
  sendNotifyTest,
  tableColumns,
} from '../../services/phase2Api';

const groups = [
  { key: 'governance', label: 'Governance', endpoints: PHASE2_ENDPOINTS.governance },
  { key: 'paramlab', label: 'ParamLab', endpoints: PHASE2_ENDPOINTS.paramlab },
  { key: 'trades', label: '交易历史', endpoints: PHASE2_ENDPOINTS.trades },
  { key: 'research', label: '研究统计', endpoints: PHASE2_ENDPOINTS.research },
  { key: 'shadow', label: 'Shadow / Candidate', endpoints: PHASE2_ENDPOINTS.shadow },
  { key: 'dashboard', label: 'Dashboard 状态', endpoints: PHASE2_ENDPOINTS.dashboard },
];

const selectedKeys = ref(['governance']);
const activeEndpoint = ref(PHASE2_ENDPOINTS.governance[0][0]);
const loading = ref(false);
const error = ref('');
const payload = ref(null);
const lastLoaded = ref('');
const notifyLoading = ref(false);
const notifyConfig = ref(null);
const notifyHistory = ref(null);
const testMessage = ref('QuantGod Phase 2 Telegram test');

const activeGroup = computed(() => groups.find((item) => item.key === selectedKeys.value[0]) || groups[0]);
const endpointOptions = computed(() => activeGroup.value.endpoints.map(([value, label]) => ({ value, label })));
const rows = computed(() => extractRows(payload.value).map((row, index) => ({ _phase2RowId: `${index}`, ...row })));
const columns = computed(() => tableColumns(rows.value));
const summary = computed(() => endpointSummary(payload.value || {}));
const notifyRows = computed(() => (notifyHistory.value?.items || []).map((row, index) => ({ key: `${index}`, ...row })).reverse());

watch(selectedKeys, () => {
  activeEndpoint.value = activeGroup.value.endpoints[0]?.[0] || '';
  loadActive();
});

watch(activeEndpoint, () => loadActive());

async function loadActive() {
  if (!activeEndpoint.value) return;
  loading.value = true;
  error.value = '';
  const next = await apiGet(activeEndpoint.value);
  payload.value = next;
  if (next?.ok === false) {
    error.value = next.error || 'API 请求失败';
  }
  lastLoaded.value = new Date().toLocaleTimeString();
  loading.value = false;
}

async function loadNotify() {
  notifyLoading.value = true;
  notifyConfig.value = await loadNotifyConfig();
  notifyHistory.value = await loadNotifyHistory(50);
  notifyLoading.value = false;
}

async function sendTest(dryRun) {
  notifyLoading.value = true;
  await sendNotifyTest(testMessage.value, dryRun);
  notifyHistory.value = await loadNotifyHistory(50);
  notifyLoading.value = false;
}

function formatCell(value) {
  if (value === null || value === undefined || value === '') return '--';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

onMounted(() => {
  loadActive();
  loadNotify();
});
</script>

<style scoped>
.phase2-workspace {
  box-sizing: border-box;
  display: grid;
  gap: 16px;
  width: 100%;
  min-width: 0;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 18px;
  padding: 18px;
  background: linear-gradient(135deg, rgba(11, 22, 40, 0.86), rgba(15, 23, 42, 0.96));
}
.phase2-hero,
.phase2-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 0.48fr);
  gap: 16px;
  align-items: start;
  min-width: 0;
}
.phase2-hero {
  align-items: end;
}
.phase2-hero p,
.phase2-hero h2 {
  margin: 0;
}
.phase2-hero p {
  color: #38bdf8;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.08em;
}
.phase2-hero h2 {
  margin-top: 6px;
  color: #f8fafc;
  font-size: 28px;
  line-height: 1.15;
}
.phase2-nav,
.phase2-button-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
}
.phase2-card {
  min-width: 0;
  margin-bottom: 16px;
}
.phase2-side,
.phase2-data-card {
  min-width: 0;
}
.phase2-field,
.phase2-notify {
  display: grid;
  gap: 10px;
  min-width: 0;
}
.phase2-field span {
  color: #94a3b8;
  font-size: 12px;
  font-weight: 700;
}
.phase2-select {
  width: 100%;
  min-width: 0;
}
.phase2-alert {
  margin: 12px 0;
}
.phase2-record-list,
.phase2-notify-list {
  display: grid;
  gap: 10px;
  min-width: 0;
}
.phase2-record {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(160px, 100%), 1fr));
  gap: 8px;
  min-width: 0;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 12px;
  padding: 10px;
  background: rgba(15, 23, 42, 0.56);
}
.phase2-kv,
.phase2-summary div,
.phase2-notify-item {
  min-width: 0;
  overflow-wrap: anywhere;
}
.phase2-kv span,
.phase2-summary dt,
.phase2-notify-item small,
.phase2-notify-item span,
.phase2-empty {
  color: #94a3b8;
}
.phase2-kv strong,
.phase2-summary dd {
  display: block;
  margin: 4px 0 0;
  color: #e5eefc;
}
.phase2-summary {
  display: grid;
  gap: 10px;
  margin: 0;
}
.phase2-summary dd {
  margin-left: 0;
}
.phase2-notify-item {
  display: grid;
  gap: 2px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 10px;
  padding: 9px;
  background: rgba(15, 23, 42, 0.5);
}
.phase2-empty {
  margin: 0;
}

@media (max-width: 1100px) {
  .phase2-hero,
  .phase2-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 640px) {
  .phase2-workspace {
    padding: 12px;
    border-radius: 14px;
  }

  .phase2-hero h2 {
    font-size: 22px;
  }

  .phase2-nav .ant-btn,
  .phase2-button-row .ant-btn {
    flex: 1 1 120px;
  }
}
</style>
