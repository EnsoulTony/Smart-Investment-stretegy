<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { formatHealthStatus } from "./lib/health";

// 以靜態列表描述目前的服務骨架，後續可改為即時輪詢。
const services = [
  "api-gateway",
  "portfolio-service",
  "radar-service",
  "news-service",
  "research-service",
];

const healthMessages = computed(() =>
  services.map((name) => ({
    name,
    message: formatHealthStatus(name),
  })),
);

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  `${window.location.protocol}//${window.location.hostname}:8000`;
const USER_ID = "tony";
const asOf = ref(new Date().toISOString().slice(0, 10));
const newsItems = ref([]);
const newsError = ref("");
const newsLoading = ref(false);
const decisionPackage = ref(null);
const decisionError = ref("");
const decisionLoading = ref(false);
const decisionHistory = ref([]);
const decisionHistoryError = ref("");
const decisionHistoryLoading = ref(false);
const outcomeMap = ref(new Map());
const outcomeEditing = ref("");
const outcomeDrafts = ref({});
const analyticsTriggers = ref([]);
const analyticsDecisions = ref([]);
const analyticsLoading = ref(false);
const analyticsError = ref("");
const decisionAnalyticsGroup = ref("tier");
const holdings = ref([]);
const positions = ref([]);
const holdingsError = ref("");
const holdingsLoading = ref(false);
const holdingsSaving = ref(false);
const holdingsSyncing = ref(false);
const holdingsRebuilding = ref(false);
const holdingsSavedAt = ref("");
const holdingsHint = ref("");
const lastUpdated = ref("");
const symbolMappings = ref([]);
const mappingsLoading = ref(false);
const mappingsError = ref("");
const mappingSymbol = ref("");
const mappingMarket = ref("US");
const mappingNameZh = ref("");
const mappingSource = ref("manual");
const mappingResolving = ref(false);
const mappingSaving = ref(false);
const mappingsUpdatedAt = ref("");
const triggerItems = ref([]);
const triggerLoading = ref(false);
const triggerError = ref("");
const triggerExpanded = ref(new Set());
const triggerDrilldown = ref(new Set());
const triggerFilters = ref({
  from: "",
  to: "",
  plugin: "v1.4",
  is_triggered: "all",
  trigger_type: "all",
  limit: 200,
  offset: 0,
});
const panels = ref({
  news: false,
  coreHoldings: true,
  positions: true,
  mappings: true,
  decision: true,
  decisionHistory: false,
  analytics: false,
  triggers: false,
  health: true,
});

const togglePanel = (key) => {
  panels.value[key] = !panels.value[key];
};

const n1Items = computed(() => newsItems.value.filter((item) => item.tier === "N1"));
const n3Items = computed(() => newsItems.value.filter((item) => item.tier === "N3"));
const decisionSummary = computed(() => {
  if (!decisionPackage.value) {
    return "尚未產生融合決策說明";
  }
  const n1 = decisionPackage.value.evidence?.news_context?.tiers_count?.N1 ?? 0;
  const n3 = decisionPackage.value.evidence?.news_context?.tiers_count?.N3 ?? 0;
  const score = decisionPackage.value.evidence?.news_context?.score_impact?.risk_off_score_added ?? 0;
  return `N1=${n1}、N3=${n3}，新聞風險分數影響 ${score}，融合後模式為 ${decisionPackage.value.mode}，決策為 ${decisionPackage.value.decision}。`;
});

const formatNotePreview = (text) => {
  if (!text) {
    return "-";
  }
  return text.length > 60 ? `${text.slice(0, 60)}...` : text;
};

const formatRate = (value) => {
  if (value === null || value === undefined) {
    return "-";
  }
  const rate = Number(value);
  if (Number.isNaN(rate)) {
    return "-";
  }
  return `${(rate * 100).toFixed(1)}%`;
};

const getOutcome = (hash) => outcomeMap.value.get(hash) || { outcome_label: "unknown", outcome_note: "" };

const startOutcomeEdit = (row) => {
  const hash = row.inputs_hash || "";
  outcomeEditing.value = hash;
  const current = getOutcome(hash);
  outcomeDrafts.value[hash] = {
    label: current.outcome_label || "unknown",
    note: current.outcome_note || "",
  };
};

const cancelOutcomeEdit = () => {
  outcomeEditing.value = "";
};

