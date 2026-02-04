# Excel 檔案匯入功能

## 功能概述

Portfolio Service 現在支援從遠端 URL 或本地路徑讀取 Excel 檔案，作為 Google Sheets 同步的替代方案。

## 技術實作

### 新增檔案

1. **`services/portfolio-service/app/excel_client.py`**
   - Excel 檔案客戶端
   - 支援本地檔案和遠端 URL
   - 自動處理臨時檔案清理

2. **`services/portfolio-service/tests/test_excel_client.py`**
   - Excel 客戶端單元測試

### 依賴套件

在 `services/portfolio-service/requirements.txt` 新增：
```
pandas>=2.0.0,<3.0.0
openpyxl>=3.1.0,<4.0.0
```

### API 端點

#### `POST /portfolio/sync_from_excel`

從遠端 Excel 檔案同步交易資料。

**Query Parameters:**
- `excel_url` (required): Excel 檔案的 URL（HTTP/HTTPS）
- `sheet_name` (optional): 工作表名稱，預設 "Sheet1"

**Response:**
```json
{
  "status": "succeeded",
  "source_url": "https://example.com/trades.xlsx",
  "sheet_name": "trades",
  "records_count": 3,
  "valid_trades_count": 3,
  "failed_rows_count": 0,
  "columns": ["user_id", "symbol", "asset_ccy", ...],
  "sample": [{...}, {...}, {...}],
  "message": "成功讀取 3 筆資料，其中 3 筆格式正確"
}
```

## 使用方式

### 方法 1：使用 curl

```bash
curl -X POST "http://localhost:8000/portfolio/sync_from_excel?excel_url=https://example.com/trades.xlsx&sheet_name=trades"
```

### 方法 2：使用 Swagger UI

1. 開啟 http://localhost:8001/docs
2. 找到 `POST /portfolio/sync_from_excel` 端點
3. 點擊 "Try it out"
4. 輸入參數：
   - `excel_url`: 您的 Excel 檔案 URL
   - `sheet_name`: 工作表名稱（例如 "trades"）
5. 點擊 "Execute"

### 方法 3：Python 程式碼

```python
from app.excel_client import ExcelClient

# 從遠端 URL 讀取
client = ExcelClient(source_url="https://example.com/trades.xlsx", sheet_name="trades")
records = client.fetch_trades_dicts()

# 從本地檔案讀取
client = ExcelClient(file_path="/path/to/trades.xlsx", sheet_name="trades")
records = client.fetch_trades_dicts()
```

## Excel 檔案格式要求

### 必要欄位

| 欄位名稱 | 型別 | 說明 | 範例 |
|---------|------|------|------|
| user_id | 文字 | 使用者 ID | tony |
| symbol | 文字 | 標的代號 | AAPL |
| asset_ccy | 文字 | 資產幣別 | USD |
| side | 文字 | 交易方向 | buy / sell |
| quantity | 數字 | 交易數量 | 100 |
| price | 數字 | 交易價格 | 150.50 |
| fee | 數字 | 手續費 | 1.5 |
| trade_date | 日期時間 | 交易日期 | 2026-01-20 10:00:00 |
| broker | 文字 | 券商 | IB |

### Excel 檔案範例

可以在 Excel 中建立如下表格：

| user_id | symbol | asset_ccy | side | quantity | price | fee | trade_date | broker |
|---------|--------|-----------|------|----------|-------|-----|------------|--------|
| tony | AAPL | USD | buy | 10 | 180.50 | 1.5 | 2026-01-20 10:00:00 | IB |
| tony | GOOGL | USD | buy | 5 | 145.00 | 1.0 | 2026-01-21 11:00:00 | IB |
| tony | TSLA | USD | buy | 3 | 250.00 | 2.0 | 2026-01-22 14:00:00 | IB |

## 測試結果

### ✅ 本地檔案讀取測試

```
✅ Excel 讀取成功！
讀取到 3 筆資料

資料範例：
1. {'user_id': 'tony', 'symbol': 'AAPL', 'asset_ccy': 'USD', 'side': 'buy', ...}
2. {'user_id': 'tony', 'symbol': 'GOOGL', 'asset_ccy': 'USD', 'side': 'buy', ...}
```

## 公開 Excel 檔案的方式

### Google Drive
1. 上傳 Excel 檔案到 Google Drive
2. 右鍵點擊檔案 → 取得連結
3. 設定為「知道連結的任何人」
4. 使用類似這樣的 URL：
   ```
   https://drive.google.com/uc?export=download&id=FILE_ID
   ```

### Dropbox
1. 上傳檔案到 Dropbox
2. 建立共享連結
3. 將 `www.dropbox.com` 改為 `dl.dropboxusercontent.com`
4. 將 `?dl=0` 改為 `?dl=1`

### GitHub
1. 將 Excel 檔案推送到 GitHub repository
2. 點擊檔案，然後點擊 "Raw" 按鈕
3. 複製該 URL

## 特性

- ✅ 支援 .xlsx 和 .xls 格式
- ✅ 自動下載遠端檔案到臨時目錄
- ✅ 使用完畢後自動清理臨時檔案
- ✅ 移除空白列
- ✅ 資料標準化與驗證
- ✅ 錯誤處理與日誌記錄
- ✅ 完整的單元測試覆蓋

## 下一步

目前 `/portfolio/sync_from_excel` 端點僅用於測試和預覽。若要將 Excel 資料實際寫入資料庫，可以：

1. 擴展該端點加入資料寫入邏輯
2. 或使用 `ExcelClient` 替換 `SyncService` 中的 `SheetsClient`
3. 新增環境變數來選擇資料來源（Google Sheets 或 Excel URL）

## 維護注意事項

- 確保遠端 URL 可公開訪問
- Excel 檔案大小建議不超過 10MB
- 遠端下載預設 timeout 為 30 秒
- 臨時檔案儲存在系統臨時目錄，會自動清理
