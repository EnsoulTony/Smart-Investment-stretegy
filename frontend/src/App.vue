<script setup>
import { computed } from "vue";
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
</script>

<template>
  <main class="container">
    <header>
      <h1>Smart Investment Strategy</h1>
      <p>微服務骨架已就緒，請使用 Claude / Aider 持續擴充。</p>
    </header>

    <section>
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
:global(body) {
  margin: 0;
  font-family: "Noto Sans TC", "Microsoft JhengHei", system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
  background: #0f172a;
  color: #e2e8f0;
}

.container {
  min-height: 100vh;
  padding: 3rem 1.5rem;
  max-width: 960px;
  margin: 0 auto;
}

header {
  margin-bottom: 2rem;
}

h1 {
  margin: 0 0 0.5rem;
  font-size: 2.5rem;
}

section {
  background: rgba(15, 23, 42, 0.8);
  border: 1px solid rgba(148, 163, 184, 0.3);
  border-radius: 12px;
  padding: 1.5rem;
  box-shadow: 0 10px 40px rgba(15, 23, 42, 0.5);
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

@media (max-width: 600px) {
  li {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.25rem;
  }
}
</style>
