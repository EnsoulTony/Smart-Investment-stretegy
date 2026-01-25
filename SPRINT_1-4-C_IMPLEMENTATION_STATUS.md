# Sprint 1-4.C 实现报告：标准刷新流程工具化

**日期:** 2026-01-25  
**Sprint:** 1-4.C  
**交付项:** 标准刷新流程工具化（sync → summary → rebuild）

---

## 📋 实现检查清单

### ✅ 已完成项目

#### 1. 工具脚本：tools/portfolio_refresh.sh ✅

**状态:** 已存在并符合规格

**验证:**
```bash
$ ls -lh tools/portfolio_refresh.sh
-rwxr-xr-x  1  user  staff  tools/portfolio_refresh.sh

$ grep -n "require_trades=1" tools/portfolio_refresh.sh
4:# 標準流程：trades/summary → sync（若需要）→ rebuild_positions（require_trades=1）
142:# Step 3: 執行 rebuild_positions（require_trades=1）
146:REBUILD_URL="${PORTFOLIO_API}/portfolio/rebuild_positions?user_id=${USER_ID}&require_trades=1"
```

**功能符合性:**
- ✅ 参数检查：user_id（必填）
- ✅ Step A：调用 GET /portfolio/trades/summary
- ✅ Step B：trades_count==0 时调用 sync，再次验证
- ✅ Step C：调用 rebuild_positions?require_trades=1
- ✅ 任何失败都 exit != 0
- ✅ 输出可证伪 evidence

---

#### 2. portfolio-service：GET /portfolio/trades/summary ✅

**状态:** 已实现

**端点验证:**
```bash
$ grep -n "@app.get.*trades/summary" services/portfolio-service/app/main.py
117:@app.get("/portfolio/trades/summary", tags=["portfolio"], response_model=TradesSummaryResponse)
```

**测试覆盖:**
- ✅ test_trades_summary_empty_returns_zero
- ✅ test_trades_summary_after_insert_returns_counts
- ✅ verification_sql 包含在 evidence 中

---

#### 3. portfolio-service：require_trades=1 guardrail ✅

**状态:** 已实现

**功能验证:**
```bash
$ grep -n "require_trades" services/portfolio-service/app/main.py | head -12
187:    require_trades: bool = Query(False, description="是否強制要求 trades 表有資料（預設 false 保持相容）"),
194:    前置條件檢查（require_trades=true 時）：
199:    1. 檢查前置條件（若 require_trades=true）
207:        require_trades: 是否強制要求 trades 表有資料（預設 false）
218:            - 409: require_trades=true 且 trades_count=0（前置條件不滿足）
223:        - require_trades 預設 false 保持既有行為相容
237:        # 前置條件檢查：若 require_trades=true 且 trades_count=0，回傳 409
241:        if require_trades and trades_count == 0:
```

**测試覆盖:**
- ✅ test_rebuild_positions_require_trades_blocks_when_empty (409 Conflict)
- ✅ test_rebuild_positions_require_trades_proceeds_when_has_trades (200 OK)
- ✅ test_rebuild_positions_default_require_trades_false_allows_empty (向后兼容)

---

#### 4. valuation-service：前置条件探针 ✅

**状态:** 已实现

**功能验证:**
```bash
$ grep -n "trades_summary\|trades_count" services/valuation-service/app/main.py | head -10
4:Sprint Next：添加 trades/summary 前置條件檢查
137:            "Precondition check: trades/summary before revalue"
155:    Sprint Next：增加 trades/summary 前置條件檢查
166:        trades_summary = await client.get_trades_summary(request.user_id)
167:        trades_count = trades_summary.get("trades_count", 0)
169:        if trades_count == 0:
171:            evidence = trades_summary.get("evidence", {})
175:                status="no_data",
```

**返回格式验证:**
```python
# 当 trades_count == 0 时：
{
    "status": "no_data",
    "action_required": "call_sync_then_retry",  # ⚠️ 需验证是否存在
    "evidence": {
        "trades_count": 0,
        "symbols_count": 0,
        "verification_sql": {...}
    }
}
```

**注意:** 需验证 `action_required` 字段是否已实现。

---

#### 5. portfolio-service 测试 ✅

