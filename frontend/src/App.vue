<script setup>
import { computed, onMounted, ref } from "vue";
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
const coverage = ref(null);
const attributionTriggers = ref([]);
const attributionTiers = ref([]);
const analyticsLoading = ref(false);
const analyticsError = ref("");
const errorLogs = ref([]);
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
const triggerTimelineItems = ref([]);
const triggerTimelineLoading = ref(false);
const triggerTimelineError = ref("");
const showOtherTimelineTriggers = ref(false);
const TRIGGER_TIMELINE_DAYS = 14;
const panels = ref({
  news: false,
  coreHoldings: true,
  positions: true,
  mappings: true,
  decision: true,
  decisionHistory: false,
  analytics: false,
  errorLog: false,
  triggers: false,
  triggersTimeline: false,
  health: true,
});

const togglePanel = (key) => {
  panels.value[key] = !panels.value[key];
};

const todayMode = computed(() => decisionPackage.value?.mode || "UNKNOWN");
const todayDecision = computed(() => decisionPackage.value?.decision || "UNKNOWN");
const todayInputsHash = computed(() => decisionPackage.value?.evidence?.inputs_hash || "");
const todayStatusText = computed(() => {
  if (decisionLoading.value) {
    return "決策載入中";
  }
  if (decisionError.value) {
    return "決策讀取失敗";
  }
  if (!decisionPackage.value) {
    return "尚未取得今日決策";
  }
  return "今日決策已更新";
});
const todayModeClass = computed(() => {
  if (todayMode.value === "RISK_ON") {
    return "risk-on";
  }
  if (todayMode.value === "RISK_OFF") {
    return "risk-off";
  }
  if (todayMode.value === "TRANSITION") {
    return "transition";
  }
  return "unknown";
});
const todayDecisionClass = computed(() => {
  if (todayDecision.value === "NO_ACTION") {
    return "decision-neutral";
  }
  if (todayDecision.value === "UNKNOWN") {
    return "decision-unknown";
  }
  return "decision-alert";
});
const todayDecisionNote = computed(() => {
  if (todayDecision.value === "NO_ACTION") {
    return "僅表示目前無新增權限狀態";
  }
  if (todayDecision.value === "UNKNOWN") {
    return "狀態尚未判定";
  }
  return "僅供狀態記錄";
});

