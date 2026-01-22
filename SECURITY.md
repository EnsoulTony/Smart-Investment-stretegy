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
