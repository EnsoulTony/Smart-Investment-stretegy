# 文件審計報告

**日期:** 2026-01-27
**範圍:** 全專案 MD 檔案審計與重整

---

## 一、文件重整結果

### 根目錄保留的核心文件 (11 個)

| 檔案 | 用途 | 說明 |
|------|------|------|
| `README.md` | 專案入口 | MVP 範圍、系統組成、快速開始 |
| `RUNBOOK.md` | 維運指南 | 日常檢查、異常排查、VM 配置 |
| `RUNBOOK-DOCTOR.md` | 環境診斷 | 一鍵檢查環境是否正常 |
| `Development.md` | 開發指南 | Sprint prompts、PR 檢查清單、硬隔離規則 |
| `ARCHITECTURE.md` | 架構文件 | 微服務邊界、資料流、Strategy Engine 架構 |
| `API_CONTRACTS.md` | API 契約 | 所有端點的 Request/Response Schema |
| `Strategy.md` | 策略邏輯 | Radar v1.4 規則、帳務層/估值層邊界 |
| `DEPLOYMENT.md` | 部署計畫 | VM 設置、GitHub Actions、systemd |
| `SECURITY.md` | 安全規範 | 金鑰管理、Google SA 配置 |
| `TESTING.md` | 測試策略 | 前後端測試指令、CI 建議 |
| `CHANGELOG.md` | 版本沿革 | 歷史變更記錄 |

---

### 移動至 docs/ 的文件 (29 個)

#### docs/sprints/ - Sprint 文件 (12 個)

| 原檔名 | 新位置 | 說明 |
|--------|--------|------|
| `SPRINT_1-4_STATUS.md` | `docs/sprints/sprint-1-4-status.md` | Sprint 1-4 狀態總覽 |
| `SPRINT_1-4-2_VERIFICATION.md` | `docs/sprints/sprint-1-4-2-verification.md` | 驗證報告 |
| `SPRINT_1-4-3_ACCEPTANCE_REPORT.md` | `docs/sprints/sprint-1-4-3-acceptance-report.md` | 驗收報告 |
| `SPRINT_NEXT_ACCEPTANCE_REPORT.md` | `docs/sprints/sprint-next-acceptance-report.md` | 下一 Sprint 驗收 |
| `SPRINT_1-4-A_ACCEPTANCE_REPORT.md` | `docs/sprints/sprint-1-4-a/acceptance-report.md` | 1-4.A 驗收 |
| `SPRINT_1-4-A_HARDENING_COMPLETE.md` | `docs/sprints/sprint-1-4-a/hardening-complete.md` | 1-4.A 加固完成 |
| `SPRINT_1-4-A_PR_SUMMARY.md` | `docs/sprints/sprint-1-4-a/pr-summary.md` | 1-4.A PR 摘要 |
| `SPRINT_1-4-A_README.md` | `docs/sprints/sprint-1-4-a/readme.md` | 1-4.A 說明 |
| `SPRINT_1-4-A_DOCS_PATCH.md` | `docs/sprints/sprint-1-4-a/docs-patch.md` | 1-4.A 文件補丁 |
| `SPRINT_1-4-B_IMPLEMENTATION.md` | `docs/sprints/sprint-1-4-b/implementation.md` | 1-4.B 實作報告 |
| `SPRINT_1-4-B_DELIVERY.md` | `docs/sprints/sprint-1-4-b/delivery.md` | 1-4.B 交付報告 |
| `SPRINT_1-4-B_VERIFICATION_STATUS.md` | `docs/sprints/sprint-1-4-b/verification-status.md` | 1-4.B 驗證狀態 |
| `SPRINT_1-4-B_PR_DESCRIPTION.md` | `docs/sprints/sprint-1-4-b/pr-description.md` | 1-4.B PR 描述 |
| `SPRINT_1-4-C_ACCEPTANCE_REPORT.md` | `docs/sprints/sprint-1-4-c/acceptance-report.md` | 1-4.C 驗收 |
| `SPRINT_1-4-C_IMPLEMENTATION_STATUS.md` | `docs/sprints/sprint-1-4-c/implementation-status.md` | 1-4.C 實作狀態 |

#### docs/reports/ - 技術報告 (5 個)

| 原檔名 | 新位置 | 說明 |
|--------|--------|------|
| `TRANSACTION_AUDIT_REPORT.md` | `docs/reports/transaction-audit.md` | 交易稽核報告 |
| `PORTFOLIO_HARDENING_REPORT.md` | `docs/reports/portfolio-hardening.md` | Portfolio 加固報告 |
| `P0_P1_IMPLEMENTATION_REPORT.md` | `docs/reports/p0-p1-implementation.md` | P0/P1 修復報告 |
| `SHORT_SELLING_BUG_DIAGNOSIS.md` | `docs/reports/short-selling-diagnosis.md` | 賣空 Bug 診斷 |
| `VERIFICATION_REPORT_2026-01-24.md` | `docs/reports/verification-2026-01-24.md` | 驗證報告 |

