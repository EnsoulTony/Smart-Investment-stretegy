# RUNBOOK 驗收命令區塊

本文件集中所有 RUNBOOK.md 提到的驗收命令，方便複製執行。

---

## 🔍 第一部分：日常健康檢查

### 1. 容器狀態檢查

```bash
# 檢查所有容器狀態
docker ps --format 'table {{.Names}}\t{{.Status}}'

# 預期：所有容器狀態為 "Up" 或 "healthy"
```

### 2. 服務健康檢查（逐一驗證）

```bash
# API Gateway
curl -s http://localhost:8000/health | jq

# Portfolio Service
curl -s http://localhost:8001/health | jq

# Radar Service
curl -s http://localhost:8002/health | jq

# News Service
curl -s http://localhost:8003/health | jq

# Research Service
curl -s http://localhost:8004/health | jq
```

### 3. 批次健康檢查（一鍵執行）

```bash
# 檢查所有服務
for port in 8000 8001 8002 8003 8004; do
  echo "=== Port $port ==="
  curl -s http://localhost:$port/health | jq '.service, .status' 2>/dev/null || echo "❌ 無回應"
  echo ""
done
```

### 4. Database 健康檢查

```bash
# PostgreSQL 連線檢查
docker compose exec postgres pg_isready

# 預期輸出：
# /var/run/postgresql:5432 - accepting connections

# 查詢 DB 版本
docker compose exec postgres psql -U investment -d investment_db -c "SELECT version();"
```

---

## 🔧 第二部分：環境變數驗證

### 1. Google Sheets 環境變數檢查

```bash
# 檢查是否設定（主機上）
test -n "$GOOGLE_SA_JSON" && echo "✅ GOOGLE_SA_JSON is set" || echo "❌ Missing GOOGLE_SA_JSON"
test -n "$GOOGLE_SHEET_ID" && echo "✅ GOOGLE_SHEET_ID is set" || echo "❌ Missing GOOGLE_SHEET_ID"

# 驗證 JSON 格式（主機上）
echo "$GOOGLE_SA_JSON" | python3 -m json.tool > /dev/null && echo "✅ Valid JSON" || echo "❌ Invalid JSON"
```

### 2. 容器內環境變數驗證

```bash
# 檢查容器內是否載入環境變數
docker compose exec portfolio-service env | grep GOOGLE

# 應該看到:
# GOOGLE_SA_JSON={"type":"service_account"...
# GOOGLE_SHEET_ID=1-PTHx8TBQ_PPJ...

# 測試 JSON 解析
docker compose exec portfolio-service python3 -c "
import os, json
sa_json = os.getenv('GOOGLE_SA_JSON')
if sa_json:
    try:
        data = json.loads(sa_json)
        print(f'✅ JSON 解析成功，project_id: {data.get(\"project_id\")}')
    except Exception as e:
        print(f'❌ JSON 解析失敗: {e}')
else:
    print('❌ 環境變數未設定')
"
```

### 3. .env 檔案格式診斷

```bash
# 檢查 GOOGLE_SA_JSON 是否為單行
cat .env | grep GOOGLE_SA_JSON | wc -l
# 應該回傳 1

# 檢查是否有隱藏字元（CRLF）
cat -A .env | grep GOOGLE_SA_JSON | head -1
# 不應該看到 ^M 或其他特殊字元

# 檢查 JSON 長度
cat .env | grep GOOGLE_SA_JSON | wc -c
# 通常應該 > 1500 字元（包含完整 private_key）
```

---

## 🌐 第三部分：API Gateway 路由驗證

### 1. 驗證 Gateway 端點清單

```bash
# 取得 API Gateway OpenAPI 規格
curl -s http://localhost:8000/openapi.json | jq '.paths | keys'

# 預期輸出（目前只有 /health）:
# [
#   "/health"
# ]
```

### 2. 驗證 Portfolio Service 端點