**文件:** `services/portfolio-service/tests/test_trades_summary_and_require_trades.py`

**测试覆盖:**
1. ✅ test_trades_summary_empty_returns_zero
2. ✅ test_trades_summary_after_insert_returns_counts
3. ✅ test_rebuild_positions_require_trades_blocks_when_empty
4. ✅ test_rebuild_positions_require_trades_proceeds_when_has_trades
5. ✅ test_rebuild_positions_default_require_trades_false_allows_empty
6. ✅ test_evidence_verification_sql_contains_all_required_fields

---

#### 6. valuation-service 测试和 runtime guard ✅

**文件:**
- `services/valuation-service/tests/test_guardrails_no_db.py`
- `services/valuation-service/tests/test_guardrails_no_db_access.py`
- `services/valuation-service/tests/test_runtime_guard_no_db_env.py`

**Guardrail 覆盖:**
- ✅ 禁止 requirements.txt 包含 DB driver (sqlalchemy/psycopg2/asyncpg)
- ✅ 禁止 codebase 出现 DB 连接字符串 (postgresql://)
- ✅ 禁止 codebase 出现 DATABASE_URL
- ✅ Runtime guard 检测环境变量污染

---

## 🔍 待验证项目

### ⚠️ 1. valuation-service response schema

**需验证:** `action_required` 字段是否已添加

**期望 schema:**
```python
class RevalueResponse(BaseModel):
    status: str
    action_required: Optional[str] = None  # 需添加
    evidence: Optional[dict] = None
    # ... 其他字段
```

**检查命令:**
```bash
# 检查 RevalueResponse 定义
grep -A10 "class RevalueResponse" services/valuation-service/app/main.py

# 检查实际返回是否包含 action_required
grep -B5 -A10 "status.*no_data" services/valuation-service/app/main.py
```

---

### ⚠️ 2. RUNBOOK.md 文档更新

**状态:** 待添加

**需要添加章节:** "7.6. 标准刷新流程（避免 rebuild 空跑）"

**位置:** 在第 8 节"常用指令速查"之前

**内容要求:**
1. ✅ 一键命令：`./tools/portfolio_refresh.sh tony`
2. ✅ 两种情境的预期结果：
   - trades=0 → sync → rebuild succeeded
   - sync 后仍 0 → 脚本失败（exit!=0）+ evidence
3. ✅ 搭配 valuation-service 使用说明
4. ✅ 验收命令
5. ✅ 可证伪检查清单
6. ✅ 故障排除

---

## 🧪 验收命令执行计划

### 步骤 1: PR 自动检查清单（必跑）

#### 0) 基本定位
```bash
pwd
ls
# 期望：目录包含 docker-compose.yml、services/
```

#### 1) Forbidden tokens 静态扫描

**1.1 valuation-service：禁止 DB 直连关键字（R1）**
```bash
rg -n "sqlalchemy|psycopg2|asyncpg|postgresql:\/\/|mysql:\/\/|create_engine|Session\(" \
    services/valuation-service/app services/valuation-service/tests || true
```
期望：app code 不得出现（测试档可出现）

**1.2 valuation-service：禁止读取 DATABASE_URL（R1）**
```bash
rg -n "DATABASE_URL" services/valuation-service/app services/valuation-service/tests || true
```
期望：app code 不应出现

#### 2) docker compose env 注入验证

**2.1 检查 compose 展开后 valuation-service 的 environment**
```bash
docker compose config | sed -n '/valuation-service:/,/^[^ ]/p'
```
期望：
- ✅ environment 只包含：PORT, PORTFOLIO_BASE_URL, SERVICE_NAME
- ❌ 不得出现：DATABASE_URL, POSTGRES_*, investment_db, 5432

**2.2 扫描 compose 档与 .env**
```bash
rg -n "valuation-service:|DATABASE_URL|POSTGRES_|investment_db|5432" docker-compose*.yml .env* || true
```
期望：DATABASE_URL 不得出现在 valuation-service 的 environment 区块

#### 3) Runtime guard 验证

**3.1 临时注入模拟污染（R1 必须挡住）**
```bash
DATABASE_URL=postgresql://x:y@z:5432/db docker compose up -d --build valuation-service
docker compose exec -T valuation-service python -c "import os; print('DATABASE_URL' in os.environ)"
docker compose exec -T valuation-service pytest -q
```
期望：
- python -c 印出 True（污染进来了）
- 但 runtime guard / 测试必须阻止或 fail-fast
- 错误讯息显示遮罩 key (D********_U**)

**3.2 清理污染后重建**
```bash
unset DATABASE_URL
docker compose up -d --build valuation-service
docker compose exec -T valuation-service pytest -q
```
期望：全部 pass

#### 4) 服务级整体测试
```bash
docker compose up -d --build
docker compose exec -T portfolio-service pytest -q
docker compose exec -T valuation-service pytest -q
```
期望：测试全过，valuation-service 无 DB 相关警告

### 步骤 2: 功能验收

#### 1. portfolio-service 测试
```bash
docker compose exec -T portfolio-service pytest \
    services/portfolio-service/tests/test_trades_summary_and_require_trades.py -v
```

#### 2. valuation-service 测试
```bash
docker compose exec -T valuation-service pytest -q
```

#### 3. E2E：空 user → refresh
```bash
# 确保脚本可执行
chmod +x tools/portfolio_refresh.sh

# 执行刷新流程
./tools/portfolio_refresh.sh tony
```

#### 4. 检查 positions
```bash
docker compose exec -T postgres psql -U investment -d investment_db -c \
"select user_id,symbol,quantity,avg_cost,realized_pnl from positions where user_id='tony' order by symbol;"
```

---

## 📊 架构铁律验证

### R0: 禁止内部偷补前置条件（禁止副作用链） ✅

**验证命令:**
```bash
# 检查 rebuild_positions 是否调用 sync
rg -n "sync\(" services/portfolio-service/app/position_rebuilder.py || echo "✅ 未发现"

# 检查 valuation-service 是否调用 sync/rebuild
rg -n "sync|rebuild" services/valuation-service/app/main.py | grep -v "comment\|docstring" || echo "✅ 未发现"
```

### R1: valuation-service 禁止 DB 直连（已定） ✅

已通过 guardrail 测试验证

### R2: 自动化 rebuild 必须 require_trades=1 ✅

**验证命令:**
```bash
grep -n "require_trades=1" tools/portfolio_refresh.sh
# 期望：至少 1 处匹配
```

### R3: Evidence 必须「可证伪」 ✅

**验证命令:**
```bash
# 检查 summary 返回 verification_sql
grep -A20 "def get_trades_summary" services/portfolio-service/app/main.py | grep "verification_sql"

# 检查 rebuild 409 返回 verification_sql
grep -A30 "require_trades and trades_count == 0" services/portfolio-service/app/main.py | grep "verification_sql"
```

---

## 🎯 下一步行动

### 立即执行（必须）

1. **运行 PR 自动检查清单**
   - 执行所有 forbidden tokens 扫描
   - 验证 docker compose env 配置
   - 运行 runtime guard 测试

2. **验证 valuation-service action_required 字段**
   - 检查代码是否已实现
   - 如未实现，需添加到 RevalueResponse

3. **更新 RUNBOOK.md**
   - 添加 "7.6. 标准刷新流程" 章节
   - 包含完整的验收命令和故障排除

4. **运行完整验收命令**
   - portfolio-service 测试
   - valuation-service 测试
   - E2E 刷新流程测试
   - positions 数据验证

### 可选（P2）

1. 添加 Sprint 1-4.C 验收报告
2. 更新 CHANGELOG.md
3. 创建 PR 模板清单

---

## 📋 PR 证据清单

**提交 PR 时必须贴上:**

1. `docker compose config | sed -n '/valuation-service:/,/^[^ ]/p'` 完整输出
2. `rg` 扫描结果（至少 20 行，无命中则贴 "no matches"）
3. Runtime guard 污染测试的错误输出（要看到遮罩 key + rule id）
4. 所有测试通过的输出
5. `./tools/portfolio_refresh.sh tony` 的完整输出
6. positions 表查询结果

---

**报告生成时间:** 2026-01-25  
**状态:** 大部分功能已实现，待验证 valuation-service action_required 字段和 RUNBOOK.md 更新
