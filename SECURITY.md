# SECURITY.md｜安全規範（MVP）

## 金鑰與憑證

- **任何 API 金鑰、密碼、OAuth 憑證一律不得提交到 Git**。
- 唯一允許的方式為：
  - `.env.example` 提供 placeholder。
  - 實際 `.env` 由開發者自行建立，並確保被 `.gitignore`。
  - CI / GitHub Actions 透過 `Secrets` 管理，名稱需與 `.env.example` 對應。
- 若發現誤提交，立即：
  1. 於供應商後台撤銷金鑰。
  2. 重新產生並更新 `.env` 及 Secrets。
  3. 通知安全負責人與專案 Owner。

### Google Service Account 金鑰管理（Sprint 1-2）

Portfolio Service 使用 Google Service Account 存取 Google Sheets 交易資料。金鑰管理方式：

1. **本機開發環境**：
   - 從 [Google Cloud Console](https://console.cloud.google.com/) 建立 Service Account
   - 下載 JSON 金鑰檔案（例如：`service-account-key.json`）
   - **不要將 JSON 檔案加入 Git**（已在 `.gitignore` 排除）
   - 將整個 JSON 內容複製到 `.env` 的 `GOOGLE_SA_JSON` 變數（單行字串）
   - 範例：`GOOGLE_SA_JSON='{"type":"service_account","project_id":"..."}'`

2. **VM 生產環境**：
   - 在 VM 上建立 `/opt/radar-warroom/.env` 檔案
   - 將 Service Account JSON 設定到 `GOOGLE_SA_JSON` 環境變數
   - 確保檔案權限：`chmod 600 /opt/radar-warroom/.env`
   - 確保擁有者：`chown <deploy_user>:<deploy_user> /opt/radar-warroom/.env`

3. **GitHub Actions / CI**：
   - 在 GitHub repo 的 Settings → Secrets and variables → Actions 新增 Secret
   - Secret 名稱：`GOOGLE_SA_JSON`
   - Secret 值：完整的 Service Account JSON 內容（單行或多行皆可）
   - 在 workflow 中透過 `${{ secrets.GOOGLE_SA_JSON }}` 注入環境變數

4. **權限最小化原則**：
   - Service Account 僅授予 Google Sheets「唯讀」權限
   - 僅分享必要的 Google Sheets 給該 Service Account（透過 email 分享）
   - 定期檢查 Service Account 的存取紀錄（Google Cloud Console → IAM → Service Accounts）

5. **金鑰輪替**：
   - 建議每 90 天輪替一次 Service Account 金鑰
   - 輪替步驟：
     1. 在 Google Cloud Console 建立新金鑰
     2. 更新所有環境的 `GOOGLE_SA_JSON`（本機、VM、GitHub Secrets）
     3. 驗證新金鑰運作正常
     4. 刪除舊金鑰

## 存取控制

- GitHub repo 需啟用 2FA。
- VM SSH 金鑰僅限 DevOps 管理，使用者不得私自散佈。
- Postgres 僅允許內部 Docker 網路連線（`postgres` 服務），外部如需調試須透過 SSH Tunnel。

## 數據保護

- 所有匯入的研究報告 PDF、Google Sheets 資料僅作內部分析，不可對外分享。
- 備份檔案須加密後存放於安全儲存體（S3 + KMS 或等級相當方案）。
- 資料匯出前需確認已去除個資或敏感標記。

## 事件回報

- 發現安全事件時，於 30 分鐘內通知：security@example.com。
- 需提供：事件時間、範圍、已採取的緊急措施。
- 將事件記錄在 `RUNBOOK.md` 的 Incident Log（未來版本補充）。
