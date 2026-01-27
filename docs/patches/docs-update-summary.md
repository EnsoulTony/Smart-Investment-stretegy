# Sprint 1-4.2 文檔更新總結

## 修改檔案清單

### 1. Development.md（開發指南）

**修改段落**：
- **Sprint 1-4: 持倉重算端點（Positions Rebuilder）**
  - 新增 **Sprint 1-4.1** 小節：均價法（Weighted Average Cost）純函數計算器與完整單元測試
  - 新增 **Sprint 1-4.2** 小節：DB 查詢整合、預覽重算端點與測試加固
  - 新增 **測試加固指南（Sprint 1-4.2 必讀）** 專節

**新增內容**：
- Sprint 1-4.1 實作任務與驗證命令
- Sprint 1-4.2 實作任務與驗證命令
- 測試加固的四個關鍵步驟：
  1. 必須 override get_db dependency
  2. 必須使用 context manager
  3. 插入後必須自我驗證
  4. fixture teardown 必須清除 dependency_overrides
- 完整程式碼範例與說明（為什麼需要？如何實作？）
- 重建容器的必要性說明

**位置**：第 225-363 行

---

### 2. RUNBOOK.md（維運指南）

**修改段落**：
- **2. 異常排查對照表**
  - 新增 **2.1. 測試隔離問題（Troubleshooting: symbols 為空）** 專節
  - 新增 **2.2. 測試修改後需重建容器** 專節

**新增內容**：

**2.1 節**：
- 症狀描述：測試插入資料，API 回傳空結果
- 根本原因分析：SAVEPOINT + transaction 隔離導致兩個 session 互相看不到資料
- 四個關鍵修法步驟（含完整程式碼範例）
- 驗證命令
- 參考範例檔案

**2.2 節**：
- 情況說明：修改測試檔案後測試仍用舊程式碼
- 原因：Dockerfile COPY tests/ 目錄
- 解決方案：重建容器命令
- 一鍵驗證腳本說明
- 注意事項

**位置**：第 61-176 行

---

### 3. SPRINT_1-4-2_VERIFICATION.md（新增檔案）

**檔案類型**：驗收文檔

**內容結構**：
1. **環境要求**
2. **快速驗收（一鍵執行）**
3. **詳細驗收步驟**：
   - 步驟 1：重建容器
   - 步驟 2：執行預覽端點測試
   - 步驟 3：執行完整測試套件
   - 步驟 4：驗證加固措施（可選）
   - 步驟 5：手動測試 API 端點（可選）
4. **Troubleshooting**：
   - 問題 1：symbols 為空
   - 問題 2：測試使用舊程式碼
   - 問題 3：容器啟動失敗
5. **驗收標準**
6. **相關文件**

**特點**：
- 所有命令可直接複製貼上執行
- 提供預期輸出範例
- 包含關鍵檢查點清單
- 附帶完整的 Troubleshooting 指南

---

## 驗收命令（可直接複製貼上）

### 方法 1：一鍵驗證

```bash
# 使用專案提供的腳本
cd /workspaces/Smart-Investment-stretegy
chmod +x test_preview.sh
./test_preview.sh
```

### 方法 2：手動步驟

```bash
# 進入專案目錄
cd /workspaces/Smart-Investment-stretegy

# 重建容器
docker compose up -d --build portfolio-service
sleep 3

# 執行預覽端點測試
docker compose exec portfolio-service pytest tests/test_rebuild_positions_preview.py -v

# 執行完整測試套件
docker compose exec portfolio-service pytest -q
```

### 預期結果

✅ **預覽端點測試**：7 passed in X.XXs
✅ **完整測試套件**：55 passed in X.XXs（48 既有 + 7 個預覽測試）

---

## 驗證已完成

根據終端輸出，Sprint 1-4.2 已成功通過驗收：

```
=== 執行預覽端點測試（含自我驗證檢查）===
tests/test_rebuild_positions_preview.py::TestRebuildPositionsPreview::test_preview_endpoint_exists PASSED [ 14%]
tests/test_rebuild_positions_preview.py::TestRebuildPositionsPreview::test_preview_with_no_trades_returns_empty_symbols PASSED [ 28%]
tests/test_rebuild_positions_preview.py::TestRebuildPositionsPreview::test_preview_with_single_buy_calculates_correctly PASSED [ 42%]
tests/test_rebuild_positions_preview.py::TestRebuildPositionsPreview::test_preview_with_buy_and_sell_calculates_pnl PASSED [ 57%]
tests/test_rebuild_positions_preview.py::TestRebuildPositionsPreview::test_preview_with_multiple_symbols_groups_correctly PASSED [ 71%]
tests/test_rebuild_positions_preview.py::TestRebuildPositionsPreview::test_preview_response_structure_complete PASSED [ 85%]
tests/test_rebuild_positions_preview.py::TestRebuildPositionsPreview::test_preview_missing_user_id_returns_422 PASSED [100%]

============================ 7 passed in 0.85s =============================

=== 執行完整測試套件 ===
.......................................................              [100%]
55 passed in 1.13s
```

**關鍵成功指標**：
- ✅ 自我驗證檢查通過（count = 1, 2, 3 分別在不同測試中）
- ✅ symbols 不為空（計算結果正確）
- ✅ 所有測試通過，無 transaction 隔離問題

---

## 文檔設計原則驗證

### ✅ 遵守最小差異原則
- 只修改必要的段落（新增 Sprint 1-4.2 相關內容）
- 不改變既有架構
- 不引入新依賴

### ✅ 繁體中文撰寫
- 所有新增內容使用繁體中文
- 保持與既有文檔風格一致

### ✅ 可直接執行
- 所有命令在 Codespace + Docker Compose 環境可直接執行
- 包含重建容器的必要步驟

### ✅ 完整的 Troubleshooting
- 症狀描述清晰
- 根本原因分析
- 具體修法與驗證步驟
- 參考範例檔案

### ✅ 四個加固措施完整記錄
1. override get_db dependency - ✅ 已記錄於 Development.md 與 RUNBOOK.md
2. 使用 context manager - ✅ 已記錄並附程式碼範例
3. 插入後自我驗證 - ✅ 已記錄並解釋原因
4. 清除 dependency_overrides - ✅ 已記錄並建議加 assert

---

## 後續建議

1. **新成員入職**：
   - 閱讀 RUNBOOK.md「2.1. 測試隔離問題」章節
   - 執行 SPRINT_1-4-2_VERIFICATION.md 的驗收命令

2. **開發新測試**：
   - 參考 Development.md「測試加固指南」
   - 使用 `tests/test_rebuild_positions_preview.py` 作為模板

3. **CI/CD Pipeline**：
   - 確保 CI 在執行測試前重建容器
   - 檢查測試通過數量（應為 55+）

4. **文檔維護**：
   - Sprint 1-4.3 實作時，繼續更新 Development.md
   - 如果發現新的測試陷阱，補充到 RUNBOOK.md Troubleshooting
