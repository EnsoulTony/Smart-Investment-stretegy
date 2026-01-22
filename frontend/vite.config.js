import path from "node:path";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// 主要針對 Docker 與本地流程設定簡單的 Vite 組態。
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": path.resolve(process.cwd(), "src"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 4173,
  },
  preview: {
    host: "0.0.0.0",
    port: 4173,
  },
});