const openPanelAndScroll = (key, elementId) => {
  panels.value[key] = false;
  requestAnimationFrame(() => {
    const el = document.getElementById(elementId);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
};

const n1Items = computed(() => newsItems.value.filter((item) => item.tier === "N1"));
const n3Items = computed(() => newsItems.value.filter((item) => item.tier === "N3"));
const formatSignalTriggerLine = (triggers) => {
  if (!Array.isArray(triggers) || triggers.length === 0) {
    return "未提供可證偽條件";
  }
  const rows = triggers
    .map((trigger) => {
      const parts = [trigger?.name, trigger?.condition, trigger?.value]
        .filter((value) => value !== null && value !== undefined && String(value).trim() !== "")
        .map((value) => (typeof value === "object" ? JSON.stringify(value) : String(value)));
      return parts.join(" · ");
    })
    .filter((row) => row.length > 0);
  return rows.length > 0 ? rows.join("；") : "未提供可證偽條件";
};
const formatSignalSourceLabel = (item) => {
  const sourceName = String(item?.source || "").trim() || "媒體";
  return `來源：${sourceName} ↗`;
};
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

const addErrorLog = (source, err) => {
  const message = err?.message || String(err) || "unknown error";
  const entry = {
    id: `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
    time: new Date().toLocaleString("zh-TW"),
    source,
    message,
  };
  errorLogs.value = [entry, ...errorLogs.value].slice(0, 50);
};

const clearErrorLogs = () => {
  errorLogs.value = [];
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
    addErrorLog("portfolio/outcomes", err);
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
    addErrorLog("radar/decisions/history", err);
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
    addErrorLog("portfolio/outcomes list", err);
  }
};

const sortedTriggerAnalytics = computed(() => {
  return [...attributionTriggers.value].sort((a, b) => {
    const rateDiff = (Number(b.win_rate) || 0) - (Number(a.win_rate) || 0);
    if (rateDiff !== 0) {
      return rateDiff;
    }
    return (Number(b.total) || 0) - (Number(a.total) || 0);
  });
});

const sortedTierAnalytics = computed(() => {
  return [...attributionTiers.value].sort((a, b) => {
    const rateDiff = (Number(b.win_rate) || 0) - (Number(a.win_rate) || 0);
    if (rateDiff !== 0) {
      return rateDiff;
    }
    return (Number(b.total) || 0) - (Number(a.total) || 0);
  });
});

const suspiciousTriggers = computed(() => {
  const scored = attributionTriggers.value
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

const formatSeconds = (value) => {
  if (value === null || value === undefined) {
    return "-";
  }
  const seconds = Number(value);
  if (Number.isNaN(seconds)) {
    return "-";
  }
  return `${Math.round(seconds)}s`;
};

const fetchOutcomeAnalytics = async () => {
  analyticsLoading.value = true;
  analyticsError.value = "";
  try {
    const to = asOf.value;
    const fromDate = new Date(to);
    fromDate.setDate(fromDate.getDate() - 30);
    const from = fromDate.toISOString().slice(0, 10);
    const coverageParams = new URLSearchParams({
      user_id: USER_ID,
      plugin: "v1.4",
      from,
      to,
    });
    const triggerParams = new URLSearchParams({
      user_id: USER_ID,
      plugin: "v1.4",
      from,
      to,
      labeled_only: "false",
      only_triggered: "true",
    });
    const tierParams = new URLSearchParams({
      user_id: USER_ID,
      plugin: "v1.4",
      from,
      to,
      labeled_only: "false",
    });
    const [coverageResponse, triggerResponse, tierResponse] = await Promise.all([
      fetch(`${API_BASE_URL}/radar/analytics/coverage?${coverageParams.toString()}`),
      fetch(`${API_BASE_URL}/radar/analytics/attribution/triggers?${triggerParams.toString()}`),
      fetch(`${API_BASE_URL}/radar/analytics/attribution/tier?${tierParams.toString()}`),
    ]);
    if (!coverageResponse.ok) {
      throw new Error(`radar-service analytics ${coverageResponse.status}`);
    }
    if (!triggerResponse.ok) {
      throw new Error(`radar-service analytics ${triggerResponse.status}`);
    }
    if (!tierResponse.ok) {
      throw new Error(`radar-service analytics ${tierResponse.status}`);
    }
    coverage.value = await coverageResponse.json();
    const triggerPayload = await triggerResponse.json();
    const tierPayload = await tierResponse.json();
    attributionTriggers.value = triggerPayload.items || [];
    attributionTiers.value = tierPayload.items || [];
  } catch (err) {
    analyticsError.value = err?.message || "api-gateway 連線失敗";
    addErrorLog("radar/analytics", err);
  } finally {
    analyticsLoading.value = false;
  }
};

const selectedCoreItems = computed(() =>
  holdings.value
    .filter((item) => item.selected)
    .map((item) => ({
      symbol: item.symbol,
      name_zh: item.name_zh || "",
    })),
);
const holdingsEmpty = computed(() => holdings.value.length === 0);
const todayTriggeredItems = computed(() =>
  triggerItems.value.filter((row) => {
    const rowAsOf = String(row?.as_of || "").slice(0, 10);
    const triggered = row?.is_triggered === true || row?.is_triggered === "true";
    return triggered && rowAsOf === asOf.value;
  }),
);

const formatTriggeredStatement = (row) => {
  const observed = row?.observed_value;
  if (observed && typeof observed === "object") {
    const headline = String(observed.headline || "").trim();
    if (headline) {
      return headline;
    }
  }
  return "（未提供引用敘述）";
};

const formatObservedValue = (value) => {
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
};

const triggerTimelineDays = computed(() => {
  const days = [];
  const endDate = new Date(asOf.value);
  for (let i = TRIGGER_TIMELINE_DAYS - 1; i >= 0; i -= 1) {
    const date = new Date(endDate);
    date.setDate(endDate.getDate() - i);
    days.push(date.toISOString().slice(0, 10));
  }
  return days;
});

const buildTriggerTimelineRows = (rows) => {
  const keyMap = new Map();
  rows.forEach((row) => {
    const key = String(row?.trigger_key || "").trim();
    const day = String(row?.as_of || "").slice(0, 10);
    if (!key || !day) {
      return;
    }
    if (!keyMap.has(key)) {
      keyMap.set(key, new Set());
    }
    keyMap.get(key).add(day);
  });
  const days = triggerTimelineDays.value;
  return Array.from(keyMap.entries())
    .map(([triggerKey, daySet]) => {
      const dayHits = days.map((day) => daySet.has(day));
      const count = dayHits.filter(Boolean).length;
      let hasConsecutive = false;
      let isolatedCount = 0;
      for (let i = 0; i < dayHits.length; i += 1) {
        const hit = dayHits[i];
        if (!hit) {
          continue;
        }
        if ((i > 0 && dayHits[i - 1]) || (i < dayHits.length - 1 && dayHits[i + 1])) {
          hasConsecutive = true;
        } else {
          isolatedCount += 1;
        }
      }
      const singleDaySpikes = count > 0 && isolatedCount * 2 >= count;
      const insufficientHistory = count <= 1;
      return {
        trigger_key: triggerKey,
        count,
        has_consecutive: hasConsecutive ? "yes" : "no",
        single_day_spikes: singleDaySpikes ? "yes" : "no",
        insufficient_history: insufficientHistory,
        day_hits: dayHits,
        appeared_today: dayHits[dayHits.length - 1] === true,
      };
    })
    .sort((a, b) => {
      if (b.count !== a.count) {
        return b.count - a.count;
      }
      return a.trigger_key.localeCompare(b.trigger_key);
    });
};

const triggerTimelineRows = computed(() => buildTriggerTimelineRows(triggerTimelineItems.value));
const todayTimelineRows = computed(() => triggerTimelineRows.value.filter((row) => row.appeared_today));
const otherTimelineRows = computed(() => triggerTimelineRows.value.filter((row) => !row.appeared_today));

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

const fetchTodayTriggeredChecks = async () => {
  triggerLoading.value = true;
  triggerError.value = "";
  try {
    const params = new URLSearchParams({
      user_id: USER_ID,
      plugin: "v1.4",
      from: asOf.value,
      to: asOf.value,
      is_triggered: "true",
      limit: "200",
      offset: "0",
    });
    const url = `${API_BASE_URL}/radar/triggers/history?${params.toString()}`;
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`radar-service ${response.status}`);
    }
    const payload = await response.json();
    triggerItems.value = payload.items || [];
  } catch (err) {
    triggerError.value = err?.message || "api-gateway 連線失敗";
    addErrorLog("radar/triggers/history", err);
  } finally {
    triggerLoading.value = false;
  }
};

const fetchTriggerTimelineHistory = async () => {
  triggerTimelineLoading.value = true;
  triggerTimelineError.value = "";
  showOtherTimelineTriggers.value = false;
  try {
    const to = asOf.value;
    const fromDate = new Date(to);
    fromDate.setDate(fromDate.getDate() - (TRIGGER_TIMELINE_DAYS - 1));
    const from = fromDate.toISOString().slice(0, 10);
    const params = new URLSearchParams({
      user_id: USER_ID,
      plugin: "v1.4",
      from,
      to,
      is_triggered: "true",
      limit: "500",
      offset: "0",
    });
    const url = `${API_BASE_URL}/radar/triggers/history?${params.toString()}`;
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`radar-service ${response.status}`);
    }
    const payload = await response.json();
    triggerTimelineItems.value = payload.items || [];
  } catch (err) {
    triggerTimelineError.value = err?.message || "api-gateway 連線失敗";
    addErrorLog("radar/triggers/history timeline", err);
  } finally {
    triggerTimelineLoading.value = false;
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
    addErrorLog("news/signals", err);
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
    addErrorLog("radar/decision", err);
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
    addErrorLog("portfolio/holdings", err);
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
    addErrorLog("portfolio/sync", err);
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
    addErrorLog("portfolio/rebuild_positions", err);
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
    addErrorLog("portfolio/core_holdings", err);
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
    addErrorLog("portfolio/symbol_mappings", err);
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
    addErrorLog("portfolio/symbol_mappings/resolve", err);
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
    addErrorLog("portfolio/symbol_mappings", err);
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
    fetchTodayTriggeredChecks(),
    fetchTriggerTimelineHistory(),
    fetchOutcomeAnalytics(),
  ]);
  await fetchOutcomes();
};

onMounted(() => {
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

    <div class="decision-status-banner" :class="todayModeClass">
      <div class="banner-left">
        <p class="banner-title">TODAY｜System Decision Status</p>
        <div class="banner-pills">
          <span class="status-pill" :class="todayModeClass">{{ todayMode }}</span>
          <span class="status-pill" :class="todayDecisionClass">{{ todayDecision }}</span>
        </div>
        <p class="banner-note" v-if="todayDecision === 'NO_ACTION'">
          NO_ACTION 為系統狀態之一。
        </p>
        <p class="banner-note" v-else>此處僅顯示系統狀態，不提供行動建議。</p>
      </div>
      <div class="banner-right">
        <div class="banner-meta">
          <span>as_of {{ asOf }}</span>
          <span v-if="lastUpdated">更新 {{ lastUpdated }}</span>
        </div>
        <span class="banner-state" :class="{ error: decisionError }">{{ todayStatusText }}</span>
        <span v-if="decisionError" class="banner-error">{{ decisionError }}</span>
      </div>
    </div>

    <section class="today-zone">
      <div class="today-grid">
        <div class="today-card">
          <div class="today-card-header">
            <div>
              <p class="section-title">Decision Status</p>
              <p class="today-subtitle">此為系統狀態顯示，非行動建議。</p>
            </div>
            <span class="badge">radar-service</span>
          </div>
          <div class="today-kv">
            <div class="kv">
              <span class="kv-label">System Status</span>
              <span class="kv-value" :class="todayModeClass">{{ todayMode }}</span>
            </div>
            <div class="kv">
              <span class="kv-label">Action Permission</span>
              <span class="kv-value" :class="todayDecisionClass">{{ todayDecision }}</span>
              <span class="kv-note">{{ todayDecisionNote }}</span>
            </div>
            <div class="kv">
              <span class="kv-label">N1 / N3</span>
              <span class="kv-value mono">
                {{ decisionPackage?.evidence?.news_context?.tiers_count?.N1 ?? "-" }} /
                {{ decisionPackage?.evidence?.news_context?.tiers_count?.N3 ?? "-" }}
              </span>
            </div>
            <div class="kv">
              <span class="kv-label">Risk score</span>
              <span class="kv-value mono">
                {{ decisionPackage?.evidence?.news_context?.score_impact?.risk_off_score_added ?? "-" }}
              </span>
            </div>
          </div>
          <div class="hash-row">
            <span class="kv-label">inputs_hash</span>
            <span class="mono">{{ todayInputsHash || "-" }}</span>
            <button class="ghost" type="button" @click="copyHash(todayInputsHash)" :disabled="!todayInputsHash">
              copy
            </button>
          </div>
        </div>

        <div class="today-card next-step">
          <div class="today-card-header">
            <div>
              <p class="section-title">Next Step Guidance</p>
              <p class="today-subtitle">只導引查證流程，請先檢查證據。</p>
            </div>
          </div>
          <div class="next-step-list">
            <button type="button" class="step-button" @click="openPanelAndScroll('triggers', 'panel-triggers')">
              查看觸發
            </button>
            <button type="button" class="step-button" @click="openPanelAndScroll('news', 'panel-news')">
              查看 N1 證據
            </button>
            <button type="button" class="step-button" @click="openPanelAndScroll('decision', 'panel-decision')">
              查看融合決策包
            </button>
          </div>
          <p class="next-step-note">本區不提供任何買賣建議。</p>
        </div>
      </div>
    </section>

    <section class="psych-separation" aria-label="Decision 與 B2 語意隔離">
      <div class="psych-separation-line"></div>
      <p class="psych-separation-caption">閱讀分界｜上方為系統決策輸出；下方為事後檢查紀錄。</p>
      <p class="psych-separation-caption muted">兩區塊語意分離，請勿互相視為理由或結論。</p>
    </section>

    <section class="panel" id="panel-news">
      <div class="panel-header">
        <h2>決策引用敘述（Signals · 暫）</h2>
        <span class="badge">news-service</span>
        <button class="collapse-btn" type="button" @click="togglePanel('news')">
          {{ panels.news ? "展開" : "收合" }}
        </button>
      </div>

      <div v-show="!panels.news">
      <div v-if="newsError" class="error">
        {{ newsError }}
      </div>

      <div v-else>
        <div class="signals-intro">
          <p class="signals-note">
            目前顯示為被決策引用的新聞敘述；主張將於後續階段依穩定條件抽象化。
          </p>
          <p class="signals-tier-summary">
            共 {{ newsItems.length }} 則引用敘述｜N1 {{ n1Items.length }} ・ N3 {{ n3Items.length }}
          </p>
        </div>

        <div v-if="newsLoading" class="empty">讀取中...</div>
        <div v-else-if="newsItems.length === 0" class="empty">目前沒有被決策引用的敘述</div>
        <div v-else class="signals-list">
          <article v-for="item in newsItems" :key="item.id" class="signal-claim" :class="{ n1: item.tier === 'N1' }">
            <p class="signal-line">
              <span class="signal-label">引用敘述（暫）</span>
              <span class="signal-value signal-claim-title">
                <span class="signal-source-summary">來源摘要：{{ item.title || "-" }}</span>
                <a
                  v-if="item.source_url"
                  class="signal-source-link mono"
                  :href="item.source_url"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {{ formatSignalSourceLabel(item) }}
                </a>
              </span>
            </p>
            <p class="signal-line">
              <span class="signal-label">何時會錯</span>
              <span class="signal-value">
                <span class="signal-falsify-hint">⚠ 以下任一條件成立，代表此敘述被證偽</span>
                <span>{{ formatSignalTriggerLine(item.falsifiable_triggers) }}</span>
              </span>
            </p>
            <p class="signal-line">
              <span class="signal-label">Tier（輔助）</span>
              <span class="signal-value"><span class="pill">{{ item.tier || "-" }}</span></span>
            </p>
            <p class="signal-line">
              <span class="signal-label">時間</span>
              <span class="signal-value mono">{{ item.published_at || "-" }}</span>
            </p>
          </article>
        </div>
      </div>
      </div>
    </section>

    <section class="panel subtle panel-observation" id="panel-triggers">
      <div class="panel-header">
        <h2>今日證偽檢查（Triggers · Today）</h2>
        <span class="badge">radar-service</span>
        <button class="collapse-btn" type="button" @click="togglePanel('triggers')">
          {{ panels.triggers ? "展開" : "收合" }}
        </button>
      </div>

      <div v-show="!panels.triggers">
        <p class="today-trigger-note">本區僅顯示是否出現反證條件，不提供任何行動依據。</p>
        <p class="today-trigger-disclaimer">此區塊為事實紀錄，請與上方決策狀態分開閱讀。</p>

        <div v-if="triggerError" class="error">
          {{ triggerError }}
        </div>

        <div v-else-if="triggerLoading" class="empty">讀取中...</div>

        <div v-else-if="todayTriggeredItems.length === 0" class="empty">今日尚無任何引用敘述被證偽。</div>

        <div v-else class="today-trigger-list">
          <article
            v-for="(row, idx) in todayTriggeredItems"
            :key="`${row.decision_inputs_hash || 'hash'}-${row.trigger_key || 'trigger'}-${idx}`"
            class="today-trigger-card"
          >
            <p class="today-trigger-line">
              <span class="today-trigger-label">引用敘述（暫）</span>
              <span class="today-trigger-value">{{ formatTriggeredStatement(row) }}</span>
            </p>
            <p class="today-trigger-line">
              <span class="today-trigger-label">觸發條件（trigger_key）</span>
              <span class="today-trigger-value mono">{{ row.trigger_key || "-" }}</span>
            </p>
            <p class="today-trigger-line">
              <span class="today-trigger-label">觀測值（observed_value）</span>
              <span class="today-trigger-value mono">{{ formatObservedValue(row.observed_value) }}</span>
            </p>
          </article>
        </div>
      </div>
    </section>

    <section class="panel subtle panel-observation" id="panel-trigger-timeline">
      <div class="panel-header">
        <h2>歷史一致性檢查（Trigger Timeline）</h2>
        <span class="badge">radar-service</span>
        <button class="collapse-btn" type="button" @click="togglePanel('triggersTimeline')">
          {{ panels.triggersTimeline ? "展開" : "收合" }}
        </button>
      </div>

      <div v-show="!panels.triggersTimeline">
        <p class="timeline-note">本區僅描述 trigger 在過去 {{ TRIGGER_TIMELINE_DAYS }} 天是否出現，不提供推論。</p>
        <div class="timeline-legend">
          <span><i class="timeline-dot appeared"></i>出現</span>
          <span><i class="timeline-dot missed"></i>未出現</span>
        </div>

        <div v-if="triggerTimelineError" class="error">
          {{ triggerTimelineError }}
        </div>
        <div v-else-if="triggerTimelineLoading" class="empty">讀取中...</div>
        <div v-else-if="triggerTimelineRows.length === 0" class="empty">歷史資料不足，無法判斷一致性。</div>

        <div v-else class="timeline-groups">
          <div class="timeline-group">
            <p class="timeline-group-title">今日曾出現</p>
            <div v-if="todayTimelineRows.length === 0" class="empty">今日尚無 trigger 出現紀錄。</div>
            <article v-for="row in todayTimelineRows" :key="`today-${row.trigger_key}`" class="timeline-card">
              <p class="timeline-line">
                <span class="timeline-label">trigger_key</span>
                <span class="timeline-value mono">{{ row.trigger_key }}</span>
              </p>
              <p class="timeline-line">
                <span class="timeline-label">過去 {{ TRIGGER_TIMELINE_DAYS }} 天出現次數</span>
                <span class="timeline-value">{{ row.count }}</span>
              </p>
              <p class="timeline-line">
                <span class="timeline-label">連續出現</span>
                <span class="timeline-value">{{ row.insufficient_history ? "-" : row.has_consecutive }}</span>
              </p>
              <p class="timeline-line">
                <span class="timeline-label">多為單日出現</span>
                <span class="timeline-value">{{ row.insufficient_history ? "-" : row.single_day_spikes }}</span>
              </p>
              <p v-if="row.insufficient_history" class="timeline-insufficient">歷史資料不足，無法判斷一致性。</p>
              <div class="timeline-track">
                <span
                  v-for="(hit, idx) in row.day_hits"
                  :key="`${row.trigger_key}-${idx}`"
                  class="timeline-dot"
                  :class="{ appeared: hit, missed: !hit }"
                ></span>
              </div>
            </article>
          </div>

          <div class="timeline-group">
            <button class="ghost" type="button" @click="showOtherTimelineTriggers = !showOtherTimelineTriggers">
              {{ showOtherTimelineTriggers ? "收合其他 trigger" : "展開其他 trigger" }}
            </button>
            <div v-if="showOtherTimelineTriggers" class="timeline-other-list">
              <div v-if="otherTimelineRows.length === 0" class="empty">沒有其他歷史 trigger。</div>
              <article v-for="row in otherTimelineRows" :key="`other-${row.trigger_key}`" class="timeline-card">
                <p class="timeline-line">
                  <span class="timeline-label">trigger_key</span>
                  <span class="timeline-value mono">{{ row.trigger_key }}</span>
                </p>
                <p class="timeline-line">
                  <span class="timeline-label">過去 {{ TRIGGER_TIMELINE_DAYS }} 天出現次數</span>
                  <span class="timeline-value">{{ row.count }}</span>
                </p>
                <p class="timeline-line">
                  <span class="timeline-label">連續出現</span>
                  <span class="timeline-value">{{ row.insufficient_history ? "-" : row.has_consecutive }}</span>
                </p>
                <p class="timeline-line">
                  <span class="timeline-label">多為單日出現</span>
                  <span class="timeline-value">{{ row.insufficient_history ? "-" : row.single_day_spikes }}</span>
                </p>
                <p v-if="row.insufficient_history" class="timeline-insufficient">歷史資料不足，無法判斷一致性。</p>
                <div class="timeline-track">
                  <span
                    v-for="(hit, idx) in row.day_hits"
                    :key="`${row.trigger_key}-${idx}`"
                    class="timeline-dot"
                    :class="{ appeared: hit, missed: !hit }"
                  ></span>
                </div>
              </article>
            </div>
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

    <section class="panel" id="panel-decision">
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
              <h3>Coverage</h3>
              <span class="meta">近 30 天</span>
            </div>
            <div v-if="!coverage" class="empty">尚無 coverage</div>
            <div v-else class="coverage-metrics">
              <div class="metric">
                <span class="label">coverage_rate</span>
                <span class="value" data-testid="coverage-rate">
                  {{ formatRate(coverage.coverage_rate) }}
                </span>
              </div>
              <div class="metric">
                <span class="label">unknown_rate</span>
                <span class="value" data-testid="unknown-rate">
                  {{ formatRate(coverage.unknown_rate) }}
                </span>
              </div>
              <div class="metric">
                <span class="label">p95 delay</span>
                <span class="value">{{ formatSeconds(coverage.label_delay_p95_seconds) }}</span>
              </div>
            </div>
          </div>

          <div class="analytics-card">
            <div class="analytics-title">
              <h3>Trigger Attribution</h3>
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
                <span>unknown</span>
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
                <span>{{ row.unknown }}</span>
                <span>{{ formatRate(row.win_rate) }}</span>
              </div>
            </div>
          </div>

          <div class="analytics-card">
            <div class="analytics-title">
              <h3>Tier Attribution</h3>
              <span class="meta">近 30 天</span>
            </div>
            <div v-if="sortedTierAnalytics.length === 0" class="empty">尚無 outcomes</div>
            <div v-else class="analytics-table">
              <div class="analytics-row analytics-header">
                <span>tier</span>
                <span>total</span>
                <span>wins</span>
                <span>losses</span>
                <span>neutral</span>
                <span>unknown</span>
                <span>win_rate</span>
              </div>
              <div
                v-for="(row, idx) in sortedTierAnalytics"
                :key="`${row.tier}-${idx}`"
                class="analytics-row"
              >
                <span class="pill">{{ row.tier }}</span>
                <span>{{ row.total }}</span>
                <span>{{ row.wins }}</span>
                <span>{{ row.losses }}</span>
                <span>{{ row.neutral }}</span>
                <span>{{ row.unknown }}</span>
                <span>{{ formatRate(row.win_rate) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="panel subtle">
      <div class="panel-header">
        <h2>Error Logs</h2>
        <button class="ghost" type="button" @click="clearErrorLogs" :disabled="errorLogs.length === 0">
          Clear
        </button>
        <button class="collapse-btn" type="button" @click="togglePanel('errorLog')">
          {{ panels.errorLog ? "展開" : "收合" }}
        </button>
      </div>

      <div v-show="!panels.errorLog">
        <div v-if="errorLogs.length === 0" class="empty">No errors</div>
        <div v-else class="error-log">
          <div v-for="item in errorLogs" :key="item.id" class="error-row">
            <span class="mono">{{ item.time }}</span>
            <span class="pill">{{ item.source }}</span>
            <span class="message">{{ item.message }}</span>
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

.today-zone {
  display: grid;
  gap: 1.25rem;
}

.decision-status-banner {
  position: sticky;
  top: 0;
  z-index: 8;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 1.25rem;
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.35);
  background: rgba(12, 18, 32, 0.82);
  box-shadow: 0 8px 18px rgba(5, 7, 15, 0.35);
  backdrop-filter: blur(12px);
}

.decision-status-banner.risk-on {
  border-color: rgba(148, 163, 184, 0.32);
}

.decision-status-banner.risk-off {
  border-color: rgba(148, 163, 184, 0.32);
}

.decision-status-banner.transition {
  border-color: rgba(148, 163, 184, 0.32);
}

.decision-status-banner.unknown {
  border-color: rgba(148, 163, 184, 0.35);
}

.banner-title {
  margin: 0 0 0.35rem;
  font-size: 0.82rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #cbd5e1;
  font-weight: 500;
}

.banner-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.3rem 0.68rem;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.35);
  background: rgba(148, 163, 184, 0.12);
  color: #dbe3ee;
  font-size: 0.72rem;
  font-weight: 500;
  letter-spacing: 0.04em;
}

.status-pill.risk-on {
  border-color: rgba(148, 163, 184, 0.4);
}

.status-pill.risk-off {
  border-color: rgba(148, 163, 184, 0.4);
}

.status-pill.transition {
  border-color: rgba(148, 163, 184, 0.4);
}

.status-pill.unknown {
  border-color: rgba(148, 163, 184, 0.4);
}

.status-pill.decision-neutral {
  border-color: rgba(148, 163, 184, 0.4);
}

.status-pill.decision-alert {
  border-color: rgba(148, 163, 184, 0.4);
}

.status-pill.decision-unknown {
  border-color: rgba(148, 163, 184, 0.4);
}

.banner-note {
  margin: 0.6rem 0 0;
  color: #9aa8ba;
  font-size: 0.78rem;
}

.banner-right {
  display: grid;
  justify-items: end;
  gap: 0.35rem;
}

.banner-meta {
  display: flex;
  gap: 0.6rem;
  flex-wrap: wrap;
  font-size: 0.75rem;
  color: #94a3b8;
}

.banner-state {
  font-size: 0.78rem;
  color: #cbd5e1;
  font-weight: 500;
}

.banner-state.error {
  color: #fca5a5;
}

.banner-error {
  font-size: 0.75rem;
  color: #fca5a5;
}

.today-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1.25rem;
}

.today-card {
  background: rgba(10, 15, 30, 0.88);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 18px;
  padding: 1.25rem;
  display: grid;
  gap: 1rem;
  box-shadow: 0 12px 26px rgba(5, 7, 15, 0.4);
}

.today-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}

.today-subtitle {
  margin: 0.25rem 0 0;
  font-size: 0.8rem;
  color: #94a3b8;
}

.today-kv {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 0.75rem;
}

.kv {
  display: grid;
  gap: 0.35rem;
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 12px;
  padding: 0.65rem 0.75rem;
}

.kv-label {
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 0.65rem;
  color: #94a3b8;
}

.kv-value {
  font-size: 0.9rem;
  font-weight: 500;
  color: #e2e8f0;
}

.kv-value.risk-on {
  color: #e2e8f0;
}

.kv-value.risk-off {
  color: #e2e8f0;
}

.kv-value.transition {
  color: #e2e8f0;
}

.kv-value.decision-neutral {
  color: #e2e8f0;
}

.kv-value.decision-alert {
  color: #e2e8f0;
}

.kv-value.decision-unknown {
  color: #e2e8f0;
}

.kv-note {
  font-size: 0.7rem;
  color: #9aa8ba;
}

.hash-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.6rem;
  padding: 0.6rem 0.75rem;
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.2);
}

.next-step-list {
  display: grid;
  gap: 0.6rem;
}

.step-button {
  border-radius: 12px;
  padding: 0.7rem 0.9rem;
  border: 1px solid rgba(148, 163, 184, 0.35);
  background: rgba(15, 23, 42, 0.8);
  color: #e2e8f0;
  font-size: 0.9rem;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.2s ease, transform 0.2s ease;
}

.step-button:hover {
  border-color: rgba(125, 211, 252, 0.7);
  transform: translateY(-1px);
}

.next-step-note {
  margin: 0;
  font-size: 0.78rem;
  color: #94a3b8;
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

.panel-observation {
  background: rgba(10, 15, 30, 0.72);
  border-color: rgba(148, 163, 184, 0.18);
  box-shadow: 0 10px 24px rgba(5, 7, 15, 0.35);
}

.psych-separation {
  display: grid;
  gap: 0.22rem;
  margin-top: -0.4rem;
}

.psych-separation-line {
  height: 1px;
  background: linear-gradient(90deg, rgba(148, 163, 184, 0), rgba(148, 163, 184, 0.45), rgba(148, 163, 184, 0));
}

.psych-separation-caption {
  margin: 0;
  font-size: 0.74rem;
  color: #94a3b8;
  text-align: center;
}

.psych-separation-caption.muted {
  color: #64748b;
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
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
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

.analytics-title h3 {
  margin: 0;
  font-size: 0.95rem;
  color: #e2e8f0;
}

.coverage-metrics {
  display: grid;
  gap: 0.5rem;
}

.coverage-metrics .metric {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0.6rem;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.7);
  border: 1px solid rgba(148, 163, 184, 0.2);
  font-size: 0.8rem;
}

.coverage-metrics .label {
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-size: 0.65rem;
  color: #94a3b8;
}

.coverage-metrics .value {
  font-weight: 600;
  color: #e2e8f0;
}

.analytics-table {
  display: grid;
  gap: 0.4rem;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.analytics-row {
  display: grid;
  grid-template-columns: minmax(220px, 2fr) 70px 70px 70px 70px 70px 90px;
  gap: 0.6rem;
  align-items: center;
  padding: 0.5rem 0.65rem;
  background: rgba(15, 23, 42, 0.7);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 12px;
  font-size: 0.78rem;
  min-width: 680px;
}

.analytics-row .key {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  word-break: normal;
  overflow-wrap: normal;
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

.suspicious-row .key {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  word-break: normal;
  overflow-wrap: normal;
  flex: 1 1 auto;
  min-width: 0;
}

.error-log {
  display: grid;
  gap: 0.5rem;
}

.error-row {
  display: grid;
  grid-template-columns: 140px 160px minmax(0, 1fr);
  gap: 0.6rem;
  align-items: center;
  padding: 0.55rem 0.7rem;
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.7);
  border: 1px solid rgba(148, 163, 184, 0.2);
  font-size: 0.78rem;
}

.error-row .message {
  color: #fca5a5;
  word-break: break-word;
}

@media (max-width: 960px) {
  .decision-row {
    grid-template-columns: 1fr;
  }
  .analytics-row {
    grid-template-columns: 1fr;
    min-width: 0;
  }
}

@media (max-width: 1400px) {
  .analytics-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 1100px) {
  .analytics-grid {
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

.today-trigger-note {
  margin: 0;
  color: #94a3b8;
  font-size: 0.78rem;
}

.today-trigger-disclaimer {
  margin: 0 0 0.9rem;
  color: #64748b;
  font-size: 0.74rem;
}

.today-trigger-list {
  display: grid;
  gap: 0.75rem;
}

.today-trigger-card {
  background: rgba(15, 23, 42, 0.8);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 12px;
  padding: 0.75rem 0.85rem;
  display: grid;
  gap: 0.4rem;
}

.today-trigger-line {
  margin: 0;
  display: grid;
  grid-template-columns: 12.6rem 1fr;
  gap: 0.55rem;
  align-items: start;
}

.today-trigger-label {
  color: #93c5fd;
  font-size: 0.75rem;
  white-space: nowrap;
}

.today-trigger-value {
  color: #e2e8f0;
  font-size: 0.84rem;
  line-height: 1.45;
  word-break: break-word;
}

.timeline-note {
  margin: 0;
  color: #94a3b8;
  font-size: 0.78rem;
}

.timeline-legend {
  display: flex;
  gap: 0.8rem;
  margin: 0.4rem 0 0.9rem;
  color: #94a3b8;
  font-size: 0.74rem;
}

.timeline-legend span {
  display: inline-flex;
  gap: 0.3rem;
  align-items: center;
}

.timeline-legend .timeline-dot {
  width: 0.72rem;
  aspect-ratio: 1 / 1;
}

.timeline-groups {
  display: grid;
  gap: 1rem;
}

.timeline-group {
  display: grid;
  gap: 0.6rem;
}

.timeline-group-title {
  margin: 0;
  color: #cbd5e1;
  font-size: 0.8rem;
}

.timeline-other-list {
  display: grid;
  gap: 0.6rem;
}

.timeline-card {
  background: rgba(15, 23, 42, 0.72);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 12px;
  padding: 0.7rem 0.8rem;
  display: grid;
  gap: 0.35rem;
}

.timeline-line {
  margin: 0;
  display: grid;
  grid-template-columns: 10.8rem 1fr;
  gap: 0.55rem;
  align-items: start;
}

.timeline-label {
  color: #93c5fd;
  font-size: 0.74rem;
  white-space: nowrap;
}

.timeline-value {
  color: #e2e8f0;
  font-size: 0.82rem;
  line-height: 1.4;
}

.timeline-insufficient {
  margin: 0.1rem 0 0;
  font-size: 0.76rem;
  color: #94a3b8;
}

.timeline-track {
  display: grid;
  grid-template-columns: repeat(14, minmax(0, 1fr));
  gap: 0.2rem;
  margin-top: 0.2rem;
}

.timeline-dot {
  width: 100%;
  aspect-ratio: 1 / 1;
  border-radius: 3px;
  border: 1px solid rgba(148, 163, 184, 0.3);
}

.timeline-dot.appeared {
  background: rgba(148, 163, 184, 0.55);
}

.timeline-dot.missed {
  background: rgba(15, 23, 42, 0.15);
}

.mono {
  font-family: "JetBrains Mono", "Fira Code", monospace;
  word-break: break-all;
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

@media (max-width: 960px) {
  .today-trigger-line {
    grid-template-columns: 1fr;
    gap: 0.35rem;
  }

  .timeline-line {
    grid-template-columns: 1fr;
    gap: 0.2rem;
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

.signals-intro {
  display: grid;
  gap: 0.45rem;
  margin-bottom: 0.9rem;
  padding: 0.8rem 0.9rem;
  border-radius: 12px;
  background: rgba(8, 47, 73, 0.18);
  border: 1px solid rgba(125, 211, 252, 0.3);
}

.signals-note {
  margin: 0;
  color: #dbeafe;
  font-size: 0.86rem;
  line-height: 1.5;
}

.signals-tier-summary {
  margin: 0;
  color: #93c5fd;
  font-size: 0.78rem;
}

.signals-list {
  display: grid;
  gap: 0.8rem;
}

.signal-claim {
  background: rgba(15, 23, 42, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 12px;
  padding: 0.85rem 0.9rem;
  display: grid;
  gap: 0.45rem;
}

.signal-claim.n1 {
  border-color: rgba(56, 189, 248, 0.45);
}

.signal-line {
  margin: 0;
  display: grid;
  grid-template-columns: 6.8rem 1fr;
  gap: 0.55rem;
  align-items: start;
  font-size: 0.86rem;
}

.signal-label {
  color: #93c5fd;
  font-size: 0.75rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  white-space: nowrap;
}

.signal-value {
  color: #e2e8f0;
  line-height: 1.45;
  word-break: break-word;
}

.signal-claim-title {
  display: grid;
  gap: 0.25rem;
}

.signal-source-summary {
  font-size: 0.8rem;
  color: #94a3b8;
}

.signal-source-link {
  color: #93c5fd;
  font-size: 0.72rem;
  text-decoration: none;
  text-underline-offset: 2px;
  width: fit-content;
}

.signal-source-link:hover {
  color: #dbeafe;
  text-decoration: underline;
}

.signal-falsify-hint {
  display: block;
  margin-bottom: 0.2rem;
  font-size: 0.76rem;
  color: #fca5a5;
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
  .signal-line {
    grid-template-columns: 1fr;
    gap: 0.2rem;
  }

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
