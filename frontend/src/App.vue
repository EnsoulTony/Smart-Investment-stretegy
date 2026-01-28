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
const holdings = ref([]);
const holdingsError = ref("");
const holdingsLoading = ref(false);
const holdingsSaving = ref(false);
const holdingsSyncing = ref(false);
const holdingsRebuilding = ref(false);
const holdingsSavedAt = ref("");
const holdingsHint = ref("");
const lastUpdated = ref("");

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

const selectedCoreSymbols = computed(() =>
  holdings.value.filter((item) => item.selected).map((item) => item.symbol),
);
const holdingsEmpty = computed(() => holdings.value.length === 0);

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
    const positionSymbols = (positionsData.items || []).map((item) => item.symbol);
    const positionNameMap = new Map(
      (positionsData.items || []).map((item) => [item.symbol, item.name_zh]),
    );
    const coreSymbols = coreData.symbols || [];
    const allSymbols = Array.from(new Set([...positionSymbols, ...coreSymbols])).sort();
    const coreSet = new Set(coreSymbols);
    holdings.value = allSymbols.map((symbol) => ({
      symbol,
      name: positionNameMap.get(symbol) || "未提供中文說明",
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
      body: JSON.stringify({ symbols: selectedCoreSymbols.value }),
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

const fetchAll = async () => {
  await Promise.all([fetchNewsSignals(), fetchDecisionPackage(), fetchHoldings()]);
};

onMounted(fetchAll);
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
        <p class="timestamp" v-if="lastUpdated">更新時間：{{ lastUpdated }}</p>
      </div>
    </header>

    <section class="panel">
      <div class="panel-header">
        <h2>戰情室｜新聞訊號</h2>
        <span class="badge">news-service</span>
      </div>

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
            <h4>{{ item.title }}</h4>
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
            <h4>{{ item.title }}</h4>
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
    </section>

    <section class="panel">
      <div class="panel-header">
        <h2>編輯核心持股</h2>
        <span class="badge">portfolio-service</span>
      </div>

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
        <button
          class="refresh"
          type="button"
          @click="rebuildPositions"
          :disabled="holdingsRebuilding"
        >
          {{ holdingsRebuilding ? "重建中..." : "重建持股" }}
        </button>
        <button
          class="refresh"
          type="button"
          @click="saveCoreHoldings"
          :disabled="holdingsSaving || holdingsLoading || holdingsEmpty"
        >
          {{ holdingsSaving ? "儲存中..." : "儲存核心持股" }}
        </button>
        <p class="timestamp" v-if="holdingsSavedAt">已儲存：{{ holdingsSavedAt }}</p>
      </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-header">
        <h2>戰情室｜融合決策包</h2>
        <span class="badge">radar-service</span>
      </div>

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
    </section>

    <section class="panel subtle">
      <h2>健康檢查總覽</h2>
      <ul>
        <li v-for="item in healthMessages" :key="item.name">
          <strong>{{ item.name }}</strong>
          <span>{{ item.message }}</span>
        </li>
      </ul>
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
