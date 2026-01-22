import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";

// Vitest 與 Vite 共用設定,確保單元測試與開發體驗一致。
export default defineConfig({
  plugins: [vue()],
  test: {
    globals: true,
    environment: "jsdom",
    include: ["tests/**/*.test.js"],
    root: process.cwd(),
  },
});
