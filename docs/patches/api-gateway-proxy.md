# API Gateway 反向代理實作完成

## 完成項目

### 1. ✅ 新增 httpx 依賴
- 檔案：`services/api-gateway/requirements.txt`
- 新增：`httpx>=0.27.0` 用於非同步 HTTP 請求

### 2. ✅ 實作反向代理路由
- 檔案：`services/api-gateway/app/main.py`
- 新增路由：
  - `POST /portfolio/sync` → 轉發至 `http://portfolio-service:8001/portfolio/sync`
  - `GET /portfolio/health` → 轉發至 `http://portfolio-service:8001/health`
- 特性：
  - 使用 httpx AsyncClient
  - 保留原始請求的 body、headers、狀態碼
  - 錯誤處理：503 (連線失敗)、500 (其他錯誤)
  - 註解使用繁體中文

### 3. ✅ 建立 pytest 測試
- 檔案：`services/api-gateway/tests/test_portfolio_proxy.py`
- 測試案例：
  - `test_proxy_portfolio_sync_success` - 成功轉發同步請求
  - `test_proxy_portfolio_sync_backend_error` - 後端回傳 500
  - `test_proxy_portfolio_sync_connection_error` - 連線失敗（503）
  - `test_proxy_portfolio_health_success` - 成功轉發健康檢查
  - `test_proxy_portfolio_health_connection_error` - 健康檢查連線失敗
  - `test_portfolio_sync_preserves_request_body` - 驗證保留請求 body
- 使用 mock httpx 驗證：URL、method、body、回應

### 4. ✅ 更新文檔
- `API_CONTRACTS.md`：新增 api-gateway 的轉發路由說明
- `ARCHITECTURE.md`：更新 api-gateway 服務邊界描述，標註 BFF 角色

## 驗收指令

### 執行測試
```bash
# 在容器內執行
docker compose exec api-gateway pytest -q

# 或使用本地 Python
cd services/api-gateway
pytest tests/test_portfolio_proxy.py -v
```

### 測試實際轉發（需先啟動服務）
```bash
# 啟動所有服務
docker compose up -d

# 測試轉發（應不再回 404）
curl -s -X POST http://localhost:8000/portfolio/sync

# 測試健康檢查轉發
curl -s http://localhost:8000/portfolio/health
```

## 技術細節

### 請求流程
```
Client → api-gateway:8000/portfolio/sync
         ↓ (httpx.AsyncClient)
         portfolio-service:8001/portfolio/sync
         ↓
         Response (保留狀態碼、body、headers)
         ↓
Client ← api-gateway
```

### 錯誤處理
- `httpx.RequestError` → 503 Service Unavailable
- 其他 Exception → 500 Internal Server Error
- 後端服務的錯誤狀態碼會被完整保留並返回

### 環境變數
- `PORTFOLIO_SERVICE_URL`：預設 `http://portfolio-service:8001`
- 可透過環境變數覆蓋以指向不同的後端服務