#### docs/runbook/ - RUNBOOK 補充 (4 個)

| 原檔名 | 新位置 | 說明 |
|--------|--------|------|
| `RUNBOOK_ACCEPTANCE_COMMANDS.md` | `docs/runbook/acceptance-commands.md` | 驗收命令集 |
| `RUNBOOK_HARDENING_CHECKLIST.md` | `docs/runbook/hardening-checklist.md` | 加固檢查清單 |
| `RUNBOOK_HARDENING_SUMMARY.md` | `docs/runbook/hardening-summary.md` | 加固摘要 |
| `RUNBOOK_UPDATE_PLAN.md` | `docs/runbook/update-plan.md` | 更新計畫 |

#### docs/patches/ - PR/Patch 歷史 (5 個)

| 原檔名 | 新位置 | 說明 |
|--------|--------|------|
| `API_GATEWAY_PROXY_IMPLEMENTATION.md` | `docs/patches/api-gateway-proxy.md` | API Gateway 代理實作 |
| `PR_DESCRIPTION_pr_check_enhancements.md` | `docs/patches/pr-check-enhancements.md` | PR Check 增強 |
| `DOCS_UPDATE_SUMMARY.md` | `docs/patches/docs-update-summary.md` | 文件更新摘要 |
| `STRATEGY_MD_PATCH.md` | `docs/patches/strategy-patch.md` | Strategy 補丁 |
| `DEVELOPMENT_MD_PATCH.md` | `docs/patches/development-patch.md` | Development 補丁 |

---

## 二、最終目錄結構

```
Smart-Investment-stretegy/
│
├── README.md
├── RUNBOOK.md
├── RUNBOOK-DOCTOR.md
├── Development.md
├── ARCHITECTURE.md
├── API_CONTRACTS.md
├── Strategy.md
├── DEPLOYMENT.md
├── SECURITY.md
├── TESTING.md
├── CHANGELOG.md
│
├── docs/
│   ├── README.md                    # 文件索引
│   ├── ci-gate.md
│   │
│   ├── sprints/
│   │   ├── sprint-2.md
│   │   ├── sprint-1-4-status.md
│   │   ├── sprint-1-4-2-verification.md
│   │   ├── sprint-1-4-3-acceptance-report.md
│   │   ├── sprint-next-acceptance-report.md
│   │   │
│   │   ├── sprint-1-4-a/
│   │   │   ├── acceptance-report.md
│   │   │   ├── hardening-complete.md
│   │   │   ├── pr-summary.md
│   │   │   ├── readme.md
│   │   │   └── docs-patch.md
│   │   │
│   │   ├── sprint-1-4-b/
│   │   │   ├── implementation.md
│   │   │   ├── delivery.md
│   │   │   ├── verification-status.md
│   │   │   └── pr-description.md
│   │   │
│   │   └── sprint-1-4-c/
│   │       ├── acceptance-report.md
│   │       └── implementation-status.md
│   │
│   ├── reports/
│   │   ├── transaction-audit.md
│   │   ├── portfolio-hardening.md
│   │   ├── p0-p1-implementation.md
│   │   ├── short-selling-diagnosis.md
│   │   └── verification-2026-01-24.md
│   │
│   ├── runbook/
│   │   ├── acceptance-commands.md
│   │   ├── hardening-checklist.md
│   │   ├── hardening-summary.md
│   │   └── update-plan.md
│   │
│   └── patches/
│       ├── api-gateway-proxy.md
│       ├── pr-check-enhancements.md
│       ├── docs-update-summary.md
│       ├── strategy-patch.md
│       └── development-patch.md
│
├── services/
│   ├── api-gateway/
│   ├── portfolio-service/
│   │   └── README.md
│   ├── valuation-service/
│   ├── radar-service/
│   └── indicator-service/
│
└── tools/
```

---

## 三、功能完成狀態

### ✅ 已完成功能

