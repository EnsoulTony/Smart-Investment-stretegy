# Sprint 2：Strategy Engine（可插拔）+ v1.4 Plugin（EDS）+ indicator-service

## 目標（Goals）

Sprint 2 聚焦於建立可插拔的策略引擎與市場指標服務：

| 項目 | 說明 |
| --- | --- |
| **Strategy Engine** | 位於 `radar-service/app/strategy_engine/`，支援 plugin 架構 |
| **v1.4 Plugin（EDS）** | 第一個實作，基於 XLU/XLK sector rotation 的計分制模式判定 |
| **indicator-service** | 新服務（port 8006），提供 XLU/XLK 指標（close, MA20, MA50, ratio, slope5） |
| **radar decision endpoint** | `GET /radar/decision` 整合 portfolio + indicators 產出建議 |

---

## Implementation Summary

### New Files Created

#### Strategy Engine (`radar-service/app/strategy_engine/`)

| 檔案 | 說明 |
| --- | --- |
| `__init__.py` | Module exports |
| `schemas.py` | 固定 Input/Output Pydantic schemas |
| `engine.py` | Plugin loader and executor |
| `plugins/__init__.py` | Plugins package |
| `plugins/v1_4/__init__.py` | v1.4 plugin exports |
| `plugins/v1_4/rules.py` | 計分規則、factor groups、exposure calculation |
| `plugins/v1_4/plugin.py` | v1.4 EDS plugin 實作 |

#### Indicator Service (`services/indicator-service/`)

| 檔案 | 說明 |
| --- | --- |
| `Dockerfile` | 容器設定 |
| `requirements.txt` | 依賴（pydantic） |
| `app/__init__.py` | Package init |
| `app/main.py` | FastAPI app with `/indicators/sector-rotation` |
| `app/schemas.py` | Response schemas |
| `app/providers/__init__.py` | Providers package |
| `app/providers/stub.py` | Stub provider（risk_on/risk_off/default scenarios） |
| `tests/test_health.py` | Health endpoint test |
| `tests/test_sector_rotation_contract.py` | Contract tests |
| `tests/test_stub_provider.py` | Stub reproducibility tests |

#### Radar Service Tests

| 檔案 | 說明 |
| --- | --- |
| `tests/test_strategy_engine_contract.py` | Input/Output schema validation |
| `tests/test_v1_4_minimal_rules.py` | 固定 indicator 測試 Case A/B/C |
| `tests/test_radar_decision_endpoint.py` | Mocked upstream 測試 |

#### Verification Script

| 檔案 | 說明 |
| --- | --- |
| `tools/verify_sprint_2.sh` | 自動化驗收腳本 |

### Modified Files

| 檔案 | 變更 |
| --- | --- |
| `services/radar-service/app/main.py` | 新增 `/radar/decision` endpoint |
| `services/radar-service/requirements.txt` | 新增 pydantic |
| `docker-compose.yml` | 新增 indicator-service，更新 radar-service 依賴 |

---

## API Contracts

### 1. `GET /indicators/sector-rotation`

**Request**
```
GET /indicators/sector-rotation?symbols=XLU,XLK&as_of=2025-01-20
```

**Response 200 OK**
```json
{
  "as_of": "2025-01-20",
  "version": "0.1",
  "source": "stub",
  "XLU": { "close": 72.0, "ma20": 71.5, "ma50": 71.0 },
  "XLK": { "close": 220.0, "ma20": 218.0, "ma50": 215.0 },
  "ratio": {
    "pair": "XLK/XLU",
    "value": 3.055,
    "ma20": 3.050,
    "ma50": 3.028,
    "slope5": 0.002,
    "value_5d_ago": 3.045
  }
}
```

**Error Codes**

| 狀態碼 | 說明 | Payload |
| --- | --- | --- |
| 422 | 缺少必要 symbols 或日期格式錯誤 | `{ "detail": { "status": "invalid_request", "missing_fields": [...] } }` |
| 503 | Provider 不可用或資料不完整 | `{ "detail": { "status": "provider_error", "message": "..." } }` |

---

### 2. `GET /radar/decision`

**Request**
```
GET /radar/decision?user_id=tony&base_ccy=TWD&plugin=v1.4
```

