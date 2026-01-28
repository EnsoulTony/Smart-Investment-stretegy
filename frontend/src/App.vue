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
const lastUpdated = ref("");

const n1Items = computed(() => newsItems.value.filter((item) => item.tier === "N1"));
const n3Items = computed(() => newsItems.value.filter((item) => item.tier === "N3"));

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

onMounted(fetchNewsSignals);
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
        <button class="refresh" type="button" @click="fetchNewsSignals" :disabled="newsLoading">
          {{ newsLoading ? "讀取中..." : "重新整理" }}
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