| Sprint | 服務 | 功能 | 驗收檔案 |
|--------|------|------|----------|
| Sprint 1 | portfolio-service | 均價法計算 (`avg_cost_calculator.py`) | `tools/verify_sprint_1-4-b.sh` |
| Sprint 1 | portfolio-service | trades/positions 資料庫 Schema | Alembic migration |
| Sprint 1 | portfolio-service | Google Sheets 同步 (`POST /portfolio/sync`) | - |
| Sprint 1 | portfolio-service | 持倉重算 (`POST /portfolio/rebuild_positions`) | - |
| Sprint 1-4.A | portfolio-service | FX 模組介面 + Stub (`app/fx/`) | 20 個測試通過 |
| Sprint 1-4.3 | portfolio-service | positions 表寫回 | - |
| Sprint 1-4.B | valuation-service | 估值層骨架 (`GET /valuation/portfolio`) | - |
| Sprint 1-4.B | valuation-service | Runtime Guard (`guardrails.py`) | - |
| Sprint 1-4.B | valuation-service | Price/FX Stub Providers | - |
| Sprint 2 | radar-service | Strategy Engine 可插拔架構 (`strategy_engine/`) | `tools/verify_sprint_2.sh` |
| Sprint 2 | radar-service | v1.4 Plugin (EDS 計分制) (`plugins/v1_4/`) | - |
| Sprint 2 | radar-service | `GET /radar/decision` 端點 | - |
| Sprint 2 | indicator-service | Sector Rotation 指標 (`GET /indicators/sector-rotation`) | - |
| CI/CD | - | CI Gate (GitHub Actions) | `.github/workflows/ci.yml` |
| 基礎設施 | api-gateway | 反向代理實作 | - |

### 實作驗證結果

| 元件 | 檔案 | 狀態 |
|------|------|------|
| Strategy Engine | `schemas.py` | ✅ InputSchema + OutputSchema 已定義 |
| Strategy Engine | `plugins/v1_4/rules.py` | ✅ 模式計分 + 決策邏輯 |
| Strategy Engine | `plugins/v1_4/plugin.py` | ✅ V1_4Plugin 類別 |
| Portfolio Service | `position_rebuilder.py` | ✅ 重算 + 預覽邏輯 |
| Portfolio Service | `avg_cost_calculator.py` | ✅ 加權平均成本計算 |
| Portfolio Service | `fx/interfaces.py` | ✅ FxProvider 抽象介面 |
| Portfolio Service | `fx/stub_provider.py` | ✅ Stub FX 實作 |
| Valuation Service | `guardrails.py` | ✅ DB 環境變數阻斷 + evidence |
| Valuation Service | `providers.py` | ✅ 抽象 + stub providers |
| Indicator Service | `main.py` | ✅ `/indicators/sector-rotation` 端點 |

---

### ⏸ 暫停/待實作功能

| 功能 | 狀態 | 說明 |
|------|------|------|
| 真實匯率 Provider (Yahoo Finance/央行) | ⏸ 暫停 | 等估值層穩定後再開工 |
| 匯率 Cache (Redis/DB) | ⏸ 暫停 | 同上 |
| 真實市價 Provider | ⏸ 暫停 | 同上 |
| `u_pnl` 真實計算 | ⏸ 暫停 | 當前固定為 0 |
| 新聞/研究訊號整合 | ❌ 未開始 | Sprint 2 明確標示不做 |
| JWT 驗證 | ❌ 未開始 | README 標示 TODO |
| 掃描型 PDF OCR | ❌ Out of Scope | MVP 不做 |

---

### P2 待辦事項（從報告中彙整）

| 項目 | 來源 |
|------|------|
| 新增單元測試 `test_fail_fast_validation.py` | P0/P1 報告 |
| 新增 API 文件（說明 evidence 欄位） | P0/P1 報告 |
| 評估是否在 sync 階段也加入驗證 | P0/P1 報告 |
| 監控 Fail Fast 觸發頻率（Prometheus metrics） | P0/P1 報告 |

---

## 四、API 端點清單

### portfolio-service (Port 8001)

| 方法 | 端點 | 說明 |
|------|------|------|
| GET | `/health` | 健康檢查 |
| POST | `/portfolio/sync` | 從 Google Sheets 同步交易 |
| GET | `/portfolio/positions` | 取得持倉快照 |
| GET | `/portfolio/trades/summary` | 取得交易摘要 |
| POST | `/portfolio/rebuild_positions` | 重算持倉 |

### valuation-service (Port 8005)

| 方法 | 端點 | 說明 |
|------|------|------|
| GET | `/health` | 健康檢查 |
| GET | `/valuation/portfolio` | 取得估值（含 evidence） |

### radar-service (Port 8003)

| 方法 | 端點 | 說明 |
|------|------|------|
| GET | `/health` | 健康檢查 |
| GET | `/radar/decision` | 取得策略決策建議 |
| GET | `/plugins` | 列出可用 plugins |

### indicator-service (Port 8004)

| 方法 | 端點 | 說明 |
|------|------|------|
| GET | `/health` | 健康檢查 |
| GET | `/indicators/sector-rotation` | XLU/XLK 指標 |
| GET | `/indicators/providers` | 列出可用 providers |

---

**報告結束**
