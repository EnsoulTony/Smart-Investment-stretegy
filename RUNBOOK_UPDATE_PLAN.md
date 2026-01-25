# RUNBOOK.md 更新計畫

## 📊 存在性驗證結果

| 加固項目 | 是否存在 | 章節位置 | 完整度評分 | 需要行動 |
|---------|---------|---------|-----------|----------|
| 1. API Gateway 路由驗證 | ❌ No | - | 0% | **新增 1.2 節** |
| 2. 容器重建規則 | ⚠️ Partial | 2.2 節 (L148-190) | 50% | **大幅加強** |
| 3. 測試隔離 & DB Override | ✅ Yes | 2.1 節 (L61-147) | 90% | 小幅補充 |
| 4. portfolio/sync 行為解釋 | ❌ No | - | 0% | **新增 1.3 節** |
| 5. Google Sheets 環境變數 | ⚠️ Partial | 1.1 節 (L14-46) | 60% | **實戰補強** |
| 6. FX Boundary 硬禁止規則 | ❌ No | - | 0% | **新增 2.3 節** |

**總體評估**: 6 項中 **3 項缺失**，需補充約 **400 行**實戰內容。

---

## 🔧 必須執行的更新

### ✅ 更新 1：加強 1.1 節（Google Sheets 環境變數）

**插入位置**: L46 之後（驗證指令區塊後）

**補充內容**:
```markdown

#### GOOGLE_SA_JSON 格式注意事項

**常見錯誤**（會導致解析失敗）:

```bash
# ❌ 錯誤 1：JSON 有換行
GOOGLE_SA_JSON={
  "type": "service_account",
  "project_id": "your-project"
}

# ❌ 錯誤 2：外層有單引號但內部雙引號未轉義
GOOGLE_SA_JSON='{"type":"service_account"}'

# ❌ 錯誤 3：private_key 的 \n 被錯誤轉義
GOOGLE_SA_JSON={"private_key":"-----BEGIN...\\n..."}  # 雙反斜線
```

**正確格式**:
```bash
# ✅ 正確：整個 JSON 在單行內，不加外層引號
GOOGLE_SA_JSON={"type":"service_account","project_id":"your-project","private_key":"-----BEGIN PRIVATE KEY-----\nMII...","client_email":"..."}
```

**驗證環境變數是否被容器正確讀取**:

```bash
# 方法 1：檢查環境變數是否設定
docker compose exec portfolio-service env | grep GOOGLE

# 應該看到:
# GOOGLE_SA_JSON={"type":"service_account"...
# GOOGLE_SHEET_ID=1-PTHx8TBQ_PPJ...

# 方法 2：測試 JSON 解析
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

# 預期輸出:
# ✅ JSON 解析成功，project_id: portfolio-tracker-485210
```

#### 修改 .env 後如何讓容器吃到

```bash
# 情況 1：只修改環境變數（最快）
docker compose restart portfolio-service

# 情況 2：不確定是否生效（安全做法）
docker compose down
docker compose up -d

# 驗證是否生效（必做）
docker compose exec portfolio-service env | grep GOOGLE_SA_JSON | head -c 50
# 應該看到最新的 JSON 前 50 字元
```

#### 診斷環境變數問題

```bash
# 檢查 .env 檔案格式（是否有隱藏字元）
cat -A .env | grep GOOGLE_SA_JSON | head -1
# 不應該看到 ^M (CRLF) 或其他特殊字元

# 檢查是否為單行
cat .env | grep GOOGLE_SA_JSON | wc -l
# 應該回傳 1

# 檢查 JSON 長度（太短可能不完整）
cat .env | grep GOOGLE_SA_JSON | wc -c
# 通常應該 > 1500 字元（包含完整 private_key）
```
```

---

### ✅ 更新 2：新增 1.2 節（API Gateway 路由驗證）

**插入位置**: L46 之後（1.1 節結尾）