```bash
# 取得 Portfolio Service 所有端點
curl -s http://localhost:8001/openapi.json | jq '.paths | keys'

# 預期輸出:
# [
#   "/health",
#   "/portfolio/sync",
#   "/portfolio/rebuild_positions/{user_id}",
#   "/portfolio/positions/{user_id}"
# ]
```

### 3. 驗證直接存取 vs Gateway 代理

```bash
# 直接呼叫 Portfolio Service (8001)
curl -s http://localhost:8001/health | jq '.service'
# 預期: "portfolio-service"

# 透過 Gateway (8000) - 目前僅支援 /health
curl -s http://localhost:8000/health | jq '.service'
# 預期: "api-gateway"
```

---

## 📊 第四部分：Portfolio Sync 驗證

### 1. 執行同步並檢查結果

```bash
# 呼叫 sync 端點
curl -s -X POST http://localhost:8001/portfolio/sync | jq

# 預期輸出範例:
# {
#   "status": "completed",
#   "inserted_count": 0,
#   "skipped_count": 64,
#   "sync_run_id": 123,
#   "duration_seconds": 2.5
# }
```

### 2. DB 同步結果驗證

```bash
# 查詢交易總數
docker compose exec postgres psql -U investment -d investment_db -c "SELECT count(*) FROM trades;"

# 查詢最近的交易
docker compose exec postgres psql -U investment -d investment_db -c "
SELECT id, user_id, symbol, side, quantity, price, trade_date, source_hash 
FROM trades 
ORDER BY trade_date DESC 
LIMIT 5;
"

# 查詢同步執行紀錄
docker compose exec postgres psql -U investment -d investment_db -c "
SELECT id, status, started_at, completed_at, inserted_count, skipped_count, error_message
FROM sync_runs 
ORDER BY started_at DESC 
LIMIT 5;
"
```

### 3. 驗證 source_hash 去重機制

```bash
# 檢查是否有重複的 source_hash
docker compose exec postgres psql -U investment -d investment_db -c "
SELECT source_hash, COUNT(*) as count
FROM trades
GROUP BY source_hash
HAVING COUNT(*) > 1;
"

# 應該回傳空結果（代表沒有重複）
```

### 4. 強制重新同步（測試用）

```bash
# ⚠️ 危險操作：刪除所有資料
docker compose exec postgres psql -U investment -d investment_db -c "TRUNCATE trades, sync_runs CASCADE;"

# 重新同步
curl -s -X POST http://localhost:8001/portfolio/sync | jq

# 此時應該看到 inserted_count > 0
```

---

## 🔄 第五部分：容器重建驗證

### 1. 確認何時需要重建

```bash
# 檢查容器建立時間
docker compose ps

# 檢查映像建立時間
docker images | grep smart-investment

# 檢查檔案修改時間（主機上）
ls -la services/portfolio-service/app/main.py

# 若檔案修改時間晚於容器建立時間，需要重建
```

### 2. 標準重建流程

```bash
# 快速重建單一服務
docker compose up -d --build portfolio-service

# 等待容器啟動
sleep 3

# 驗證服務正常
curl http://localhost:8001/health
```

### 3. 驗證容器內檔案是否更新

```bash
# 查看容器內檔案修改時間
docker compose exec portfolio-service ls -la /app/app/

# 查看容器內程式碼內容
docker compose exec portfolio-service cat /app/app/main.py | head -20

# 查看容器內測試檔案
docker compose exec portfolio-service cat /app/tests/test_fx.py | head -20
```

### 4. 修改環境變數後的處理

```bash
# 只需 restart（不需 rebuild）
docker compose restart portfolio-service

# 驗證環境變數是否生效
docker compose exec portfolio-service env | grep GOOGLE_SA_JSON | head -c 50
```

---

## ✅ 第六部分：FX Boundary 驗證（Sprint 1-4.A）

### 1. 執行 FX 模組單元測試

