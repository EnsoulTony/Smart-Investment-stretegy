# Sprint 1｜Portfolio + Valuation Guardrails

本文件整合 Sprint 1 的核心交付、驗收與合約重點，並與 Sprint 2 互相對照。

## 範圍與交付

- Portfolio 帳務層：交易同步、持倉重算、均價法
- Rebuild / Preview：hash 一致性與可證偽 evidence
- Valuation guardrails：valuation-service 禁止 DB 直連（HTTP-only）
- FX 模組介面（Stub）與 Guardrails（Sprint 1-4.A）

## 驗收（最短路徑）

```bash
./tools/verify_sprint_1-4-b.sh
./tools/verify_sprint_1-4-a.sh
./tools/test_preview.sh
```

## 合約重點（節錄）

- `POST /portfolio/sync`：同步交易，含可觀測性欄位
- `GET /portfolio/positions`：帳務層結果（`u_pnl` 固定為 0）
- `GET /portfolio/trades/summary`：前置條件探針（evidence + verification_sql）
- `GET /valuation/portfolio`：估值層 API（HTTP-only，禁止 DB）

## Guardrails（不得破壞）

- valuation-service：禁止 DB 直連、禁止 `DATABASE_URL` / `postgresql://`
- portfolio-service：帳務層不做 FX / 市價估值

## 關聯文件

- Sprint 2：`docs/sprints/sprint-2.md`
- 架構邊界：`ARCHITECTURE.md`
- API 合約：`API_CONTRACTS.md`
- 策略規格：`Strategy.md`
