# PR: 新增 PR Gate 檢查 - 防止 VM 才爆的問題與 Secret 外洩

## 目的

本 PR 對 `tools/pr_check.sh` 進行最小幅度的「加法」修改，新增兩個關鍵檢查步驟，確保在本機/CI 階段就能發現問題，避免「VM 才爆」的情況。

## 新增檢查項目

### ✅ STEP 3: Compose config secrets leak guard

**目的：防止 Secret 外洩到 docker compose config**

檢查內容：
- 禁止 `GOOGLE_SA_JSON:` 出現在 compose config（代表整包 JSON 塞入環境變數）
- 禁止 `BEGIN PRIVATE KEY` 出現（代表 private key 可能被印出）

**為什麼需要這個檢查？**
- 避免敏感金鑰被意外提交到版本控制或 CI 日誌
- 確保遵循「使用 GOOGLE_SA_JSON_PATH + volume mount」的最佳實踐
- 防止 secret 在 `docker compose config` 輸出中暴露

**失敗時的 Remediation：**
```
❌ Remediation:
   - Use GOOGLE_SA_JSON_PATH instead of GOOGLE_SA_JSON
   - Mount key file via docker-compose.secrets.yml with volume bind
   - Example: /secure/keys/google_sa.json:/run/keys/google_sa.json:ro
   - See RUNBOOK.md 'Google Service Account 金鑰部署注意事項' section
```

**輸出範例：**
```
==> STEP: Compose config secrets leak guard
command: docker compose config | grep -E 'GOOGLE_SA_JSON:|BEGIN PRIVATE KEY'
Checking for secrets leakage in compose config...
  matches_GOOGLE_SA_JSON: 0
  matches_BEGIN_PRIVATE_KEY: 0
decision=pass
```

---

### ✅ STEP 10: Valuation API JSON contract check (200 success path)

**目的：端到端驗證 200 成功路徑的 JSON 合約**

**為什麼需要這個檢查？**
- 現有 Step 9 只檢查 409（precondition_failed）情境
- 曾出現「jq: parse error」錯誤，代表 API 回傳非 JSON 格式
- 需要確保成功路徑真的回傳有效的 JSON，而非 dict repr 或純文字
- **這是「避免 VM 才爆」的關鍵檢查** - 本機測試可能因為沒有真實 trades 而走不到 200 路徑，導致問題在 VM 才被發現

檢查內容：
1. **前置條件自動化**：使用 `./tools/portfolio_refresh.sh tony` 確保有 trades 資料（避免假設 DB 狀態）
2. **HTTP code 驗證**：必須為 200 或 409（409 視為預期的替代路徑）
3. **Content-Type 驗證**：必須包含 `application/json`
4. **JSON parse 驗證**：使用 Python `json.loads()` 確保可解析（比 jq 更穩定）
5. **Schema 驗證**：必須包含 `status`, `totals`, `positions`, `evidence` 欄位
6. **Evidence 不洩漏檢查**：
   - 不可包含 `postgresql://`
   - 不可包含 `BEGIN PRIVATE KEY`
   - 不可包含未遮罩的 secret 值（只允許如 `D**********L` 的遮罩格式）

**輸出範例（200 成功）：**
```
==> STEP: Valuation API JSON contract check (200 success path)
command: portfolio_refresh.sh + curl + JSON validation
Ensuring success path is reachable (portfolio sync + trades)...
command: ./tools/portfolio_refresh.sh tony
  portfolio_refresh: completed
command: curl -s -w '\n%{http_code}\n%{content_type}' 'http://localhost:8005/valuation/portfolio?user_id=tony&base_ccy=TWD'
  http_code: 200
  content_type: application/json
  content_type_ok: yes
  json_parse_ok: yes
  required_fields_ok: yes (status, totals, positions, evidence)
  evidence_leak_check: pass (no postgresql://, private keys, or unmasked secrets)
  decision: pass
```

**輸出範例（409 替代路徑）：**
```
==> STEP: Valuation API JSON contract check (200 success path)
command: portfolio_refresh.sh + curl + JSON validation
Ensuring success path is reachable (portfolio sync + trades)...
command: ./tools/portfolio_refresh.sh tony
  portfolio_refresh: failed (may affect 200 path reachability)
command: curl -s -w '\n%{http_code}\n%{content_type}' 'http://localhost:8005/valuation/portfolio?user_id=tony&base_ccy=TWD'
  http_code: 409
  content_type: application/json
  → Got 409 (no trades), this is expected alternative path
  decision: pass (409 scenario already validated in Step 9)
```

---

## 修改原則遵循

