// 封裝簡單的健康檢查訊息格式，供 UI 與測試共用。
export function formatHealthStatus(serviceName, isHealthy = true) {
  if (!serviceName) {
    throw new Error("serviceName 為必填");
  }
  return isHealthy
    ? `${serviceName} 狀態：綠燈`
    : `${serviceName} 狀態：需注意`;
}
