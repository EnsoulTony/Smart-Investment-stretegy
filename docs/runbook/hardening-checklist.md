# RUNBOOK 加固檢查報告

## 📋 第一部分：應該被寫進 RUNBOOK 的加固清單

### 1. API Gateway 路由驗證
**狀態**: ❌ **缺失**

**應包含內容**:
- 如何驗證 `http://localhost:8000` 只暴露 `/health` 端點
- 如何確認 API Gateway 正確代理到 portfolio-service
- 使用 `curl` + `jq` 驗證 OpenAPI 規格
- 直接呼叫 portfolio-service (8001) vs 透過 gateway (8000) 的差異

**建議章節**: `## 1.2. API Gateway 路由驗證`
**插入位置**: 在「1.1. VM 環境變數配置檢查」之後

---

### 2. 容器重建規則
**狀態**: ⚠️ **部分存在**（2.2 節有提到，但不夠完整）

**缺失內容**:
- 明確規則：何時必須 `--build`、何時只需 `restart`
- 常見錯誤：「測試用新碼、容器跑舊碼」的診斷方法
- Python 程式碼修改 vs 依賴修改 vs 設定檔修改的不同處理

**建議加強**: 在現有 2.2 節補充完整的決策表

---

### 3. 測試隔離與 DB Session Override
**狀態**: ✅ **已存在**（2.1 節）

**評估**: 內容完整，包含 `dependency_overrides` + `SAVEPOINT` 範例

**建議補充**: 加入「常見錯誤模式」清單（如忘記 teardown、忘記 commit）

---

### 4. portfolio/sync 行為解釋
**狀態**: ❌ **缺失**

**應包含內容**:
- `inserted_count=0, skipped_count=64` 的含義（source_hash 去重）
- 如何查詢 DB 驗證同步結果
- `sync_runs` 表的用途與查詢命令
- 常見問題：為何重複 sync 都是 skipped？

**建議章節**: `## 1.3. Portfolio Sync 行為解釋與驗證`
**插入位置**: 在「1.2. API Gateway 路由驗證」之後

---

### 5. Google Sheets 環境變數配置
**狀態**: ✅ **已存在**（1.1 節）

**評估**: 基本內容存在

**建議補充**: 
- `GOOGLE_SA_JSON` 換行/引號/轉義的注意事項（實戰問題）
- VM 上修改 `.env` 後如何讓容器吃到（restart vs rebuild）
- 驗證環境變數是否正確載入的命令

---

### 6. FX Boundary（Sprint 1-4.A）硬禁止規則
**狀態**: ❌ **完全缺失**

**應包含內容**:
- 硬禁止規則：只能透過 `app.fx.get_fx_provider()` 取得 provider
- 禁止在 `app/fx/*` 之外讀取 `FX_*` / `VALUATION_*` env
- 禁止帳務層寫入折算金額/匯率欄位
- Guardrail Tests 的驗證命令
- 違規時的錯誤訊息範例

**建議章節**: `## 2.3. FX Boundary 邊界規範（Sprint 1-4.A）`
**插入位置**: 在「2.2. 測試修改後需重建容器」之後

---

## 📊 第二部分：文件存在性驗證摘要

| 加固項目 | 是否存在 | 完整度 | 需補充內容 |
|---------|---------|-------|-----------|
| API Gateway 路由驗證 | ❌ No | 0% | 完整章節 + 驗證命令 |
| 容器重建規則 | ⚠️ Partial | 40% | 決策表 + 診斷方法 |
| 測試隔離 & DB Override | ✅ Yes | 85% | 常見錯誤模式 |
| portfolio/sync 行為 | ❌ No | 0% | 完整章節 + DB 查詢 |
| Google Sheets 環境變數 | ✅ Yes | 60% | 換行/引號處理實戰 |
| FX Boundary 規範 | ❌ No | 0% | 完整章節 + Guardrail |

**結論**: 6 項中有 3 項缺失或不完整，需補充約 **60%** 的加固文件。

---

## 🔧 第三部分：建議的 RUNBOOK 章節結構