```bash
# 進入專案目錄
cd /root/Smart-Investment-stretegy

# 重建容器（確保最新程式碼）
docker compose up -d --build portfolio-service
sleep 3

# 執行 FX 模組測試
docker compose exec portfolio-service pytest tests/test_fx.py -v

# 預期：14 個測試全部 PASSED
```

### 2. 執行 Guardrail Tests（規範守門）

```bash
# 執行邊界守門測試
docker compose exec portfolio-service pytest tests/test_fx_guardrails.py -v

# 預期輸出（6 個測試全部 PASSED）:
# test_no_direct_fx_env_access_outside_fx_module PASSED
# test_no_direct_provider_import_outside_fx_module PASSED
# test_fx_module_exists_and_has_public_api PASSED
# test_stub_provider_same_currency_returns_original PASSED
# test_stub_provider_cross_currency_raises_not_implemented PASSED
# test_factory_can_switch_providers PASSED
```

### 3. 驗證 Public API

```bash
# 測試 FX 模組 public API 可正常匯入
docker compose exec portfolio-service python3 -c "
from app.fx import get_fx_provider, reset_fx_provider
fx = get_fx_provider()
print(f'✅ Public API 可正常匯入')
print(f'Provider type: {type(fx).__name__}')
print(f'Is stub: {fx.is_stub()}')
"

# 預期輸出:
# ✅ Public API 可正常匯入
# Provider type: StubFxProvider
# Is stub: True
```

### 4. 手動檢查違規（grep 掃描）

```bash
# 檢查是否有直接讀取 FX_* 環境變數（app/fx/ 以外）
grep -r "os.getenv.*FX_" services/portfolio-service/app/ --exclude-dir=fx

# 檢查是否有直接讀取 VALUATION_* 環境變數
grep -r "os.environ.*VALUATION" services/portfolio-service/app/ --exclude-dir=fx

# 檢查是否有直接 import provider 實作
grep -r "from app.fx.stub_provider" services/portfolio-service/app/ --exclude=__init__.py
grep -r "from app.fx.interfaces" services/portfolio-service/app/ --exclude=__init__.py

# 上述命令應該都回傳空結果
```

### 5. 完整自動化驗收（Sprint 1-4.A）

```bash
# 執行完整驗收腳本
cd /root/Smart-Investment-stretegy
chmod +x verify_sprint_1-4-a.sh
./verify_sprint_1-4-a.sh

# 預期：所有步驟 ✅ PASSED
```

---

## 🧪 第七部分：測試隔離驗證

### 1. 執行測試隔離相關測試

```bash
# 執行 rebuild_positions_preview 測試
docker compose exec portfolio-service pytest tests/test_rebuild_positions_preview.py -v

# 檢查測試是否使用 dependency_overrides
docker compose exec portfolio-service grep -A 5 "def client" tests/conftest.py
```

### 2. 驗證 SAVEPOINT 機制

```bash
# 執行任何測試並檢查 DB 狀態
docker compose exec portfolio-service pytest tests/test_fx.py -v

# 查詢測試後 DB 狀態（應該沒有測試資料殘留）
docker compose exec postgres psql -U investment -d investment_db -c "
SELECT count(*) FROM trades WHERE user_id LIKE 'test_%';
"

# 預期：0 rows（測試資料已回滾）
```

---

## 📝 第八部分：完整系統驗收

### 一鍵完整驗收腳本