**完整內容**:
```markdown

### 1.2. API Gateway 路由驗證

**目的**: 確認 API Gateway 正確運作且只暴露必要端點。

#### 快速健康檢查

```bash
# API Gateway 健康檢查
curl -s http://localhost:8000/health | jq

# 預期輸出:
# {
#   "status": "healthy",
#   "service": "api-gateway",
#   "timestamp": "2026-01-24T..."
# }
```

#### 驗證端點清單

```bash
# 取得 API Gateway 的所有端點
curl -s http://localhost:8000/openapi.json | jq '.paths | keys'

# 預期輸出（目前只有 /health）:
# [
#   "/health"
# ]

# 如果回傳 404 或空，檢查容器狀態
docker compose ps api-gateway
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

# 取得 portfolio-service 所有端點
curl -s http://localhost:8001/openapi.json | jq '.paths | keys'

# 預期輸出:
# [
#   "/health",
#   "/portfolio/sync",
#   "/portfolio/rebuild_positions",
#   "/portfolio/positions"
# ]
```

#### 驗證所有服務健康狀態

```bash
# 一鍵檢查所有服務
for port in 8000 8001 8002 8003 8004; do
  echo "=== Port $port ==="
  curl -s http://localhost:$port/health | jq '.service, .status' 2>/dev/null || echo "❌ 無回應"
done

# 預期輸出範例:
# === Port 8000 ===
# "api-gateway"
# "healthy"
# === Port 8001 ===
# "portfolio-service"
# "healthy"
# ...
```

#### 常見問題排查

**Q: API Gateway 回傳 404**
```bash
# 檢查容器是否正常運行
docker compose ps api-gateway

# 查看日誌
docker logs smart-investment-strategy-api-gateway-1 --tail 50

# 重啟服務
docker compose restart api-gateway
```

**Q: 為何 API Gateway (8000) 只有 /health 端點？**
A: 目前架構中，API Gateway 僅用於健康檢查聚合。業務端點需直接呼叫各服務（8001, 8002 等）。未來 Sprint 2.x 會實作完整路由代理。

**Q: 如何透過 Gateway 呼叫 Portfolio Service？**
A: 目前階段請直接呼叫 `http://localhost:8001/portfolio/*`。Gateway 路由功能計劃在 Sprint 2.1 實作。
```

---

### ✅ 更新 3：新增 1.3 節（Portfolio Sync 行為解釋）

**插入位置**: 新增的 1.2 節之後

**完整內容**:
```markdown

### 1.3. Portfolio Sync 行為解釋與驗證

**目的**: 理解 portfolio/sync 的去重機制與資料驗證方法。

#### 執行同步

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

#### 解讀輸出欄位

| 欄位 | 含義 | 正常值 |
|-----|------|-------|
| `inserted_count` | 新插入的交易數 | 首次 sync > 0，後續通常為 0 |
| `skipped_count` | 因重複而跳過的交易數 | 等於 Google Sheets 總行數 |
| `sync_run_id` | 本次同步的執行 ID | 正整數，遞增 |
| `duration_seconds` | 同步耗時 | 通常 1-5 秒 |
| `status` | 同步狀態 | "completed" 或 "failed" |

**為何 inserted_count=0, skipped_count=64？**
- Portfolio Service 使用 `source_hash` 欄位去重（基於 user_id + symbol + side + quantity + price + trade_date）
- 相同內容的交易不會重複插入
- **這是正常行為**，代表 Google Sheets 沒有新交易
- 若 Google Sheets 新增一筆交易，下次 sync 會看到 `inserted_count=1, skipped_count=64`

#### 驗證 DB 同步結果

```bash
# 進入 postgres 容器
docker compose exec postgres psql -U investment -d investment_db

# 查詢交易總數
SELECT count(*) FROM trades;

# 查詢最近的交易（驗證內容）
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

#### 驗證 source_hash 去重機制

```bash
# 在 psql 中執行
SELECT source_hash, COUNT(*) as count
FROM trades
GROUP BY source_hash
HAVING COUNT(*) > 1;