const saveOutcome = async (row) => {
  const hash = row.inputs_hash || "";
  const draft = outcomeDrafts.value[hash];
  if (!draft) {
    return;
  }
  try {
    const response = await fetch(`${API_BASE_URL}/portfolio/outcomes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: USER_ID,
        as_of: row.as_of,
        plugin: "v1.4",
        decision_inputs_hash: hash,
        outcome_label: draft.label,
        outcome_note: draft.note,
      }),
    });
    if (!response.ok) {
      throw new Error(`portfolio-service ${response.status}`);
    }
    const payload = await response.json();
    const next = new Map(outcomeMap.value);
    next.set(hash, payload);
    outcomeMap.value = next;
    outcomeEditing.value = "";
  } catch (err) {
    decisionHistoryError.value = err?.message || "api-gateway 連線失敗";
  }
};

const fetchDecisionHistory = async () => {
  decisionHistoryLoading.value = true;
  decisionHistoryError.value = "";
  try {
    const url = `${API_BASE_URL}/radar/decisions/history?user_id=${USER_ID}&limit=20`;
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`radar-service ${response.status}`);
    }
    decisionHistory.value = await response.json();
  } catch (err) {
    decisionHistoryError.value = err?.message || "api-gateway 連線失敗";
  } finally {
    decisionHistoryLoading.value = false;
  }
};

const fetchOutcomes = async () => {
  const to = asOf.value;
  const fromDate = new Date(to);
  fromDate.setDate(fromDate.getDate() - 30);
  const from = fromDate.toISOString().slice(0, 10);
  try {
    const url = `${API_BASE_URL}/portfolio/outcomes?user_id=${USER_ID}&plugin=v1.4&from=${from}&to=${to}&limit=200&offset=0`;
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`portfolio-service ${response.status}`);
    }
    const payload = await response.json();
    const next = new Map();
    (payload.items || []).forEach((item) => {
      next.set(item.decision_inputs_hash, item);
    });
    outcomeMap.value = next;
  } catch (err) {
    decisionHistoryError.value = err?.message || "api-gateway 連線失敗";
  }
};

const sortedTriggerAnalytics = computed(() => {
  return [...analyticsTriggers.value].sort((a, b) => {
    const rateDiff = (Number(b.win_rate) || 0) - (Number(a.win_rate) || 0);
    if (rateDiff !== 0) {
      return rateDiff;
    }
    return (Number(b.total) || 0) - (Number(a.total) || 0);
  });
});

const sortedDecisionAnalytics = computed(() => {
  return [...analyticsDecisions.value].sort((a, b) => {
    const rateDiff = (Number(b.win_rate) || 0) - (Number(a.win_rate) || 0);
    if (rateDiff !== 0) {
      return rateDiff;
    }
    return (Number(b.total) || 0) - (Number(a.total) || 0);
  });
});

const suspiciousTriggers = computed(() => {
  const scored = analyticsTriggers.value
    .map((row) => {
      const total = Number(row.total) || 0;
      const losses = Number(row.losses) || 0;
      const lossRate = total ? losses / total : 0;
      return { ...row, loss_rate: lossRate };
    })
    .filter((row) => (Number(row.total) || 0) >= 2)
    .sort((a, b) => {
      const rateDiff = (b.loss_rate || 0) - (a.loss_rate || 0);
      if (rateDiff !== 0) {
        return rateDiff;
      }
      return (Number(b.total) || 0) - (Number(a.total) || 0);
    });
  return scored.slice(0, 3);
});

const fetchOutcomeAnalytics = async () => {
  analyticsLoading.value = true;
  analyticsError.value = "";
  try {
    const to = asOf.value;
    const fromDate = new Date(to);
    fromDate.setDate(fromDate.getDate() - 30);
    const from = fromDate.toISOString().slice(0, 10);
    const triggerParams = new URLSearchParams({
      user_id: USER_ID,
      plugin: "v1.4",
      from,
      to,
      only_triggered: "true",
    });
    const decisionParams = new URLSearchParams({
      user_id: USER_ID,
      plugin: "v1.4",
      from,
      to,
      group_by: decisionAnalyticsGroup.value,
    });
    const [triggerResponse, decisionResponse] = await Promise.all([
      fetch(`${API_BASE_URL}/radar/analytics/triggers?${triggerParams.toString()}`),
      fetch(`${API_BASE_URL}/radar/analytics/decisions?${decisionParams.toString()}`),
    ]);
    if (!triggerResponse.ok) {
      throw new Error(`radar-service analytics ${triggerResponse.status}`);
    }
    if (!decisionResponse.ok) {
      throw new Error(`radar-service analytics ${decisionResponse.status}`);
    }
    const triggerPayload = await triggerResponse.json();
    const decisionPayload = await decisionResponse.json();
    analyticsTriggers.value = triggerPayload.items || [];
    analyticsDecisions.value = decisionPayload.items || [];
  } catch (err) {
    analyticsError.value = err?.message || "api-gateway 連線失敗";
  } finally {
    analyticsLoading.value = false;
  }
};

watch(decisionAnalyticsGroup, () => {
  fetchOutcomeAnalytics();
});

const selectedCoreItems = computed(() =>
  holdings.value
    .filter((item) => item.selected)
    .map((item) => ({
      symbol: item.symbol,
      name_zh: item.name_zh || "",
    })),
);
const holdingsEmpty = computed(() => holdings.value.length === 0);
const triggerTypeOptions = ["all", "news", "indicator", "price", "time", "core", "unknown"];

const triggerRowKey = (row, idx) =>
  `${row.trigger_key || "trigger"}-${row.evaluated_at || "time"}-${idx}`;

const toggleTriggerDetails = (rowKey) => {
  const next = new Set(triggerExpanded.value);
  if (next.has(rowKey)) {
    next.delete(rowKey);
  } else {
    next.add(rowKey);
  }
  triggerExpanded.value = next;
};

const toggleTriggerDrilldown = (rowKey) => {
  const next = new Set(triggerDrilldown.value);
  if (next.has(rowKey)) {
    next.delete(rowKey);
  } else {
    next.add(rowKey);
  }
  triggerDrilldown.value = next;
};

const formatObservedPreview = (value) => {
  if (!value) {
    return "-";
  }
  const text = JSON.stringify(value);
  return text.length > 140 ? `${text.slice(0, 140)}...` : text;
};

const groupedByInputsHash = computed(() => {
  const groups = new Map();
  triggerItems.value.forEach((row) => {
    const key = row.decision_inputs_hash || "unknown";
    if (!groups.has(key)) {
      groups.set(key, []);
    }
    groups.get(key).push(row);
  });
  return groups;
});

const copyHash = async (value) => {
  if (!value) {
    return;
  }
  try {
    await navigator.clipboard.writeText(value);
  } catch (err) {
    console.warn("copy failed", err);
  }
};

const initTriggerDates = () => {
  const today = new Date();
  const to = today.toISOString().slice(0, 10);
  const fromDate = new Date(today);
  fromDate.setDate(fromDate.getDate() - 30);
  const from = fromDate.toISOString().slice(0, 10);
  triggerFilters.value.from = from;
  triggerFilters.value.to = to;
};

const fetchTriggerHistory = async () => {
  triggerLoading.value = true;
  triggerError.value = "";
  try {
    const params = new URLSearchParams({
      user_id: USER_ID,
      plugin: triggerFilters.value.plugin,
      from: triggerFilters.value.from,
      to: triggerFilters.value.to,
      limit: String(triggerFilters.value.limit || 200),
      offset: String(triggerFilters.value.offset || 0),
    });
    if (triggerFilters.value.is_triggered !== "all") {
      params.set("is_triggered", triggerFilters.value.is_triggered);
    }
    if (triggerFilters.value.trigger_type !== "all") {
      params.set("trigger_type", triggerFilters.value.trigger_type);
    }
    const url = `${API_BASE_URL}/radar/triggers/history?${params.toString()}`;
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`radar-service ${response.status}`);
    }
    const payload = await response.json();
    triggerItems.value = payload.items || [];
  } catch (err) {
    triggerError.value = err?.message || "api-gateway 連線失敗";
  } finally {
    triggerLoading.value = false;
  }
};

const fetchNewsSignals = async () => {
  newsLoading.value = true;
  newsError.value = "";
  try {
    const url = `${API_BASE_URL}/news/signals?user_id=${USER_ID}&as_of=${asOf.value}`;
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`news-service ${response.status}`);
    }
    const payload = await response.json();
    newsItems.value = payload.items || [];
    lastUpdated.value = new Date().toLocaleString("zh-TW");
  } catch (err) {
    newsError.value = err?.message || "api-gateway 連線失敗";
  } finally {
    newsLoading.value = false;
  }
};

const fetchDecisionPackage = async () => {
  decisionLoading.value = true;
  decisionError.value = "";
  try {
    const url = `${API_BASE_URL}/radar/decision?user_id=${USER_ID}&as_of=${asOf.value}&base_ccy=TWD&plugin=v1.4`;
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`radar-service ${response.status}`);
    }
    decisionPackage.value = await response.json();
  } catch (err) {
    decisionError.value = err?.message || "api-gateway 連線失敗";
  } finally {
    decisionLoading.value = false;
  }
};

const fetchHoldings = async () => {
  holdingsLoading.value = true;
  holdingsError.value = "";
  holdingsHint.value = "";
  try {
    const positionsUrl = `${API_BASE_URL}/portfolio/positions?user_id=${USER_ID}`;
    const coreUrl = `${API_BASE_URL}/portfolio/core_holdings?user_id=${USER_ID}`;
    const [positionsResp, coreResp] = await Promise.all([
      fetch(positionsUrl),
      fetch(coreUrl),
    ]);
    if (!positionsResp.ok) {
      throw new Error(`portfolio-service positions ${positionsResp.status}`);
    }
    if (!coreResp.ok) {
      throw new Error(`portfolio-service core_holdings ${coreResp.status}`);
    }
    const positionsData = await positionsResp.json();
    const coreData = await coreResp.json();
    positions.value = positionsData.items || [];
    const positionSymbols = (positionsData.items || []).map((item) => item.symbol);
    const positionNameMap = new Map(
      (positionsData.items || []).map((item) => [item.symbol, item.name_zh]),
    );
    const coreItems = coreData.items || [];
    const coreSymbols = coreItems.map((item) => item.symbol);
    const coreNameMap = new Map(coreItems.map((item) => [item.symbol, item.name_zh]));
    const allSymbols = Array.from(new Set([...positionSymbols, ...coreSymbols])).sort();
    const coreSet = new Set(coreSymbols);
    holdings.value = allSymbols.map((symbol) => ({
      symbol,
      name_zh: positionNameMap.get(symbol) || coreNameMap.get(symbol) || "",
      name:
        positionNameMap.get(symbol) ||
        coreNameMap.get(symbol) ||
        "未提供中文說明",
      selected: coreSet.has(symbol),
    }));
    if (holdings.value.length === 0) {
      holdingsHint.value = "目前尚未同步/重建持股，請先按下「同步」與「重建」取得清單。";
    }
  } catch (err) {
    holdingsError.value = err?.message || "api-gateway 連線失敗";
  } finally {
    holdingsLoading.value = false;
  }
};

const syncPortfolio = async () => {
  holdingsSyncing.value = true;
  holdingsError.value = "";
  holdingsHint.value = "";
  try {
    const url = `${API_BASE_URL}/portfolio/sync`;
    const response = await fetch(url, { method: "POST" });
    if (!response.ok) {
      throw new Error(`portfolio-service sync ${response.status}`);
    }
  } catch (err) {
    holdingsError.value = err?.message || "api-gateway 連線失敗";
  } finally {
    holdingsSyncing.value = false;
  }
};

const rebuildPositions = async () => {
  holdingsRebuilding.value = true;
  holdingsError.value = "";
  holdingsHint.value = "";
  try {
    const url = `${API_BASE_URL}/portfolio/rebuild_positions?user_id=${USER_ID}&require_trades=true`;
    const response = await fetch(url, { method: "POST" });
    if (!response.ok) {
      throw new Error(`portfolio-service rebuild_positions ${response.status}`);
    }
    await fetchHoldings();
  } catch (err) {
    holdingsError.value = err?.message || "api-gateway 連線失敗";
  } finally {
    holdingsRebuilding.value = false;
  }
};

const saveCoreHoldings = async () => {
  holdingsSaving.value = true;
  holdingsError.value = "";
  holdingsHint.value = "";
  try {
    const url = `${API_BASE_URL}/portfolio/core_holdings?user_id=${USER_ID}`;
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: selectedCoreItems.value }),
    });
    if (!response.ok) {
      throw new Error(`portfolio-service core_holdings ${response.status}`);
    }
    holdingsSavedAt.value = new Date().toLocaleString("zh-TW");
  } catch (err) {
    holdingsError.value = err?.message || "api-gateway 連線失敗";
  } finally {
    holdingsSaving.value = false;
  }
};

const fetchSymbolMappings = async () => {
  mappingsLoading.value = true;
  mappingsError.value = "";
  try {
    const url = `${API_BASE_URL}/portfolio/symbol_mappings`;
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`portfolio-service symbol_mappings ${response.status}`);
    }
    const payload = await response.json();
    symbolMappings.value = payload.items || [];
  } catch (err) {
    mappingsError.value = err?.message || "api-gateway 連線失敗";
  } finally {
    mappingsLoading.value = false;
  }
};

const resolveSymbolMapping = async () => {
  if (!mappingSymbol.value.trim()) {
    mappingsError.value = "請先輸入 symbol";
    return;
  }
  mappingResolving.value = true;
  mappingsError.value = "";
  try {
    const url = `${API_BASE_URL}/portfolio/symbol_mappings/resolve`;
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol: mappingSymbol.value.trim().toUpperCase(),
        market: mappingMarket.value,
      }),
    });
    if (!response.ok) {
      throw new Error(`portfolio-service symbol_mappings resolve ${response.status}`);
    }
    const payload = await response.json();
    mappingNameZh.value = payload.name_zh || "";
    mappingSource.value = payload.source || "manual";
    await fetchSymbolMappings();
  } catch (err) {
    mappingsError.value = err?.message || "api-gateway 連線失敗";
  } finally {
    mappingResolving.value = false;
  }
};

const saveSymbolMapping = async () => {
  if (!mappingSymbol.value.trim() || !mappingNameZh.value.trim()) {
    mappingsError.value = "請填入 symbol 與中文名稱";
    return;
  }
  mappingSaving.value = true;
  mappingsError.value = "";
  try {
    const url = `${API_BASE_URL}/portfolio/symbol_mappings`;
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol: mappingSymbol.value.trim().toUpperCase(),
        market: mappingMarket.value,
        name_zh: mappingNameZh.value.trim(),
        source: mappingSource.value || "manual",
      }),
    });
    if (!response.ok) {
      throw new Error(`portfolio-service symbol_mappings ${response.status}`);
    }
    mappingsUpdatedAt.value = new Date().toLocaleString("zh-TW");
    await fetchSymbolMappings();
  } catch (err) {
    mappingsError.value = err?.message || "api-gateway 連線失敗";
  } finally {
    mappingSaving.value = false;
  }
};

const fetchAll = async () => {
  await Promise.all([
    fetchNewsSignals(),
    fetchDecisionPackage(),
    fetchHoldings(),
    fetchSymbolMappings(),
    fetchDecisionHistory(),
    fetchTriggerHistory(),
    fetchOutcomeAnalytics(),
  ]);
  await fetchOutcomes();
};

onMounted(() => {
  initTriggerDates();
  fetchAll();
});
</script>

<template>
  <main class="container">
    <header class="hero">
      <div>
        <p class="eyebrow">Sprint 3 War Room</p>
        <h1>Smart Investment Strategy</h1>
        <p class="subtitle">新聞（N1/N3）→ news_signals → 戰情室呈現</p>
      </div>
      <div class="hero-card">
        <div>
        <p class="label">as_of</p>
        <p class="value">{{ asOf }}</p>
      </div>
        <button class="refresh" type="button" @click="fetchAll" :disabled="newsLoading || decisionLoading">
          {{ newsLoading || decisionLoading ? "讀取中..." : "重新整理" }}
        </button>
        <span class="action-note">重新載入新聞、持股、名稱映射與決策包</span>
        <p class="timestamp" v-if="lastUpdated">更新時間：{{ lastUpdated }}</p>
      </div>
    </header>

    <section class="panel">
      <div class="panel-header">
        <h2>戰情室｜新聞訊號</h2>
        <span class="badge">news-service</span>
        <button class="collapse-btn" type="button" @click="togglePanel('news')">
          {{ panels.news ? "展開" : "收合" }}
        </button>
      </div>

      <div v-show="!panels.news">
      <div v-if="newsError" class="error">
        {{ newsError }}
      </div>

      <div v-else class="news-grid">
        <div class="tier">
          <div class="tier-header">
            <h3>N1：市場重定價</h3>
            <span class="count">{{ n1Items.length }}</span>
          </div>
          <div v-if="n1Items.length === 0" class="empty">目前沒有 N1</div>
          <article v-for="item in n1Items" :key="item.id" class="news-card n1">
            <div class="news-title">
              <h4>{{ item.title }}</h4>
              <span class="score-pill">Score {{ item.score ?? "-" }}</span>
            </div>
            <p>{{ item.summary_zh }}</p>
            <a
              v-if="item.source_url"
              class="news-link"
              :href="item.source_url"
              target="_blank"
              rel="noopener noreferrer"
            >
              開啟原文
            </a>
            <div class="meta">
              <span>{{ item.published_at }}</span>
              <span>Symbols: {{ item.symbols.join(", ") || "-" }}</span>
            </div>
            <div class="meta">
              <span>Groups: {{ item.factor_groups.join(", ") || "-" }}</span>
              <span>Themes: {{ item.themes.join(", ") || "-" }}</span>
            </div>
            <div class="trigger">
              <span v-for="(t, idx) in item.falsifiable_triggers" :key="idx">
                {{ t.name }} · {{ t.condition }} · {{ t.value }}
              </span>
            </div>
          </article>
        </div>

        <div class="tier">
          <div class="tier-header">
            <h3>N3：值得追蹤</h3>
            <span class="count">{{ n3Items.length }}</span>
          </div>
          <div v-if="n3Items.length === 0" class="empty">目前沒有 N3</div>
          <article v-for="item in n3Items" :key="item.id" class="news-card">
            <div class="news-title">
              <h4>{{ item.title }}</h4>
              <span class="score-pill">Score {{ item.score ?? "-" }}</span>
            </div>
            <p>{{ item.summary_zh }}</p>
            <a
              v-if="item.source_url"
              class="news-link"
              :href="item.source_url"
              target="_blank"
              rel="noopener noreferrer"
            >
              開啟原文
            </a>
            <div class="meta">
              <span>{{ item.published_at }}</span>
              <span>Symbols: {{ item.symbols.join(", ") || "-" }}</span>
            </div>
            <div class="meta">
              <span>Groups: {{ item.factor_groups.join(", ") || "-" }}</span>
              <span>Themes: {{ item.themes.join(", ") || "-" }}</span>
            </div>
            <div class="trigger">
              <span v-for="(t, idx) in item.falsifiable_triggers" :key="idx">
                {{ t.name }} · {{ t.condition }} · {{ t.value }}
              </span>
            </div>
          </article>
        </div>
      </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-header">
        <h2>編輯核心持股</h2>
        <span class="badge">portfolio-service</span>
        <button class="collapse-btn" type="button" @click="togglePanel('coreHoldings')">
          {{ panels.coreHoldings ? "展開" : "收合" }}
        </button>
      </div>

      <div v-show="!panels.coreHoldings">
        <div v-if="holdingsError" class="error">
          {{ holdingsError }}
        </div>

        <div v-else class="holdings-grid">
          <div v-if="holdingsLoading" class="empty">讀取中...</div>
          <div v-else-if="holdings.length === 0" class="empty">尚無持股清單</div>
          <div v-else class="holdings-list">
            <label v-for="item in holdings" :key="item.symbol" class="holding-item">
              <input type="checkbox" v-model="item.selected" />
              <span class="holding-symbol">{{ item.symbol }}</span>
              <span class="holding-name">{{ item.name }}</span>
            </label>
          </div>
          <p v-if="holdingsHint" class="hint">{{ holdingsHint }}</p>
          <div class="holdings-actions">
            <button class="refresh" type="button" @click="syncPortfolio" :disabled="holdingsSyncing">
              {{ holdingsSyncing ? "同步中..." : "同步交易" }}
            </button>
            <span class="action-note">從交易來源匯入並補齊 name_zh</span>
            <button
              class="refresh"
              type="button"
              @click="rebuildPositions"
              :disabled="holdingsRebuilding"
            >
              {{ holdingsRebuilding ? "重建中..." : "重建持股" }}
            </button>
            <span class="action-note">依 trades 重新計算 positions</span>
            <button
              class="refresh"
              type="button"
              @click="saveCoreHoldings"
              :disabled="holdingsSaving || holdingsLoading || holdingsEmpty"
            >
              {{ holdingsSaving ? "儲存中..." : "儲存核心持股" }}
            </button>
            <span class="action-note">把勾選清單寫入 core_holdings</span>
            <p class="timestamp" v-if="holdingsSavedAt">已儲存：{{ holdingsSavedAt }}</p>
          </div>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-header">
        <h2>持股明細</h2>
        <span class="badge">portfolio-service</span>
        <button class="collapse-btn" type="button" @click="togglePanel('positions')">
          {{ panels.positions ? "展開" : "收合" }}
        </button>
      </div>

      <div v-show="!panels.positions">
        <div v-if="holdingsLoading" class="empty">讀取中...</div>
        <div v-else-if="positions.length === 0" class="empty">尚無持股資料</div>
        <div v-else class="positions-table">
          <div class="positions-row positions-header">
            <span>代碼</span>
            <span>名稱</span>
            <span>幣別</span>
            <span class="number">數量</span>
            <span class="number">均價</span>
            <span class="number">成本</span>
            <span class="number">已實現損益</span>
          </div>
          <div v-for="pos in positions" :key="pos.symbol" class="positions-row">
            <span class="symbol">{{ pos.symbol }}</span>
            <span>{{ pos.name_zh || '-' }}</span>
            <span>{{ pos.asset_ccy }}</span>
            <span class="number">{{ Number(pos.quantity).toLocaleString('zh-TW', { maximumFractionDigits: 4 }) }}</span>
            <span class="number">{{ Number(pos.avg_cost).toLocaleString('zh-TW', { minimumFractionDigits: 2, maximumFractionDigits: 4 }) }}</span>
            <span class="number">{{ Number(pos.cost_basis).toLocaleString('zh-TW', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</span>
            <span class="number" :class="{ positive: Number(pos.realized_pnl) > 0, negative: Number(pos.realized_pnl) < 0 }">
              {{ Number(pos.realized_pnl).toLocaleString('zh-TW', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}
            </span>
          </div>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-header">
        <h2>資產中文名稱維護</h2>
        <span class="badge">portfolio-service</span>
        <button class="collapse-btn" type="button" @click="togglePanel('mappings')">
          {{ panels.mappings ? "展開" : "收合" }}
        </button>
      </div>

      <div v-show="!panels.mappings">
        <div v-if="mappingsError" class="error">
          {{ mappingsError }}
        </div>

        <div class="mapping-form">
          <label class="mapping-field">
            <span>Symbol</span>
            <input v-model="mappingSymbol" placeholder="例如：AAPL / 2330.TW" />
          </label>
          <label class="mapping-field">
            <span>Market</span>
            <select v-model="mappingMarket">
              <option value="US">US</option>
              <option value="TW">TW</option>
            </select>
          </label>
          <label class="mapping-field">
            <span>中文名稱</span>
            <input v-model="mappingNameZh" placeholder="輸入中文名稱" />
          </label>
          <div class="holdings-actions">
            <button class="refresh" type="button" @click="resolveSymbolMapping" :disabled="mappingResolving">
              {{ mappingResolving ? "查詢中..." : "自動查詢" }}
            </button>
            <span class="action-note">用 symbol 查詢中文名稱</span>
            <button class="refresh" type="button" @click="saveSymbolMapping" :disabled="mappingSaving">
              {{ mappingSaving ? "儲存中..." : "儲存映射" }}
            </button>
            <span class="action-note">手動覆寫或補齊名稱</span>
            <p class="timestamp" v-if="mappingsUpdatedAt">已更新：{{ mappingsUpdatedAt }}</p>
          </div>
        </div>

        <div v-if="mappingsLoading" class="empty">讀取中...</div>
        <div v-else-if="symbolMappings.length === 0" class="empty">尚無資料</div>
        <div v-else class="mapping-table">
          <div class="mapping-row mapping-header">
            <span>Symbol</span>
            <span>Market</span>
            <span>中文名稱</span>
            <span>來源</span>
          </div>
          <div v-for="row in symbolMappings" :key="`${row.symbol}-${row.market}`" class="mapping-row">
            <span>{{ row.symbol }}</span>
            <span>{{ row.market }}</span>
            <span>{{ row.name_zh }}</span>
            <span>{{ row.source }}</span>
          </div>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-header">
        <h2>戰情室｜融合決策包</h2>
        <span class="badge">radar-service</span>
        <button class="collapse-btn" type="button" @click="togglePanel('decision')">
          {{ panels.decision ? "展開" : "收合" }}
        </button>
      </div>

      <div v-show="!panels.decision">
      <div v-if="decisionError" class="error">
        {{ decisionError }}
      </div>

      <div v-else-if="decisionPackage" class="decision-grid">
        <div class="decision-card">
          <p class="section-title">決策摘要</p>
          <div class="pill-row">
            <span class="pill">{{ decisionPackage.mode }}</span>
            <span class="pill pill-accent">{{ decisionPackage.decision }}</span>
          </div>
          <p class="hash">inputs_hash: {{ decisionPackage.evidence?.inputs_hash }}</p>
        </div>

        <div class="decision-card">
          <p class="section-title">新聞融合影響</p>
          <div class="meta">
            <span>N1：{{ decisionPackage.evidence?.news_context?.tiers_count?.N1 ?? 0 }}</span>
            <span>N3：{{ decisionPackage.evidence?.news_context?.tiers_count?.N3 ?? 0 }}</span>
            <span>Risk score：{{ decisionPackage.evidence?.news_context?.score_impact?.risk_off_score_added ?? 0 }}</span>
          </div>
          <p class="section-subtitle">引用新聞</p>
          <div class="tag-list">
            <span
              v-for="(item, idx) in decisionPackage.evidence?.news_context?.items_used || []"
              :key="`${item}-${idx}`"
              class="tag"
            >
              {{ item }}
            </span>
          </div>
        </div>

        <div class="decision-card">
          <p class="section-title">融合決策說明</p>
          <p class="decision-text">{{ decisionSummary }}</p>
        </div>

        <div class="decision-card wide">
          <p class="section-title">決策過程（scoring_detail）</p>
          <pre class="code-block">
{{ JSON.stringify(decisionPackage.evidence?.scoring_detail || {}, null, 2) }}
          </pre>
        </div>

        <div class="decision-card wide">
          <p class="section-title">融合後 actions + triggers</p>
          <div v-if="(decisionPackage.actions || []).length === 0" class="empty">目前沒有 action</div>
          <div v-else class="action-grid">
            <article v-for="action in decisionPackage.actions" :key="action.symbol" class="action-card">
              <h4>{{ action.symbol }}</h4>
              <p class="pill">{{ action.action }}</p>
              <p class="meta">{{ action.reason }}</p>
              <div class="trigger">
                <span v-for="(t, idx) in action.falsifiable_triggers" :key="idx">
                  {{ t.name }} · {{ t.condition }} · {{ t.value }}
                </span>
              </div>
            </article>
          </div>
        </div>
      </div>

      <div v-else class="empty">尚未取得決策包</div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-header">
        <h2>Decision History + Outcome</h2>
        <span class="badge">radar-service</span>
        <button class="collapse-btn" type="button" @click="togglePanel('decisionHistory')">
          {{ panels.decisionHistory ? "展開" : "收合" }}
        </button>
      </div>

      <div v-show="!panels.decisionHistory">
        <div v-if="decisionHistoryError" class="error">
          {{ decisionHistoryError }}
        </div>
        <div v-else-if="decisionHistoryLoading" class="empty">讀取中...</div>
        <div v-else-if="decisionHistory.length === 0" class="empty">尚無歷史紀錄</div>
        <div v-else class="decision-history">
          <div class="decision-row decision-header">
            <span>as_of</span>
            <span>mode</span>
            <span>decision</span>
            <span>inputs_hash</span>
            <span>outcome</span>
            <span>note</span>
            <span>actions</span>
          </div>
          <template v-for="row in decisionHistory" :key="row.inputs_hash">
            <div class="decision-row">
              <span class="mono">{{ row.as_of }}</span>
              <span class="pill">{{ row.mode }}</span>
              <span class="pill pill-accent">{{ row.decision }}</span>
              <span class="mono">{{ row.inputs_hash }}</span>
              <span class="badge" :class="{ good: getOutcome(row.inputs_hash).outcome_label === 'win', neutral: getOutcome(row.inputs_hash).outcome_label !== 'win' }">
                {{ getOutcome(row.inputs_hash).outcome_label }}
              </span>
              <span class="note">{{ formatNotePreview(getOutcome(row.inputs_hash).outcome_note) }}</span>
              <span class="actions">
                <button class="ghost" type="button" @click="startOutcomeEdit(row)">編輯</button>
              </span>
            </div>
            <div v-if="outcomeEditing === row.inputs_hash" class="decision-edit">
              <label>
                <span>Outcome</span>
                <select v-model="outcomeDrafts[row.inputs_hash].label">
                  <option value="unknown">unknown</option>
                  <option value="neutral">neutral</option>
                  <option value="win">win</option>
                  <option value="loss">loss</option>
                </select>
              </label>
              <label class="wide">
                <span>Note</span>
                <textarea v-model="outcomeDrafts[row.inputs_hash].note" rows="3"></textarea>
              </label>
              <div class="edit-actions">
                <button class="refresh" type="button" @click="saveOutcome(row)">Save</button>
                <button class="ghost" type="button" @click="cancelOutcomeEdit">Cancel</button>
              </div>
            </div>
          </template>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-header">
        <h2>Outcome Analytics</h2>
        <span class="badge">radar-service</span>
        <button class="collapse-btn" type="button" @click="togglePanel('analytics')">
          {{ panels.analytics ? "展開" : "收合" }}
        </button>
      </div>

      <div v-show="!panels.analytics">
        <div v-if="analyticsError" class="error">
          {{ analyticsError }}
        </div>
        <div v-else-if="analyticsLoading" class="empty">讀取中...</div>
        <div v-else class="analytics-grid">
          <div class="analytics-card">
            <div class="analytics-title">
              <h3>Trigger Hit Rate</h3>
              <span class="meta">近 30 天</span>
            </div>
            <div v-if="suspiciousTriggers.length > 0" class="suspicious-list">
              <p class="section-subtitle">最可疑 triggers</p>
              <div v-for="(row, idx) in suspiciousTriggers" :key="`${row.trigger_key}-${idx}`" class="suspicious-row">
                <span class="mono key">{{ row.trigger_key }}</span>
                <span class="badge neutral">loss {{ formatRate(row.loss_rate) }}</span>
                <span class="meta">total {{ row.total }}</span>
              </div>
            </div>
            <div v-if="sortedTriggerAnalytics.length === 0" class="empty">尚無 trigger outcomes</div>
            <div v-else class="analytics-table">
              <div class="analytics-row analytics-header">
                <span>trigger_key</span>
                <span>total</span>
                <span>wins</span>
                <span>losses</span>
                <span>neutral</span>
                <span>win_rate</span>
              </div>
              <div
                v-for="(row, idx) in sortedTriggerAnalytics"
                :key="`${row.trigger_key}-${idx}`"
                class="analytics-row"
              >
                <span class="mono key">{{ row.trigger_key }}</span>
                <span>{{ row.total }}</span>
                <span>{{ row.wins }}</span>
                <span>{{ row.losses }}</span>
                <span>{{ row.neutral }}</span>
                <span>{{ formatRate(row.win_rate) }}</span>
              </div>
            </div>
          </div>

          <div class="analytics-card">
            <div class="analytics-title">
              <h3>Decision Outcome</h3>
              <div class="analytics-toggle">
                <span class="meta">by</span>
                <select v-model="decisionAnalyticsGroup">
                  <option value="tier">tier</option>
                  <option value="decision">decision</option>
                </select>
              </div>
            </div>
            <div v-if="sortedDecisionAnalytics.length === 0" class="empty">尚無 outcomes</div>
            <div v-else class="analytics-table">
              <div class="analytics-row analytics-header">
                <span>{{ decisionAnalyticsGroup }}</span>
                <span>total</span>
                <span>wins</span>
                <span>losses</span>
                <span>neutral</span>
                <span>win_rate</span>
              </div>
              <div
                v-for="(row, idx) in sortedDecisionAnalytics"
                :key="`${row.label || row[decisionAnalyticsGroup] || 'item'}-${idx}`"
                class="analytics-row"
              >
                <span class="pill">{{ row.label || row[decisionAnalyticsGroup] }}</span>
                <span>{{ row.total }}</span>
                <span>{{ row.wins }}</span>
                <span>{{ row.losses }}</span>
                <span>{{ row.neutral }}</span>
                <span>{{ formatRate(row.win_rate) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="panel subtle">
      <div class="panel-header">
        <h2>健康檢查總覽</h2>
        <button class="collapse-btn" type="button" @click="togglePanel('health')">
          {{ panels.health ? "展開" : "收合" }}
        </button>
      </div>
      <div v-show="!panels.health">
        <ul>
          <li v-for="item in healthMessages" :key="item.name">
            <strong>{{ item.name }}</strong>
            <span>{{ item.message }}</span>
          </li>
        </ul>
      </div>
    </section>
    
    <section class="panel">
      <div class="panel-header">
        <h2>Trigger Timeline</h2>
        <span class="badge">radar-service</span>
        <button class="collapse-btn" type="button" @click="togglePanel('triggers')">
          {{ panels.triggers ? "展開" : "收合" }}
        </button>
      </div>

      <div v-show="!panels.triggers">
        <div class="trigger-filters">
          <label>
            <span>from</span>
            <input type="date" v-model="triggerFilters.from" />
          </label>
          <label>
            <span>to</span>
            <input type="date" v-model="triggerFilters.to" />
          </label>
          <label>
            <span>plugin</span>
            <input v-model="triggerFilters.plugin" placeholder="v1.4" />
          </label>
          <label>
            <span>is_triggered</span>
            <select v-model="triggerFilters.is_triggered">
              <option value="all">all</option>
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          </label>
          <label>
            <span>trigger_type</span>
            <select v-model="triggerFilters.trigger_type">
              <option v-for="option in triggerTypeOptions" :key="option" :value="option">
                {{ option }}
              </option>
            </select>
          </label>
          <label>
            <span>limit</span>
            <input type="number" min="1" max="500" v-model.number="triggerFilters.limit" />
          </label>
          <button class="refresh" type="button" @click="fetchTriggerHistory" :disabled="triggerLoading">
            {{ triggerLoading ? "查詢中..." : "查詢" }}
          </button>
        </div>

        <div v-if="triggerError" class="error">
          {{ triggerError }}
        </div>

        <div v-else-if="triggerLoading" class="empty">讀取中...</div>

        <div v-else-if="triggerItems.length === 0" class="empty">尚無 triggers</div>

        <div v-else class="trigger-table">
          <div class="trigger-row trigger-header">
            <span>evaluated_at</span>
            <span>as_of</span>
            <span>trigger_key</span>
            <span>type</span>
            <span>is_triggered</span>
            <span>observed_value</span>
            <span>decision_inputs_hash</span>
            <span>actions</span>
          </div>

          <template v-for="(row, idx) in triggerItems" :key="triggerRowKey(row, idx)">
            <div class="trigger-row">
              <span class="mono">{{ row.evaluated_at }}</span>
              <span class="mono">{{ row.as_of }}</span>
              <span class="mono key">{{ row.trigger_key }}</span>
              <span class="pill">{{ row.trigger_type }}</span>
              <span class="badge" :class="{ good: row.is_triggered, neutral: !row.is_triggered }">
                {{ row.is_triggered ? "true" : "false" }}
              </span>
              <span class="mono preview">{{ formatObservedPreview(row.observed_value) }}</span>
              <span class="mono hash">
                {{ row.decision_inputs_hash }}
              </span>
              <span class="actions">
                <button type="button" class="ghost" @click="toggleTriggerDetails(triggerRowKey(row, idx))">
                  {{ triggerExpanded.has(triggerRowKey(row, idx)) ? "收合" : "展開" }}
                </button>
                <button type="button" class="ghost" @click="toggleTriggerDrilldown(triggerRowKey(row, idx))">
                  同批
                </button>
                <button type="button" class="ghost" @click="copyHash(row.decision_inputs_hash)">
                  copy
                </button>
              </span>
            </div>

            <div
              v-if="triggerExpanded.has(triggerRowKey(row, idx))"
              class="trigger-detail"
            >
              <p class="detail-title">observed_value</p>
              <pre class="code-block">{{ JSON.stringify(row.observed_value || {}, null, 2) }}</pre>
            </div>

            <div
              v-if="triggerDrilldown.has(triggerRowKey(row, idx))"
              class="trigger-detail"
            >
              <p class="detail-title">同 decision_inputs_hash 的 triggers</p>
              <div class="drilldown-list">
                <div
                  v-for="(item, subIdx) in groupedByInputsHash.get(row.decision_inputs_hash) || []"
                  :key="`${row.decision_inputs_hash}-${subIdx}`"
                  class="drilldown-item"
                >
                  <span class="mono">{{ item.trigger_key }}</span>
                  <span class="pill">{{ item.trigger_type }}</span>
                  <span class="badge" :class="{ good: item.is_triggered, neutral: !item.is_triggered }">
                    {{ item.is_triggered ? "true" : "false" }}
                  </span>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped>
@import url("https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=Noto+Sans+TC:wght@400;600&display=swap");

:global(body) {
  margin: 0;
  font-family: "Space Grotesk", "Noto Sans TC", "Microsoft JhengHei", sans-serif;
  background: radial-gradient(circle at top, #102a43 0%, #0b1324 45%, #05070f 100%);
  color: #e2e8f0;
}

.container {
  min-height: 100vh;
  padding: 3rem 1.5rem;
  max-width: 1100px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.hero {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1.5rem;
}

.eyebrow {
  text-transform: uppercase;
  letter-spacing: 0.2em;
  font-size: 0.75rem;
  color: #93c5fd;
  margin: 0 0 0.75rem;
}

h1 {
  margin: 0 0 0.5rem;
  font-size: clamp(2.5rem, 4vw, 3.5rem);
}

.subtitle {
  margin: 0;
  color: #cbd5f5;
  font-size: 1.05rem;
}

.hero-card {
  min-width: 220px;
  background: linear-gradient(145deg, rgba(34, 197, 94, 0.15), rgba(15, 23, 42, 0.8));
  border: 1px solid rgba(34, 197, 94, 0.4);
  border-radius: 16px;
  padding: 1rem 1.25rem;
  display: grid;
  gap: 0.75rem;
}

.label {
  margin: 0;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: #86efac;
}

.value {
  margin: 0.2rem 0 0;
  font-size: 1.1rem;
  font-weight: 600;
}

.refresh {
  border: none;
  border-radius: 999px;
  padding: 0.5rem 1rem;
  font-weight: 600;
  background: #22c55e;
  color: #052e16;
  cursor: pointer;
}

.refresh:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.timestamp {
  margin: 0;
  font-size: 0.8rem;
  color: #bbf7d0;
}

.mapping-form {
  display: grid;
  gap: 0.75rem;
  margin: 1rem 0;
}

.mapping-field {
  display: grid;
  gap: 0.35rem;
  font-size: 0.9rem;
  color: #cbd5f5;
}

.mapping-field input,
.mapping-field select {
  padding: 0.5rem 0.75rem;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.4);
  background: rgba(15, 23, 42, 0.7);
  color: #e2e8f0;
}

.mapping-table {
  display: grid;
  gap: 0.5rem;
}

.mapping-row {
  display: grid;
  grid-template-columns: 1.2fr 0.6fr 1.6fr 1fr;
  gap: 0.5rem;
  padding: 0.6rem 0.75rem;
  background: rgba(15, 23, 42, 0.6);
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.2);
}

.mapping-header {
  font-weight: 600;
  color: #93c5fd;
}

.positions-table {
  display: grid;
  gap: 0.5rem;
  overflow-x: auto;
}

.positions-row {
  display: grid;
  grid-template-columns: 1fr 1.5fr 0.6fr 1fr 1fr 1.2fr 1.2fr;
  gap: 0.5rem;
  padding: 0.6rem 0.75rem;
  background: rgba(15, 23, 42, 0.6);
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  min-width: 700px;
}

.positions-header {
  font-weight: 600;
  color: #93c5fd;
}

.positions-row .symbol {
  font-weight: 600;
  color: #93c5fd;
}

.positions-row .number {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.positions-row .positive {
  color: #4ade80;
}

.positions-row .negative {
  color: #f87171;
}

.panel {
  background: rgba(10, 15, 30, 0.85);
  border: 1px solid rgba(94, 234, 212, 0.2);
  border-radius: 18px;
  padding: 1.75rem;
  box-shadow: 0 20px 40px rgba(5, 7, 15, 0.6);
}

.panel.subtle {
  border-color: rgba(148, 163, 184, 0.2);
}

ul {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

li {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1rem;
  background: rgba(30, 41, 59, 0.7);
  border-radius: 8px;
}

strong {
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #7dd3fc;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.badge {
  font-size: 0.75rem;
  padding: 0.3rem 0.6rem;
  background: rgba(148, 163, 184, 0.2);
  border-radius: 999px;
  color: #e2e8f0;
}

.collapse-btn {
  font-size: 0.75rem;
  padding: 0.35rem 0.7rem;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.35);
  background: rgba(15, 23, 42, 0.6);
  color: #e2e8f0;
  cursor: pointer;
}

.collapse-btn:hover {
  border-color: rgba(226, 232, 240, 0.7);
}

.decision-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 1.25rem;
}

.decision-card {
  background: rgba(15, 23, 42, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 14px;
  padding: 1rem;
  display: grid;
  gap: 0.75rem;
}

.decision-card.wide {
  grid-column: 1 / -1;
}

.decision-history {
  display: grid;
  gap: 0.5rem;
}

.decision-row {
  display: grid;
  grid-template-columns: 120px 100px 120px minmax(0, 1.6fr) 120px minmax(0, 1fr) 120px;
  gap: 0.75rem;
  align-items: center;
  padding: 0.6rem 0.75rem;
  background: rgba(15, 23, 42, 0.7);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 12px;
  font-size: 0.78rem;
}

.decision-header {
  background: rgba(30, 41, 59, 0.9);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 0.7rem;
  color: #cbd5f5;
}

.decision-row .note {
  color: #cbd5f5;
}

.decision-edit {
  margin: 0.25rem 0 0.75rem;
  padding: 0.75rem 1rem;
  border-radius: 12px;
  background: rgba(9, 14, 28, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.2);
  display: grid;
  gap: 0.75rem;
}

.decision-edit label {
  display: grid;
  gap: 0.35rem;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #94a3b8;
}

.decision-edit select,
.decision-edit textarea {
  padding: 0.5rem 0.6rem;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.3);
  background: rgba(15, 23, 42, 0.7);
  color: #e2e8f0;
}

.decision-edit .wide {
  grid-column: 1 / -1;
}

.edit-actions {
  display: flex;
  gap: 0.6rem;
  justify-content: flex-end;
}

.analytics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1rem;
}

.analytics-card {
  background: rgba(15, 23, 42, 0.85);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 14px;
  padding: 1rem;
  display: grid;
  gap: 0.8rem;
}

.analytics-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.analytics-toggle {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.analytics-toggle select {
  padding: 0.3rem 0.5rem;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.3);
  background: rgba(15, 23, 42, 0.7);
  color: #e2e8f0;
  font-size: 0.75rem;
}

.analytics-title h3 {
  margin: 0;
  font-size: 0.95rem;
  color: #e2e8f0;
}

.analytics-table {
  display: grid;
  gap: 0.4rem;
}

.analytics-row {
  display: grid;
  grid-template-columns: minmax(0, 2fr) 70px 70px 70px 70px 90px;
  gap: 0.6rem;
  align-items: center;
  padding: 0.5rem 0.65rem;
  background: rgba(15, 23, 42, 0.7);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 12px;
  font-size: 0.78rem;
}

.analytics-header {
  background: rgba(30, 41, 59, 0.9);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 0.7rem;
  color: #cbd5f5;
}

.suspicious-list {
  display: grid;
  gap: 0.4rem;
}

.suspicious-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.45rem 0.6rem;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.65);
  border: 1px solid rgba(148, 163, 184, 0.2);
  font-size: 0.75rem;
}

@media (max-width: 960px) {
  .decision-row {
    grid-template-columns: 1fr;
  }
  .analytics-row {
    grid-template-columns: 1fr;
  }
}

.section-title {
  margin: 0;
  font-size: 0.95rem;
  color: #e2e8f0;
}

.section-subtitle {
  margin: 0.5rem 0 0;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #94a3b8;
}

.decision-text {
  margin: 0;
  font-size: 0.9rem;
  color: #cbd5f5;
  line-height: 1.5;
}

.pill-row {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.3rem 0.7rem;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.2);
  color: #bfdbfe;
  font-size: 0.75rem;
}

.pill-accent {
  background: rgba(34, 197, 94, 0.2);
  color: #bbf7d0;
}

.hash {
  font-size: 0.75rem;
  color: #94a3b8;
  word-break: break-all;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.tag {
  background: rgba(148, 163, 184, 0.2);
  padding: 0.2rem 0.5rem;
  border-radius: 8px;
  font-size: 0.7rem;
  color: #e2e8f0;
}

.code-block {
  background: rgba(8, 12, 25, 0.9);
  color: #c7d2fe;
  font-size: 0.75rem;
  padding: 1rem;
  border-radius: 12px;
  overflow-x: auto;
}

.trigger-filters {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 0.75rem;
  margin-bottom: 1rem;
  align-items: end;
}

.trigger-filters label {
  display: grid;
  gap: 0.35rem;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #94a3b8;
}

.trigger-filters input,
.trigger-filters select {
  padding: 0.5rem 0.6rem;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.3);
  background: rgba(15, 23, 42, 0.7);
  color: #e2e8f0;
}

.trigger-table {
  display: grid;
  gap: 0.4rem;
  overflow-x: auto;
}

.trigger-row {
  display: grid;
  grid-template-columns: 140px 110px minmax(0, 1.6fr) 110px 110px minmax(0, 1.2fr) minmax(0, 1.2fr) 160px;
  gap: 0.75rem;
  align-items: center;
  padding: 0.6rem 0.75rem;
  background: rgba(15, 23, 42, 0.7);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 12px;
  font-size: 0.78rem;
  width: 100%;
  box-sizing: border-box;
}

.trigger-row > span {
  min-width: 0;
}

.trigger-header {
  background: rgba(30, 41, 59, 0.9);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 0.7rem;
  color: #cbd5f5;
}

.mono {
  font-family: "JetBrains Mono", "Fira Code", monospace;
  word-break: break-all;
}

.trigger-row .key {
  color: #93c5fd;
}

.trigger-row .preview {
  color: #cbd5f5;
}

.trigger-row .hash {
  color: #a5b4fc;
}

.trigger-row .actions {
  display: flex;
  gap: 0.4rem;
}

.ghost {
  border: 1px solid rgba(148, 163, 184, 0.4);
  background: transparent;
  color: #e2e8f0;
  padding: 0.25rem 0.5rem;
  border-radius: 8px;
  font-size: 0.7rem;
  cursor: pointer;
}

.ghost:hover {
  border-color: rgba(148, 163, 184, 0.8);
}

.badge.good {
  background: rgba(34, 197, 94, 0.2);
  color: #86efac;
}

.badge.neutral {
  background: rgba(148, 163, 184, 0.2);
  color: #e2e8f0;
}

.trigger-detail {
  margin: 0.25rem 0 0.75rem;
  padding: 0.75rem 1rem;
  border-radius: 12px;
  background: rgba(9, 14, 28, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.2);
  overflow-x: auto;
}

.detail-title {
  margin: 0 0 0.5rem;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: #7dd3fc;
}

.drilldown-list {
  display: grid;
  gap: 0.5rem;
}

.drilldown-item {
  display: flex;
  gap: 0.6rem;
  align-items: center;
  flex-wrap: wrap;
}

@media (max-width: 960px) {
  .trigger-row {
    grid-template-columns: 1fr;
    gap: 0.35rem;
  }
}

.action-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1rem;
}

.action-card {
  background: rgba(11, 18, 32, 0.95);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 12px;
  padding: 0.8rem;
  display: grid;
  gap: 0.4rem;
}

.news-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 1.5rem;
}

.tier-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.count {
  font-size: 0.9rem;
  color: #93c5fd;
}

.news-card {
  background: rgba(15, 23, 42, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 14px;
  padding: 1rem;
  display: grid;
  gap: 0.5rem;
}

.news-card.n1 {
  border-color: rgba(244, 63, 94, 0.6);
  box-shadow: 0 12px 28px rgba(244, 63, 94, 0.15);
}

.news-card h4 {
  margin: 0;
  font-size: 1.05rem;
}

.news-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.score-pill {
  font-size: 0.7rem;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  background: rgba(56, 189, 248, 0.15);
  color: #7dd3fc;
  border: 1px solid rgba(125, 211, 252, 0.35);
  white-space: nowrap;
  font-weight: 700;
}

.news-card p {
  margin: 0;
  color: #cbd5f5;
  font-size: 0.9rem;
}

.news-link {
  display: inline-flex;
  width: fit-content;
  font-size: 0.75rem;
  color: #93c5fd;
  text-decoration: none;
}

.news-link:hover {
  text-decoration: underline;
}

.holdings-grid {
  display: grid;
  gap: 1rem;
}

.holdings-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0.75rem;
}

.holding-item {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.6rem 0.8rem;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.85);
  border: 1px solid rgba(148, 163, 184, 0.2);
  font-size: 0.85rem;
}

.holding-item input {
  accent-color: #22c55e;
}

.holding-symbol {
  font-weight: 600;
  color: #93c5fd;
}

.holding-name {
  color: #cbd5f5;
}

.holdings-actions {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.action-note {
  font-size: 0.75rem;
  color: #94a3b8;
}

.meta {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  font-size: 0.75rem;
  color: #94a3b8;
}

.trigger {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  font-size: 0.75rem;
  color: #a5b4fc;
}

.empty {
  font-size: 0.9rem;
  color: #94a3b8;
  margin-bottom: 1rem;
}

.error {
  padding: 0.75rem 1rem;
  border-radius: 10px;
  background: rgba(248, 113, 113, 0.15);
  border: 1px solid rgba(248, 113, 113, 0.4);
  color: #fecaca;
}

@media (max-width: 600px) {
  li {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.25rem;
  }

  .hero {
    flex-direction: column;
  }
}
</style>
