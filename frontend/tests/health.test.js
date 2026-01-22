import { describe, expect, it } from "vitest";
import { formatHealthStatus } from "../lib/health.js";

// 驗證健康訊息格式化工具可提供穩定的輸出。
describe("formatHealthStatus", () => {
  it("回傳預設綠燈訊息", () => {
    expect(formatHealthStatus("api-gateway")).toBe("api-gateway 狀態：綠燈");
  });

  it("當服務異常時顯示警示文字", () => {
    expect(formatHealthStatus("portfolio-service", false)).toBe(
      "portfolio-service 狀態：需注意",
    );
  });

  it("若缺少名稱應拋出錯誤", () => {
    expect(() => formatHealthStatus()).toThrowError();
  });
});