**Response 200 OK（OutputSchema）**
```json
{
  "schema_version": "1.0",
  "as_of": "2025-01-20",
  "user_id": "tony",
  "mode": "RISK_ON",
  "decision": "NO_ACTION",
  "actions": [
    {
      "symbol": "TSLA",
      "action": "HOLD",
      "reason": "mode=RISK_ON, exposure within limits",
      "constraints": { "cooldown_days": 5, "max_position_pct": 0.45 },
      "falsifiable_triggers": [
        { "type": "indicator", "name": "XLK/XLU", "condition": "cross_below_ma50", "value": 3.028 },
        { "type": "indicator", "name": "ratio.slope5", "condition": "sign_flip_to_negative", "value": 0.002 }
      ]
    }
  ],
  "evidence": {
    "engine": "strategy_engine",
    "plugin": "v1.4",
    "inputs_hash": "a1b2c3d4e5f6...",
    "notes": ["mode=RISK_ON with balanced exposure"],
    "scoring_detail": { "score_on": 5, "score_off": 0, "rules": {...}, "exposure": {...} }
  }
}
```

**Error Codes**

| 狀態碼 | 說明 | Payload |
| --- | --- | --- |
| 422 | 無效參數（日期格式、plugin 不存在） | `{ "detail": { "status": "invalid_request", "message": "..." } }` |
| 502 | 上游服務錯誤（portfolio/indicator） | `{ "detail": { "status": "upstream_error", "service": "...", "message": "..." } }` |
| 503 | 缺少必要資料（indicators 欄位缺失） | `{ "detail": { "status": "missing_data", "missing_fields": [...] } }` |

---

## v1.4 Plugin 規則（EDS）

### Mode 計分制

**Risk-on 加分（每條 +1）**
- ON1: `ratio.value > ratio.ma50`
- ON2: `ratio.ma20 > ratio.ma50`
- ON3: `ratio.slope5 > 0`
- ON4: `XLK.close > XLK.ma50`
- ON5: `XLU.close < XLU.ma50`

**Risk-off 加分（每條 +1）**
- OFF1: `ratio.value < ratio.ma50`
- OFF2: `ratio.ma20 < ratio.ma50`
- OFF3: `ratio.slope5 < 0`
- OFF4: `XLU.close > XLU.ma50`
- OFF5: `XLK.close < XLK.ma50`

**Mode 判定**
- `score_on >= 4` 且 `score_on - score_off >= 2` → **RISK_ON**
- `score_off >= 4` 且 `score_off - score_on >= 2` → **RISK_OFF**
- 其他 → **TRANSITION**

### Decision 判定

| Mode | 條件 | Decision |
| --- | --- | --- |
| TRANSITION | - | WATCHLIST |
| RISK_ON | defensive > 60% | REBALANCE |
| RISK_ON | 其他 | NO_ACTION |
| RISK_OFF | growth_tech > 45% | REDUCE_RISK |
| RISK_OFF | 其他 | NO_ACTION |

### Factor Groups（硬編碼）

| Group | Symbols | 上限 |
| --- | --- | --- |
| defensive | XLU, TLT, IEF, 00687B, 00953B, 00965, 009805, 00983A, 00984A, 00988A | 60% |
| growth_tech | TSLA, TSM, QQQ, ARKK, ARKQ, 0050, 0052, 6789 | 45% |
| energy | OXY, XLE, URA, CCJ, MP | 45% |
| other | (default) | 40% |

---

## How to Verify

### 自動化驗收

```bash
./tools/verify_sprint_2.sh
```

### 手動驗收

```bash
# 1. 啟動服務
./dc.sh up -d --build

# 2. 測試 indicator-service
curl http://localhost:8006/indicators/sector-rotation?symbols=XLU,XLK

# 3. 測試 radar-service
curl "http://localhost:8002/radar/decision?user_id=tony&base_ccy=TWD"

# 4. 容器內跑測試
./dc.sh exec -T indicator-service pytest -q
./dc.sh exec -T radar-service pytest -q
```

---

## Non-Goals（Sprint 2 不做）

- ❌ 新聞/研究訊號整合（只預留 `signals` 欄位）
- ❌ 即時行情（使用 stub provider）
- ❌ 估值層整合（valuation-service 仍禁止 DB 連線）

---

## 與 Sprint 1 的邊界

- **valuation-service 禁止 DB 連線**的 guardrails 維持不變
- **portfolio-service** 不新增指標/行情相關邏輯
- **indicator-service** 為獨立服務，不寫入任何 DB

---

**Sprint 2 更新日期：2026-01-26**

**變更摘要：**
- 建立 Strategy Engine 可插拔架構
- 實作 v1.4 plugin（EDS 計分制模式判定）
- 新增 indicator-service（XLU/XLK sector rotation）
- radar-service 新增 `/radar/decision` endpoint
- 新增驗收腳本 `tools/verify_sprint_2.sh`
