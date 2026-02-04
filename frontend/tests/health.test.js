import { test, expect } from '@playwright/test';
import { formatHealthStatus } from "../src/lib/health.js";

test('should return default healthy message', async () => {
  expect(formatHealthStatus("api-gateway")).toBe("api-gateway 狀態：綠燈");
});

test('should show warning message when service is unhealthy', async () => {
  expect(formatHealthStatus("portfolio-service", false)).toBe(
    "portfolio-service 狀態：需注意"
  );
});

test('should throw error if serviceName is missing', async () => {
  expect(() => formatHealthStatus()).toThrowError();
});