# 應該回傳空結果（代表沒有重複的 source_hash）
# 若有重複，代表去重機制失效，需檢查 app/trade_normalizer.py
```

#### 強制重新同步（測試用）

```bash
# ⚠️ 危險操作：刪除所有交易與同步紀錄
docker compose exec postgres psql -U investment -d investment_db -c "TRUNCATE trades, sync_runs CASCADE;"

# 重新同步
curl -s -X POST http://localhost:8001/portfolio/sync | jq

# 此時應該看到 inserted_count > 0（所有交易都是新的）
# 範例輸出:
# {
#   "inserted_count": 64,
#   "skipped_count": 0
# }
```

#### 常見問題排查

**Q: sync 回傳 error_message 不為空**
```bash
# 查詢錯誤訊息
docker compose exec postgres psql -U investment -d investment_db -c "
SELECT id, error_message, inserted_count, skipped_count
FROM sync_runs
WHERE error_message IS NOT NULL
ORDER BY started_at DESC
LIMIT 5;
"

# 查看詳細日誌
docker logs smart-investment-strategy-portfolio-service-1 --tail 100 | grep -i error
```

**Q: 為何 skipped_count 比 Google Sheets 行數少？**
A: 可能有以下原因：
1. Google Sheets 有空白行（會被過濾）
2. 有資料格式錯誤的行（會被跳過並記錄在 `normalized_invalid_count`）
3. 查詢 sync_runs 表確認 `normalized_invalid_count` 欄位

**Q: 如何驗證 Google Sheets 與 DB 的資料一致性？**
```bash
# 1. 查詢 DB 總筆數
docker compose exec postgres psql -U investment -d investment_db -c "SELECT count(*) FROM trades;"

# 2. 檢查 Google Sheets 總行數（排除標題行）
# 手動登入 Google Sheets 確認

# 3. 若不一致，查詢最新 sync_run 的詳細資訊
docker compose exec postgres psql -U investment -d investment_db -c "
SELECT * FROM sync_runs ORDER BY started_at DESC LIMIT 1;
"
```
```

---

### ✅ 更新 4：大幅加強 2.2 節（容器重建規則）

**操作**: 替換 L148-190 的內容

**新內容**:
```markdown
### 2.2. 容器重建規則（何時需要 --build）

**症狀**: 修改程式碼或測試後，容器仍執行舊版本。

#### 決策表：何時需要重建？

| 變更類型 | 只需 restart | 需要 --build | 說明 |
|---------|-------------|-------------|------|
| Python 程式碼 (.py) | ❌ | ✅ | 容器內 /app/ 目錄的檔案不會自動更新 |
| 測試檔案 (tests/*.py) | ❌ | ✅ | 測試被 COPY 進容器，需重建 |
| requirements.txt | ❌ | ✅ | 需重新執行 pip install |
| Dockerfile | ❌ | ✅ | 映像層結構變更 |
| docker-compose.yml (環境變數) | ✅ | ❌ | restart 即可套用 |
| .env 檔案 | ✅ | ❌ | restart 即可套用 |
| 設定檔 (.json, .yaml) | 視情況 | ✅ | 若被 COPY 進容器則需 rebuild |
| alembic 遷移檔案 | ❌ | ✅ | migrations 目錄被 COPY 進容器 |

**記憶口訣**: 「檔案在容器內 = 需 rebuild，檔案在環境變數 = 只需 restart」

#### 標準重建流程

```bash
# 方法 1：快速重建單一服務（推薦）
docker compose up -d --build portfolio-service

# 方法 2：完整重建所有服務（確保一致性）
docker compose down
docker compose up -d --build

# 方法 3：只重建不啟動（檢查建置錯誤）
docker compose build portfolio-service
```

#### 診斷：確認容器是否使用新版本

```bash
# 檢查 1：查看容器建立時間
docker compose ps