```markdown
## 1. 日常檢查清單
### 1.1. VM 環境變數配置檢查（已存在，需補充）
### 1.2. API Gateway 路由驗證（新增）
### 1.3. Portfolio Sync 行為解釋與驗證（新增）

## 2. 異常排查對照表
### 2.1. 測試隔離問題（已存在，需補充）
### 2.2. 容器重建規則（已存在，需大幅加強）
### 2.3. FX Boundary 邊界規範（新增）

## 3-9. 保持原有章節
```

---

## 📝 第四部分：待補充的具體內容

### 新章節 1.2：API Gateway 路由驗證

```markdown
### 1.2. API Gateway 路由驗證

**目的**: 確認 API Gateway 只暴露必要端點，且正確代理到後端服務。

#### 驗證 API Gateway 端點清單

```bash
# 取得 API Gateway OpenAPI 規格
curl -s http://localhost:8000/openapi.json | jq '.paths | keys'

# 預期輸出（只有 /health）:
# [
#   "/health"
# ]
```

#### 驗證 API Gateway Health

```bash
curl -s http://localhost:8000/health | jq

# 預期輸出:
# {
#   "status": "healthy",
#   "service": "api-gateway",
#   "timestamp": "2026-01-24T..."
# }
```

#### 驗證 Portfolio Service 直接存取

```bash
# 直接呼叫 portfolio-service (8001 port)
curl -s http://localhost:8001/health | jq

# 預期輸出:
# {
#   "status": "healthy",
#   "service": "portfolio-service"
# }
```

#### 驗證 Portfolio Service 端點清單

```bash
# 取得 portfolio-service 所有端點
curl -s http://localhost:8001/openapi.json | jq '.paths | keys'

# 預期輸出:
# [
#   "/health",
#   "/portfolio/sync",
#   "/portfolio/rebuild",
#   "/portfolio/positions"
# ]
```

#### 常見問題

**Q: 為何 8000 只有 /health？**
A: API Gateway 目前只做健康檢查聚合，業務端點需直接呼叫各服務（8001, 8002 等）。未來會加入路由代理。

**Q: 如何透過 Gateway 呼叫 Portfolio Service？**
A: 目前階段請直接呼叫 8001。Gateway 代理功能在 Sprint 2.x 實作。
```

### 新章節 1.3：Portfolio Sync 行為解釋

```markdown
### 1.3. Portfolio Sync 行為解釋與驗證

**目的**: 理解 portfolio/sync 的去重機制與資料驗證方法。

#### 執行同步

```bash
# 呼叫 sync 端點
curl -s -X POST http://localhost:8001/portfolio/sync | jq

# 預期輸出:
# {
#   "status": "completed",
#   "inserted_count": 0,
#   "skipped_count": 64,
#   "sync_run_id": 123,
#   "duration_seconds": 2.5
# }
```

#### 解讀輸出

- **inserted_count=0**: 沒有新交易被插入
- **skipped_count=64**: 64 筆交易因 `source_hash` 重複而跳過
- **sync_run_id**: 本次同步的執行 ID（用於追蹤）

**為何都是 skipped？**
- Portfolio Service 使用 `source_hash` 欄位去重（基於 user_id + symbol + side + quantity + price + trade_date）
- 相同內容的交易不會重複插入
- 這是**正常行為**，代表 Google Sheets 沒有新交易

#### 驗證 DB 同步結果

```bash
# 進入 postgres 容器
docker compose exec postgres psql -U investment -d investment_db

# 查詢交易總數
SELECT count(*) FROM trades;

# 查詢最近的交易
SELECT id, user_id, symbol, side, quantity, price, trade_date, source_hash 
FROM trades 
ORDER BY trade_date DESC 
LIMIT 5;

# 查詢同步執行紀錄
SELECT id, status, started_at, completed_at, inserted_count, skipped_count, error_message
FROM sync_runs 
ORDER BY started_at DESC 
LIMIT 5;

# 退出 psql
\q
```

#### 查詢 source_hash 重複情況

```bash
# 在 psql 中執行
SELECT source_hash, COUNT(*) as count
FROM trades
GROUP BY source_hash
HAVING COUNT(*) > 1;

# 應該回傳空結果（代表沒有重複）
```

#### 強制重新同步（清空測試）

```bash
# ⚠️ 危險操作：刪除所有交易
docker compose exec postgres psql -U investment -d investment_db -c "TRUNCATE trades, sync_runs CASCADE;"

