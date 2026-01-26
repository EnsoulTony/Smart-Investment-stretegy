## 變更摘要

<!-- 簡述本 PR 的目的與主要變更 -->

-

## 影響範圍（請勾選）

<!-- 勾選本 PR 影響到的服務/模組 -->

- [ ] portfolio-service
- [ ] valuation-service
- [ ] api-gateway / compose / tools
- [ ] docs-only

## 本地驗收（必填，請勾選）

<!--
重要：請在提交 PR 前，在本地執行以下驗收並勾選。
若 CI 判定為 full mode，所有項目都必須勾選，否則 CI 會直接 fail。
若只變更 docs/**/*.md，只需勾選 pr_check.sh。
-->

- [ ] ./tools/pr_check.sh
- [ ] ./tools/verify_sprint_1-4-b.sh
- [ ] pytest (portfolio-service)
- [ ] pytest (valuation-service)

## 回滾方式

<!-- 說明如果此 PR 出問題，如何快速回滾 -->

-

---

> **警告**：若 CI 判定為 full mode，而上述「本地驗收」勾選未完成（未勾），CI 會直接 fail。
>
> **CI Mode 判定規則**：
> - **Full mode**：變更了 `services/portfolio-service/**`、`services/valuation-service/**`、`services/api-gateway/**`、`tools/**`、`dc.sh`、`docker-compose*.yml`、`Dockerfile*`
> - **Light mode**：僅變更 `docs/**` 或 `*.md` 檔案
>
> 詳細說明請參考 [docs/ci-gate.md](../docs/ci-gate.md)