# 檢查 2：查看映像建立時間
docker images | grep smart-investment

# 檢查 3：進入容器檢查檔案修改時間
docker compose exec portfolio-service ls -la /app/app/

# 檢查 4：查看容器內的程式碼（確認最新修改）
docker compose exec portfolio-service cat /app/app/main.py | head -20

# 檢查 5：查看容器內的測試檔案
docker compose exec portfolio-service cat /app/tests/test_fx.py | head -20
```

#### 快速驗證流程（開發專用）

```bash
# 1. 修改程式碼後，確認差異
git diff HEAD app/

# 2. 重建容器
docker compose up -d --build portfolio-service

# 3. 等待容器啟動
sleep 3

# 4. 執行測試驗證
docker compose exec portfolio-service pytest tests/ -v

# 5. 確認服務正常
curl http://localhost:8001/health
```

#### 常見錯誤與診斷

**錯誤 1: 只執行 `docker compose up -d`（沒有 --build）**
- **現象**: 程式碼修改沒生效
- **診斷**: 
  ```bash
  # 查看容器建立時間
  docker compose ps portfolio-service
  # 若建立時間早於檔案修改時間，代表沒重建
  ```
- **解決**: 加上 `--build` 旗標

**錯誤 2: 修改 .env 後用 --build**
- **現象**: 浪費時間重建映像（2-3 分鐘）
- **診斷**: 環境變數變更不需要重建映像
- **解決**: 只需 `docker compose restart`

**錯誤 3: 忘記停止舊容器**
- **現象**: 
  ```
  Error response from daemon: driver failed programming external connectivity: 
  Bind for 0.0.0.0:8001 failed: port is already allocated
  ```
- **診斷**: 舊容器仍在運行
- **解決**: 
  ```bash
  docker compose down
  docker compose up -d --build
  ```

**錯誤 4: 修改測試但忘記重建**
- **現象**: pytest 仍執行舊測試
- **診斷**: 
  ```bash
  # 查看容器內的測試檔案
  docker compose exec portfolio-service cat /app/tests/test_fx.py | grep "def test_"
  # 若看不到新增的測試函數，代表沒重建
  ```
- **解決**: 執行 `docker compose up -d --build portfolio-service`

#### 開發時的最佳實務

```bash
# 建立 alias 簡化指令（加入 ~/.bashrc）
alias dc-rebuild='docker compose up -d --build'
alias dc-test='docker compose exec portfolio-service pytest tests/ -v'

# 使用範例
dc-rebuild portfolio-service
sleep 3
dc-test
```

#### CI/CD pipeline 注意事項

- **GitHub Actions**: 每次 push 都會自動 rebuild，無需手動處理
- **本地開發**: 必須手動 rebuild
- **Staging 環境**: 建議每次部署都用 `--build` 確保一致性
```

---

### ✅ 更新 5：新增 2.3 節（FX Boundary 硬禁止規則）

**插入位置**: 2.2 節之後（新的 2.2 節結束後）