# 重新同步
curl -s -X POST http://localhost:8001/portfolio/sync | jq

# 此時應該看到 inserted_count > 0
```
```

### 加強章節 2.2：容器重建規則

```markdown
### 2.2. 容器重建規則（何時需要 --build）

**症狀**: 修改程式碼後測試失敗，但實際上容器還在跑舊版本。

#### 決策表：何時需要重建？

| 變更類型 | 重啟即可 | 需要 --build | 說明 |
|---------|---------|-------------|------|
| Python 程式碼 (.py) | ❌ | ✅ | 容器內的檔案不會自動更新 |
| requirements.txt | ❌ | ✅ | 需重新 pip install |
| Dockerfile | ❌ | ✅ | 映像層變更 |
| docker-compose.yml 環境變數 | ✅ | ❌ | restart 即可 |
| .env 檔案 | ✅ | ❌ | restart 即可 |
| 設定檔 (.json, .yaml) | ❌ | ✅ | 若被 COPY 進容器 |
| 測試檔案 (tests/) | ❌ | ✅ | 同程式碼 |

#### 標準重建流程

```bash
# 停止服務
docker compose down

# 重建並啟動（推薦）
docker compose up -d --build

# 或僅重建特定服務
docker compose up -d --build portfolio-service
```

#### 診斷：確認容器是否使用新版本

```bash
# 查看容器建立時間
docker compose ps

# 查看映像建立時間
docker images | grep smart-investment

# 進入容器檢查檔案修改時間
docker compose exec portfolio-service ls -la /app/app/

# 查看容器內的程式碼
docker compose exec portfolio-service cat /app/app/main.py | head -20
```

#### 快速驗證流程

```bash
# 1. 修改程式碼後
git diff HEAD app/

# 2. 重建容器
docker compose up -d --build portfolio-service

# 3. 執行測試驗證
docker compose exec portfolio-service pytest tests/ -v

# 4. 確認服務正常
curl http://localhost:8001/health
```

#### 常見錯誤

**錯誤 1**: 只執行 `docker compose up -d`（沒有 --build）
- **現象**: 程式碼修改沒生效
- **解決**: 加上 `--build` 旗標

**錯誤 2**: 修改 .env 後用 --build
- **現象**: 浪費時間重建映像
- **解決**: 環境變數變更只需 `docker compose restart`

**錯誤 3**: 忘記停止舊容器
- **現象**: 新容器無法啟動（port 被占用）
- **解決**: 先執行 `docker compose down`
```

### 新章節 2.3：FX Boundary 邊界規範

