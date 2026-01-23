# Portfolio Service

Portfolio Service 負責管理交易流水帳、持倉快照與 Google Sheets 同步。

## 快速驗證

**重要：首次使用需先執行 migration，再執行測試**

```bash
# 方法一：使用一鍵驗證腳本（推薦）
bash services/portfolio-service/verify_setup.sh

# 方法二：手動執行
# 1. 啟動服務
docker compose up -d --build postgres portfolio-service

# 2. 執行 migration（必須先執行！）
docker compose exec portfolio-service alembic upgrade head

# 3. 執行測試
docker compose exec portfolio-service pytest -q

# 4. 檢查表格
docker compose exec postgres psql -U investment -d investment_db -c "\dt"
```

### 常見問題

**Q: 執行 `alembic upgrade head` 時出現 "relation already exists" 錯誤**

A: 表格已存在但 Alembic 未記錄。解決方式：
```bash
# 方案1: 標記當前狀態（推薦，保留資料）
docker compose exec portfolio-service alembic stamp head

# 方案2: 重建資料庫（會清空所有資料）
docker compose exec postgres psql -U investment -d investment_db -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
docker compose exec portfolio-service alembic upgrade head
```

**Q: 測試失敗顯示 "trades 表不存在"**

A: 需要先執行 migration：
```bash
docker compose exec portfolio-service alembic upgrade head
```

**Q: 想要重新開始，清空所有資料**

A: 使用重置腳本（會刪除所有資料！）：
```bash
bash services/portfolio-service/reset_db.sh
```

## 資料庫 Schema

本服務使用 Alembic 管理資料庫 migration，包含三張表：

1. **trades** - 交易流水帳
2. **positions** - 最新持倉快照
3. **sync_runs** - 同步執行記錄

## 執行 Migration

### 方式一：在 Docker 容器內執行

```bash
# 啟動 postgres 與 portfolio-service
docker compose up -d --build postgres portfolio-service

# 執行 migration
docker compose exec portfolio-service alembic upgrade head

# 檢查 migration 狀態
docker compose exec portfolio-service alembic current

# 查看 migration 歷史
docker compose exec portfolio-service alembic history

# 若需進入容器內互動操作
docker compose exec portfolio-service bash
```

### 方式二：本機執行（開發環境）

```bash
cd services/portfolio-service

# 設定資料庫連線
export DATABASE_URL=postgresql://investment:investment@localhost:5432/investment_db

# 執行 migration
alembic upgrade head

# 回滾 migration
alembic downgrade -1

# 建立新的 migration（當 models 有變更時）
alembic revision --autogenerate -m "描述你的變更"
```

## 執行測試

### 測試資料庫 Schema

```bash
# 在 Docker 容器內執行（推薦）
docker compose exec portfolio-service pytest tests/test_db_schema.py -v

# 或執行所有測試
docker compose exec portfolio-service pytest -q

# 或在本機執行（需先設定 DATABASE_URL）
cd services/portfolio-service
export DATABASE_URL=postgresql://investment:investment@localhost:5432/investment_db
pytest tests/test_db_schema.py -v
```

測試涵蓋：
- Migration 成功執行
- 插入 trade 資料
- source_hash 唯一性約束
- positions 的 (user_id, symbol) 唯一性約束
- sync_run 記錄建立

## 手動檢查資料庫

```bash
# 連線到 Postgres（互動模式）
docker compose exec postgres psql -U investment -d investment_db

# 查看所有表格
\dt

# 查看 trades 表結構
\d trades

# 查看 positions 表結構
\d positions

# 查看 sync_runs 表結構
\d sync_runs

# 查看索引
\di

# 離開
\q

# 或快速檢查表格是否存在（單一命令）
docker compose exec postgres psql -U investment -d investment_db -c "\dt"
```

## 開發注意事項

1. **修改 Models 後需建立 Migration**
   ```bash
   alembic revision --autogenerate -m "描述變更"
   ```

2. **測試前需確保 Migration 已執行**
   - 測試會自動建立表格，但建議先執行 `alembic upgrade head`

3. **DATABASE_URL 格式**
   ```
   postgresql://[user]:[password]@[host]:[port]/[database]
   ```

4. **環境變數**
   - `DATABASE_URL`: 資料庫連線字串（必填）
   - `PORT`: 服務端口（預設 8001）
   - `SERVICE_NAME`: 服務名稱（預設 portfolio-service）