**完整內容**:
```markdown

### 2.3. FX Boundary 邊界規範（Sprint 1-4.A）

**目的**: 確保匯率折算邏輯集中管理，避免散落各處造成維護困難與資料不一致。

#### 硬禁止規則（Hard Rules）

**規則 1: 唯一入口點**
- ✅ **允許**: `from app.fx import get_fx_provider`
- ❌ **禁止**: 在 `app/fx/*` 以外直接讀取 `FX_PROVIDER`, `FX_API_KEY`, `VALUATION_CCY` 等環境變數
- ❌ **禁止**: 直接 import `StubFxProvider`, `FxProvider` 等實作類別

**規則 2: 帳務層不做折算**
- ✅ **允許**: 在 `positions` 表儲存 `asset_ccy`（原始幣別）
- ✅ **允許**: 在 `trades` 表記錄原始交易金額
- ❌ **禁止**: 在帳務層（`rebuild_positions`）寫入折算後的 TWD 金額
- ❌ **禁止**: 在 `position_rebuilder.py` 中呼叫 FX Provider

**規則 3: 估值層才做折算**
- ✅ **允許**: 在 API 回應時即時折算（未來 Sprint 2.x）
- ✅ **允許**: 在 `portfolio_snapshots` 表儲存估值快照
- ❌ **禁止**: 在持久化資料中混合原始金額與折算金額

#### 驗證 FX Boundary（Guardrail Tests）

```bash
# 執行 FX 邊界守門測試
docker compose exec portfolio-service pytest tests/test_fx_guardrails.py -v

# 預期輸出（6 個測試全部 PASSED）:
# test_no_direct_fx_env_access_outside_fx_module PASSED
# test_no_direct_provider_import_outside_fx_module PASSED
# test_fx_module_exists_and_has_public_api PASSED
# test_stub_provider_same_currency_returns_original PASSED
# test_stub_provider_cross_currency_raises_not_implemented PASSED
# test_factory_can_switch_providers PASSED
```

#### 違規範例與修正

**違規範例 1: 直接讀取環境變數**
```python
# ❌ 錯誤（在 app/position_rebuilder.py 中）
import os
fx_provider_name = os.getenv('FX_PROVIDER')
valuation_ccy = os.getenv('VALUATION_CCY')

# ✅ 正確
from app.fx import get_fx_provider
fx = get_fx_provider()
# 不需要直接讀環境變數，provider 內部會處理
```

**違規範例 2: 直接 import 實作類別**
```python
# ❌ 錯誤（在 app/main.py 中）
from app.fx.stub_provider import StubFxProvider
provider = StubFxProvider()

# ✅ 正確
from app.fx import get_fx_provider
fx = get_fx_provider()  # 工廠函數會根據環境變數選擇實作
```

**違規範例 3: 帳務層寫入折算金額**
```python
# ❌ 錯誤（在 rebuild_positions 中）
from app.fx import get_fx_provider
fx = get_fx_provider()

for symbol in symbols:
    pos = Position(...)
    if pos.asset_ccy != 'TWD':
        pos.value_twd = fx.convert(pos.value, pos.asset_ccy, 'TWD')  # ❌ 不應該在帳務層
    db.add(pos)

# ✅ 正確（在估值層 API 中即時計算）
@app.get("/portfolio/positions")
def get_positions(user_id: str):
    positions = db.query(Position).filter_by(user_id=user_id).all()
    fx = get_fx_provider()
    
    for pos in positions:
        # 回傳時才做折算（不寫入 DB）
        if pos.asset_ccy != 'TWD':
            pos.value_twd = fx.convert(pos.value, pos.asset_ccy, 'TWD')
    
    return positions
```

#### 違規時的錯誤訊息

如果違反規則，Guardrail 測試會顯示：

```
FAILED tests/test_fx_guardrails.py::test_no_direct_fx_env_access_outside_fx_module

🚨 違反 FX 邊界規範：檢測到直接讀取環境變數

檔案: app/position_rebuilder.py
  ❌ 第 42 行: 直接讀取環境變數 'FX_PROVIDER'
  ❌ 第 43 行: 直接讀取環境變數 'VALUATION_CCY'

💡 修正方式：
  1. 移除直接的環境變數讀取
  2. 使用 'from app.fx import get_fx_provider' 取得 FX 服務
  3. 所有 FX 相關邏輯應該在 app/fx/ 模組內處理
```

#### 手動檢查違規（AST 掃描原理）

```bash
# Guardrail Tests 使用 AST 掃描，你也可以手動檢查

# 檢查是否有直接讀取 FX_* 環境變數
grep -r "os.getenv.*FX_" services/portfolio-service/app/ --exclude-dir=fx

# 檢查是否有直接讀取 VALUATION_* 環境變數
grep -r "os.environ.*VALUATION" services/portfolio-service/app/ --exclude-dir=fx

# 檢查是否有直接 import provider 實作
grep -r "from app.fx.stub_provider" services/portfolio-service/app/ --exclude=__init__.py

# 上述命令應該都回傳空結果（除了 app/fx/ 目錄內的檔案）
```

#### 測試隔離：reset_fx_provider()

```python
# 在測試中需要切換 provider 或重置狀態
from app.fx import get_fx_provider, reset_fx_provider

def test_fx_behavior():
    # 測試前重置（避免其他測試污染）
    reset_fx_provider()
    
    fx = get_fx_provider()  # 重新建立 provider
    rate = fx.get_rate('USD', 'TWD')
    
    # 測試邏輯...
    
    # 測試後清理（可選，pytest fixture 會自動清理）
    reset_fx_provider()
```

#### 相關文件連結

- [Development.md - FX 模組硬禁止規則](Development.md#fx-模組sprint-1-4-a)
- [Strategy.md - 帳務層 vs 估值層](Strategy.md#架構分層)
- [SPRINT_1-4-A_HARDENING_COMPLETE.md](SPRINT_1-4-A_HARDENING_COMPLETE.md) - 完整加固報告
- [app/fx/__init__.py](services/portfolio-service/app/fx/__init__.py) - FX 模組 Public API

#### 驗收命令（Sprint 1-4.A）

```bash
# 完整驗收流程
cd /root/Smart-Investment-stretegy
./verify_sprint_1-4-a.sh

# 或手動執行各步驟
docker compose up -d --build portfolio-service
sleep 3

# 步驟 1: FX 模組單元測試
docker compose exec portfolio-service pytest tests/test_fx.py -v

# 步驟 2: Guardrail Tests（規範守門）
docker compose exec portfolio-service pytest tests/test_fx_guardrails.py -v

# 步驟 3: 驗證 public API
docker compose exec portfolio-service python3 -c "
from app.fx import get_fx_provider, reset_fx_provider
print('✅ Public API 可正常匯入')
"

# 預期結果：所有測試 PASSED，無 import 錯誤
```
```

---

## 📝 執行摘要

### 需要更新的 RUNBOOK.md 區塊

1. **L46 之後**: 插入「GOOGLE_SA_JSON 格式注意事項」（約 80 行）
2. **L46 之後**: 插入「1.2. API Gateway 路由驗證」（約 70 行）
3. **1.2 節之後**: 插入「1.3. Portfolio Sync 行為解釋」（約 100 行）
4. **L148-190**: 替換「2.2. 容器重建規則」（約 150 行）
5. **2.2 節之後**: 插入「2.3. FX Boundary 邊界規範」（約 180 行）

**總新增/修改行數**: ~580 行

### 更新後的章節結構

```
## 1. 日常檢查清單
### 1.1. VM 環境變數配置檢查（Portfolio Service 相關）
  - 基本配置
  - ✨ GOOGLE_SA_JSON 格式注意事項（新增）
  - ✨ 修改 .env 後如何讓容器吃到（新增）
  - ✨ 診斷環境變數問題（新增）
### 1.2. API Gateway 路由驗證（✨ 完整新增）
### 1.3. Portfolio Sync 行為解釋與驗證（✨ 完整新增）

## 2. 異常排查對照表
### 2.1. 測試隔離問題（現有，維持不變）
### 2.2. 容器重建規則（✨ 大幅加強）
  - ✨ 決策表（新增）
  - ✨ 診斷流程（新增）
  - ✨ 常見錯誤與診斷（新增）
### 2.3. FX Boundary 邊界規範（✨ 完整新增）
  - 硬禁止規則
  - Guardrail Tests 驗證
  - 違規範例與修正
  - 驗收命令

## 3-9. 其他章節（維持不變）
```