```markdown
### 2.3. FX Boundary 邊界規範（Sprint 1-4.A）

**目的**: 確保匯率折算邏輯集中管理，避免散落各處造成維護困難。

#### 硬禁止規則（Hard Rules）

**規則 1: 唯一入口**
- ✅ **允許**: `from app.fx import get_fx_provider`
- ❌ **禁止**: 在 `app/fx/*` 以外直接讀取 `FX_PROVIDER`, `VALUATION_CCY` 等環境變數
- ❌ **禁止**: 直接 import `StubFxProvider`, `FxProvider` 等實作類別

**規則 2: 帳務層不做折算**
- ✅ **允許**: 在 `positions` 表儲存 `asset_ccy`（原始幣別）
- ❌ **禁止**: 在帳務層寫入折算後的 TWD 金額
- ❌ **禁止**: 在 `rebuild_positions` 中呼叫 FX Provider

**規則 3: 估值層才做折算**
- ✅ **允許**: 在 API 回應時即時折算（未來 Sprint 2.x）
- ✅ **允許**: 在 `portfolio_snapshots` 表儲存估值快照

#### 驗證 FX Boundary（Guardrail Tests）

```bash
# 執行 FX 邊界守門測試
docker compose exec portfolio-service pytest tests/test_fx_guardrails.py -v

# 預期輸出：
# test_no_direct_fx_env_access_outside_fx_module PASSED
# test_no_direct_provider_import_outside_fx_module PASSED
# test_fx_module_exists_and_has_public_api PASSED
```

#### 違規範例與修正

**違規範例 1: 直接讀取環境變數**
```python
# ❌ 錯誤
import os
fx_provider = os.getenv('FX_PROVIDER')

# ✅ 正確
from app.fx import get_fx_provider
fx = get_fx_provider()
```

**違規範例 2: 直接 import 實作**
```python
# ❌ 錯誤
from app.fx.stub_provider import StubFxProvider
provider = StubFxProvider()

# ✅ 正確
from app.fx import get_fx_provider
fx = get_fx_provider()
```

**違規範例 3: 帳務層寫入折算金額**
```python
# ❌ 錯誤（在 rebuild_positions 中）
fx = get_fx_provider()
twd_value = fx.convert(usd_value, 'USD', 'TWD')
position.valuation_twd = twd_value  # 不應該在帳務層

# ✅ 正確（在估值層 API 中）
positions = get_positions(user_id)
for pos in positions:
    if pos.asset_ccy != 'TWD':
        pos.value_twd = fx.convert(pos.value, pos.asset_ccy, 'TWD')
```

#### 違規時的錯誤訊息

如果違反規則，Guardrail 測試會顯示：

```
🚨 違反 FX 邊界規範：檢測到直接讀取環境變數

檔案: app/position_rebuilder.py
  ❌ 第 42 行: 直接讀取環境變數 'FX_PROVIDER'

💡 修正方式：
  1. 移除直接的環境變數讀取
  2. 使用 'from app.fx import get_fx_provider' 取得 FX 服務
```

#### 相關文件

- [Development.md](Development.md): 硬禁止規則完整說明
- [Strategy.md](Strategy.md): 帳務層 vs 估值層架構設計
- [SPRINT_1-4-A_HARDENING_COMPLETE.md](SPRINT_1-4-A_HARDENING_COMPLETE.md): 完整加固報告
```

### 加強章節 1.1：Google Sheets 環境變數

```markdown
### 1.1. VM 環境變數配置檢查（Portfolio Service 相關）

#### GOOGLE_SA_JSON 配置注意事項

**格式要求**: 整個 JSON 物件需要在單行內（不能有換行）

**錯誤範例**（會導致解析失敗）:
```bash
# ❌ 錯誤：有換行
GOOGLE_SA_JSON={
  "type": "service_account",
  "project_id": "your-project"
}

# ❌ 錯誤：外層有單引號，內部雙引號未轉義
GOOGLE_SA_JSON='{"type":"service_account"}'
```

**正確範例**:
```bash
# ✅ 正確：整個 JSON 在單行內，不加外層引號
GOOGLE_SA_JSON={"type":"service_account","project_id":"your-project","private_key":"-----BEGIN PRIVATE KEY-----\nMII...","client_email":"..."}
```

**注意事項**:
1. **不要**在 JSON 外加單引號或雙引號
2. `private_key` 內的 `\n` 換行符號保持原樣
3. 複製時確保沒有意外的空白或換行
4. Windows 使用者注意 CRLF vs LF 問題

#### 修改 .env 後如何讓容器吃到

```bash
# 情況 1: 只修改環境變數（推薦）
docker compose restart portfolio-service

# 情況 2: 不確定是否生效（安全做法）
docker compose down
docker compose up -d --build portfolio-service

# 驗證環境變數是否載入
docker compose exec portfolio-service env | grep GOOGLE

# 應該看到:
# GOOGLE_SA_JSON={"type":"service_account"...
# GOOGLE_SHEET_ID=1-PTHx8TBQ_PPJ...
```

#### 診斷環境變數問題

```bash
# 檢查 .env 檔案格式
cat .env | grep GOOGLE_SA_JSON | wc -l
# 應該是 1（只有一行）

# 檢查是否有隱藏字元
cat -A .env | grep GOOGLE_SA_JSON | head -1
# 不應該看到 ^M (CRLF) 或其他特殊字元

# 測試 JSON 是否可解析
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
```

---

## 總結

**需要補充的主要章節**:
1. ✅ 1.1 Google Sheets 環境變數（加強）
2. 🆕 1.2 API Gateway 路由驗證（完整新增）
3. 🆕 1.3 Portfolio Sync 行為解釋（完整新增）
4. ✅ 2.1 測試隔離（小幅補充）
5. ✅ 2.2 容器重建規則（大幅加強）
6. 🆕 2.3 FX Boundary 邊界規範（完整新增）

**預估工作量**: 約 300-400 行新內容，涵蓋 3 個新章節 + 3 個加強章節。
