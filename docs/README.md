# 文件索引

本目錄包含專案的補充文件，主要文件請參考根目錄。

## 根目錄文件

| 檔案 | 說明 |
|------|------|
| [README.md](../README.md) | 專案入口、MVP 範圍、快速開始 |
| [RUNBOOK.md](../RUNBOOK.md) | 維運指南、日常檢查、異常排查 |
| [RUNBOOK-DOCTOR.md](../RUNBOOK-DOCTOR.md) | 環境自我診斷 |
| [Development.md](../Development.md) | 開發指南、Sprint prompts、PR 檢查清單 |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | 系統架構、微服務邊界 |
| [API_CONTRACTS.md](../API_CONTRACTS.md) | API 契約（Request/Response Schema） |
| [Strategy.md](../Strategy.md) | 策略邏輯、Radar v1.4 規則 |
| [DEPLOYMENT.md](../DEPLOYMENT.md) | 部署計畫、VM 設置 |
| [SECURITY.md](../SECURITY.md) | 安全規範、金鑰管理 |
| [TESTING.md](../TESTING.md) | 測試策略 |
| [CHANGELOG.md](../CHANGELOG.md) | 版本沿革 |

---

## 本目錄結構

```
docs/
├── README.md              # 本文件
├── ci-gate.md             # CI Gate 說明
│
├── sprints/               # Sprint 文件
│   ├── sprint-2.md        # Sprint 2 規格
│   ├── sprint-1-4-status.md
│   ├── sprint-1-4-a/      # FX 模組邊界
│   ├── sprint-1-4-b/      # 估值層骨架
│   └── sprint-1-4-c/      # 額外加固
│
├── reports/               # 技術報告
│   ├── transaction-audit.md
│   ├── portfolio-hardening.md
│   ├── p0-p1-implementation.md
│   ├── short-selling-diagnosis.md
│   └── verification-2026-01-24.md
│
├── runbook/               # RUNBOOK 補充
│   ├── acceptance-commands.md
│   ├── hardening-checklist.md
│   ├── hardening-summary.md
│   └── update-plan.md
│
└── patches/               # PR/Patch 歷史
    ├── api-gateway-proxy.md
    ├── pr-check-enhancements.md
    ├── docs-update-summary.md
    ├── strategy-patch.md
    └── development-patch.md
```

---

## Sprint 文件

### Sprint 2: Strategy Engine
- [sprint-2.md](sprints/sprint-2.md) - Strategy Engine 可插拔架構、v1.4 Plugin

### Sprint 1-4: Portfolio 加固
- [sprint-1-4-status.md](sprints/sprint-1-4-status.md) - 狀態總覽
- [sprint-1-4-2-verification.md](sprints/sprint-1-4-2-verification.md) - 驗證報告
- [sprint-1-4-3-acceptance-report.md](sprints/sprint-1-4-3-acceptance-report.md) - 驗收報告

#### Sprint 1-4.A: FX 模組邊界
- [acceptance-report.md](sprints/sprint-1-4-a/acceptance-report.md)
- [hardening-complete.md](sprints/sprint-1-4-a/hardening-complete.md)
- [pr-summary.md](sprints/sprint-1-4-a/pr-summary.md)

#### Sprint 1-4.B: 估值層骨架
- [implementation.md](sprints/sprint-1-4-b/implementation.md)
- [delivery.md](sprints/sprint-1-4-b/delivery.md)
- [verification-status.md](sprints/sprint-1-4-b/verification-status.md)

#### Sprint 1-4.C: 額外加固
- [acceptance-report.md](sprints/sprint-1-4-c/acceptance-report.md)
- [implementation-status.md](sprints/sprint-1-4-c/implementation-status.md)

---

## 技術報告

| 報告 | 說明 |
|------|------|
| [transaction-audit.md](reports/transaction-audit.md) | 交易稽核報告 |
| [portfolio-hardening.md](reports/portfolio-hardening.md) | Portfolio 服務加固報告 |
| [p0-p1-implementation.md](reports/p0-p1-implementation.md) | P0/P1 錯誤處理改進 |
| [short-selling-diagnosis.md](reports/short-selling-diagnosis.md) | 賣空 Bug 診斷 |
| [verification-2026-01-24.md](reports/verification-2026-01-24.md) | 2026-01-24 驗證報告 |

---

## 功能完成狀態

### 已完成

| 功能 | Sprint | 服務 |
|------|--------|------|
| Portfolio 均價法計算 | 1 | portfolio-service |
| Google Sheets 同步 | 1 | portfolio-service |
| 持倉重算 | 1 | portfolio-service |
| FX 模組介面 + Stub | 1-4.A | portfolio-service |
| 估值層骨架 | 1-4.B | valuation-service |
| Strategy Engine 架構 | 2 | radar-service |
| v1.4 Plugin | 2 | radar-service |
| Sector Rotation 指標 | 2 | indicator-service |
| `/radar/decision` 端點 | 2 | radar-service |

### 待實作

| 功能 | 說明 |
|------|------|
| 真實匯率 Provider | 等估值層穩定後開工 |
| 真實市價 Provider | 同上 |
| `u_pnl` 真實計算 | 當前固定為 0 |
| JWT 驗證 | MVP 未納入 |