```bash
#!/bin/bash
# 完整系統驗收腳本

echo "=========================================="
echo "Smart Investment Strategy - 完整驗收"
echo "=========================================="
echo ""

# 1. 容器狀態
echo "📦 檢查容器狀態..."
docker compose ps
echo ""

# 2. 服務健康檢查
echo "🏥 檢查服務健康..."
for port in 8000 8001 8002 8003 8004; do
  echo -n "Port $port: "
  curl -s http://localhost:$port/health | jq -r '.service + " - " + .status' 2>/dev/null || echo "❌ 無回應"
done
echo ""

# 3. Database 健康檢查
echo "🗄️  檢查 Database..."
docker compose exec postgres pg_isready
echo ""

# 4. Portfolio Sync
echo "📊 執行 Portfolio Sync..."
curl -s -X POST http://localhost:8001/portfolio/sync | jq '.status, .inserted_count, .skipped_count'
echo ""

# 5. FX 模組測試
echo "✅ 執行 FX 模組測試..."
docker compose exec portfolio-service pytest tests/test_fx.py -v --tb=short
echo ""

# 6. Guardrail Tests
echo "🚨 執行 Guardrail Tests..."
docker compose exec portfolio-service pytest tests/test_fx_guardrails.py -v --tb=short
echo ""

echo "=========================================="
echo "✅ 完整驗收完成"
echo "=========================================="
```

**使用方式**:
```bash
# 儲存為 full_acceptance_test.sh
chmod +x full_acceptance_test.sh
./full_acceptance_test.sh
```

---

## ⚠️ 第九部分：故障排查命令

### 1. 查看日誌

```bash
# 查看特定服務日誌（最近 50 行）
docker logs smart-investment-strategy-portfolio-service-1 --tail 50

# 即時追蹤日誌
docker logs smart-investment-strategy-portfolio-service-1 -f

# 查看所有容器日誌
docker compose logs --tail 50
```

### 2. 重啟服務

```bash
# 重啟單一服務
docker compose restart portfolio-service

# 重啟所有服務
docker compose restart

# 完全重建
docker compose down
docker compose up -d --build
```

### 3. DB 診斷

```bash
# 進入 psql 互動式介面
docker compose exec postgres psql -U investment -d investment_db

# 查詢所有資料表
\dt

# 查詢資料表結構
\d trades

# 退出
\q
```

### 4. 清理與重置

```bash
# 清理所有容器（保留 volumes）
docker compose down

# 清理所有容器與 volumes（⚠️ 會刪除資料）
docker compose down -v

# 清理未使用的 Docker 資源
docker system prune -a

# 重新建立環境
docker compose up -d --build
```

---

## 📋 第十部分：驗收檢查表

複製此檢查表，逐項驗證：

```
[ ] 所有容器狀態為 "Up" 或 "healthy"
[ ] API Gateway (8000) /health 回傳 healthy
[ ] Portfolio Service (8001) /health 回傳 healthy
[ ] Radar Service (8002) /health 回傳 healthy
[ ] News Service (8003) /health 回傳 healthy
[ ] Research Service (8004) /health 回傳 healthy
[ ] PostgreSQL 連線正常 (pg_isready)
[ ] GOOGLE_SA_JSON 環境變數設定正確
[ ] GOOGLE_SHEET_ID 環境變數設定正確
[ ] Portfolio sync 執行成功（status: completed）
[ ] sync_runs 表有執行紀錄
[ ] trades 表有資料（首次 sync 後）
[ ] source_hash 沒有重複（去重機制正常）
[ ] FX 模組單元測試全部 PASSED (14 tests)
[ ] Guardrail Tests 全部 PASSED (6 tests)
[ ] FX public API 可正常匯入
[ ] 手動 grep 檢查無違規
[ ] 修改程式碼後 rebuild 測試通過
[ ] 修改 .env 後 restart 環境變數生效
[ ] 測試隔離正常（無資料殘留）
[ ] API 端點清單正確
```

**完成度**: ___/20

---

## 🎯 預期結果總結

- **所有服務健康**: 7/7 容器 Up + 5/5 health endpoints 正常
- **環境變數正確**: GOOGLE_* 變數設定且格式有效
- **同步功能正常**: portfolio/sync 執行無錯誤
- **FX 模組完整**: 14 單元測試 + 6 Guardrail 測試全 PASSED
- **無違規程式碼**: grep 掃描無結果
- **容器管理正確**: rebuild/restart 流程清晰
- **測試隔離有效**: 無資料殘留或污染