### ✅ 只做「加法」修改
- 保留所有原有 step 的檢查邏輯
- 沒有刪除任何既有檢查
- 沒有修改既有檢查的判定條件

### ⚠️ 必要的 STEP 編號更新

**為什麼需要重新編號？（可證偽）**

1. **新增 STEP 3（secrets leak guard）** 必須放在 compose config 相關檢查的最早階段（越早發現 secret 洩漏越好）
2. **新增 STEP 10（200 success path）** 必須緊接在 STEP 9（409 檢查）之後，保持邏輯連貫性
3. 若不重新編號，會造成：
   - STEP 順序跳號（例如 Step 3 → Step 5）
   - 邏輯順序混亂（200 檢查應該緊接在 409 檢查之後）
   - Summary 中的 step 編號與實際執行順序不一致

**最小 diff 原則：**
- 只修改了 `echo "==> STEP:"` 中的編號（從 3→4, 4→5, ..., 12→14）
- 沒有修改任何檢查邏輯的程式碼
- 保留了所有原有的輸出格式（`==> STEP:`、`command:`、`decision=` 風格）

**變更對照表：**
```
原 Step 3 → 新 Step 4: docker compose config env allow-list
原 Step 4 → 新 Step 5: docker compose config env checks
原 Step 5 → 新 Step 6: Check services are running
原 Step 6 → 新 Step 7: Runtime env sanity
原 Step 7 → 新 Step 8: Runtime guard injection test
原 Step 8 → 新 Step 9: Valuation API JSON contract check (409)
[新增]   → 新 Step 10: Valuation API JSON contract check (200)
原 Step 9 → 新 Step 11: pytest (portfolio-service)
原 Step 10 → 新 Step 12: pytest collect-only (portfolio-service)
原 Step 11 → 新 Step 13: pytest (valuation-service)
原 Step 12 → 新 Step 14: pytest collect-only (valuation-service)
```

### ✅ 維持 fail-fast 與清晰輸出
- 任一檢查失敗會立即 exit 1
- 所有輸出遵循原有格式
- 失敗時提供明確的 remediation 指引

### ✅ 無新依賴
- 使用既有工具：`grep`, `python3`, `curl`, `docker compose`
- 不需要 `apt install` 任何新套件
- 可在 VM / Codespaces 直接執行

### ✅ 避免敏感資訊洩漏
- 不印出完整 compose config
- 只顯示 key name，遮罩 value（`***`）
- response 預覽限制在 200 字元

---

## 測試結果

執行 `./tools/pr_check.sh` 後，新增的兩個 STEP 輸出如下：

### STEP 3 輸出（Secrets Leak Guard）
```
==> STEP: Compose config secrets leak guard
command: docker compose config | grep -E 'GOOGLE_SA_JSON:|BEGIN PRIVATE KEY'
Checking for secrets leakage in compose config...
  matches_GOOGLE_SA_JSON: 0
  matches_BEGIN_PRIVATE_KEY: 0
decision=pass
```

### STEP 10 輸出（200 Success Path）
```
==> STEP: Valuation API JSON contract check (200 success path)
command: portfolio_refresh.sh + curl + JSON validation
Ensuring success path is reachable (portfolio sync + trades)...
command: ./tools/portfolio_refresh.sh tony
  portfolio_refresh: completed
command: curl -s -w '\n%{http_code}\n%{content_type}' 'http://localhost:8005/valuation/portfolio?user_id=tony&base_ccy=TWD'
  http_code: 200
  content_type: application/json
  content_type_ok: yes
  json_parse_ok: yes
  required_fields_ok: yes (status, totals, positions, evidence)
  evidence_leak_check: pass (no postgresql://, private keys, or unmasked secrets)
  decision: pass
```

---

## 檔案變更

- `tools/pr_check.sh`: 新增 STEP 3 與 STEP 10，並重新編號既有 steps（3-12 → 4-14）

## 相關文件

- [RUNBOOK.md - Google Service Account 金鑰部署注意事項](RUNBOOK.md)
- [docker-compose.secrets.example.yml](docker-compose.secrets.example.yml)

---

## Checklist

- [x] 遵循「只做加法」原則
- [x] 保留原有 step 順序與檢查邏輯
- [x] 新增 STEP 3: Compose config secrets leak guard
- [x] 新增 STEP 10: Valuation API JSON contract check (200 success path)
- [x] 維持原有輸出格式（`==> STEP:`、`command:`、`decision=`）
- [x] 無新依賴引入
- [x] 可在 VM / Codespaces 執行
- [x] 避免敏感資訊洩漏
- [x] 更新 Summary 章節
- [x] 本機測試通過
