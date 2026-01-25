"""Valuation portfolio API tests.

Sprint 1-4.B：測試估值 API 的完整功能
- 409 場景（trades_count=0）
- 200 場景（trades>0，positions 有資料）
- JSON 格式驗證（防止 jq 爆掉）
- Evidence 結構驗證
"""

import json
from datetime import date
from fastapi.testclient import TestClient

import app.main as main


class _StubClient:
    """Stub client：模擬 portfolio-service 回傳有資料"""

    async def get_trades_summary(self, user_id: str):
        return {
            "user_id": user_id,
            "trades_count": 2,
            "symbols_count": 1,
            "evidence": {
                "verification_sql": {
                    "trades_count": f"select count(*) from trades where user_id='{user_id}';",
                    "distinct_symbols": f"select count(distinct symbol) from trades where user_id='{user_id}';",
                }
            },
        }

    async def get_positions(self, user_id: str):
        return [
            {
                "symbol": "AAPL",
                "asset_ccy": "USD",
                "quantity": 10,
                "avg_cost": 100,
            }
        ]


class _StubEmptyTradesClient(_StubClient):
    """Stub client：模擬 portfolio-service 回傳 trades_count=0"""

    async def get_trades_summary(self, user_id: str):
        return {
            "user_id": user_id,
            "trades_count": 0,
            "symbols_count": 0,
            "evidence": {
                "verification_sql": {
                    "trades_count": f"select count(*) from trades where user_id='{user_id}';",
                    "distinct_symbols": f"select count(distinct symbol) from trades where user_id='{user_id}';",
                }
            },
        }


class TestValuationPortfolioSuccess:
    """測試估值 API 成功場景（HTTP 200）"""

    def test_valuation_portfolio_success_status_code(self, monkeypatch):
        """測試：成功時回傳 HTTP 200"""
        monkeypatch.setattr(main, "PortfolioClient", lambda: _StubClient())
        client = TestClient(main.app)

        response = client.get(
            "/valuation/portfolio",
            params={"user_id": "tony", "base_ccy": "USD", "as_of": "2026-01-24"}
        )
        assert response.status_code == 200

    def test_valuation_portfolio_success_content_type(self, monkeypatch):
        """測試：回傳 content-type 必須是 application/json"""
        monkeypatch.setattr(main, "PortfolioClient", lambda: _StubClient())
        client = TestClient(main.app)

        response = client.get(
            "/valuation/portfolio",
            params={"user_id": "tony", "base_ccy": "USD"}
        )
        assert response.status_code == 200
        assert "application/json" in response.headers.get("content-type", "")

    def test_valuation_portfolio_success_is_valid_json(self, monkeypatch):
        """測試：回傳必須是有效 JSON（防 jq 爆）"""
        monkeypatch.setattr(main, "PortfolioClient", lambda: _StubClient())
        client = TestClient(main.app)

        response = client.get(
            "/valuation/portfolio",
            params={"user_id": "tony", "base_ccy": "USD"}
        )
        assert response.status_code == 200

        # 這是關鍵測試：確保 response.text 可以被 json.loads
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError as e:
            raise AssertionError(f"Response is not valid JSON: {e}\nResponse text: {response.text[:500]}")

        assert isinstance(data, dict)

    def test_valuation_portfolio_success_has_status_field(self, monkeypatch):
        """測試：回傳包含 status 欄位"""
        monkeypatch.setattr(main, "PortfolioClient", lambda: _StubClient())
        client = TestClient(main.app)

        response = client.get(
            "/valuation/portfolio",
            params={"user_id": "tony", "base_ccy": "USD"}
        )
        data = response.json()

        assert data["status"] == "succeeded"
        assert data["user_id"] == "tony"
        assert data["base_ccy"] == "USD"

    def test_valuation_portfolio_success_has_totals(self, monkeypatch):
        """測試：回傳包含 totals 欄位"""
        monkeypatch.setattr(main, "PortfolioClient", lambda: _StubClient())
        client = TestClient(main.app)

        response = client.get(
            "/valuation/portfolio",
            params={"user_id": "tony", "base_ccy": "USD"}
        )
        data = response.json()

        assert "totals" in data
        totals = data["totals"]
        assert "market_value" in totals
        assert "cost_value" in totals
        assert "unrealized_pnl" in totals

    def test_valuation_portfolio_success_has_positions(self, monkeypatch):
        """測試：回傳包含 positions 欄位"""
        monkeypatch.setattr(main, "PortfolioClient", lambda: _StubClient())
        client = TestClient(main.app)

        response = client.get(
            "/valuation/portfolio",
            params={"user_id": "tony", "base_ccy": "USD"}
        )
        data = response.json()

        assert "positions" in data
        assert len(data["positions"]) == 1

        pos = data["positions"][0]
        assert pos["symbol"] == "AAPL"
        assert "quantity" in pos
        assert "avg_cost" in pos
        assert "cost_value" in pos
        assert "price" in pos
        assert "price_ccy" in pos
        assert "market_value" in pos
        assert "unrealized_pnl" in pos

    def test_valuation_portfolio_success_has_evidence(self, monkeypatch):
        """測試：回傳包含 evidence 欄位（可證偽）"""
        monkeypatch.setattr(main, "PortfolioClient", lambda: _StubClient())
        client = TestClient(main.app)

        response = client.get(
            "/valuation/portfolio",
            params={"user_id": "tony", "base_ccy": "USD"}
        )
        data = response.json()

        assert "evidence" in data
        evidence = data["evidence"]

        # 必須包含的欄位
        assert evidence["decision"] == "proceed"
        assert "precondition_snapshot" in evidence
        assert "verification" in evidence
        assert "providers" in evidence
        assert "positions_count" in evidence
        assert "positions_hash" in evidence
        assert "masked_env_keys" in evidence

        # precondition_snapshot 欄位
        snapshot = evidence["precondition_snapshot"]
        assert snapshot["trades_count"] == 2
        assert snapshot["distinct_symbols_count"] == 1

        # verification 欄位
        verification = evidence["verification"]
        assert "portfolio_service_endpoints_called" in verification
        assert "trades_summary_sql" in verification
        assert "as_of" in verification

        # providers 欄位
        providers = evidence["providers"]
        assert providers["price_provider"] == "stub"
        assert providers["fx_provider"] == "stub"
        assert "price_provider_version" in providers
        assert "fx_provider_version" in providers

    def test_valuation_portfolio_success_masked_env_keys_no_values(self, monkeypatch):
        """測試：masked_env_keys 不得包含任何 value"""
        monkeypatch.setattr(main, "PortfolioClient", lambda: _StubClient())
        client = TestClient(main.app)

        response = client.get(
            "/valuation/portfolio",
            params={"user_id": "tony", "base_ccy": "USD"}
        )
        data = response.json()

        masked_env_keys = data["evidence"]["masked_env_keys"]

        # 每個 key 都應該是 "KEY=***" 格式
        for item in masked_env_keys:
            assert "=***" in item, f"env key should be masked: {item}"


class TestValuationPortfolioPreconditionFailed:
    """測試估值 API 前置條件失敗場景（HTTP 409）"""

    def test_precondition_failed_status_code(self, monkeypatch):
        """測試：trades_count=0 時回傳 HTTP 409"""
        monkeypatch.setattr(main, "PortfolioClient", lambda: _StubEmptyTradesClient())
        client = TestClient(main.app)

        response = client.get(
            "/valuation/portfolio",
            params={"user_id": "empty_user"}
        )
        assert response.status_code == 409

    def test_precondition_failed_content_type(self, monkeypatch):
        """測試：409 時 content-type 必須是 application/json"""
        monkeypatch.setattr(main, "PortfolioClient", lambda: _StubEmptyTradesClient())
        client = TestClient(main.app)

        response = client.get(
            "/valuation/portfolio",
            params={"user_id": "empty_user"}
        )
        assert response.status_code == 409
        assert "application/json" in response.headers.get("content-type", "")

    def test_precondition_failed_is_valid_json(self, monkeypatch):
        """測試：409 回傳必須是有效 JSON（防 jq 爆）"""
        monkeypatch.setattr(main, "PortfolioClient", lambda: _StubEmptyTradesClient())
        client = TestClient(main.app)

        response = client.get(
            "/valuation/portfolio",
            params={"user_id": "empty_user"}
        )
        assert response.status_code == 409

        # 關鍵測試：確保 response.text 可以被 json.loads
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError as e:
            raise AssertionError(f"Response is not valid JSON: {e}\nResponse text: {response.text[:500]}")

        assert isinstance(data, dict)

    def test_precondition_failed_has_detail(self, monkeypatch):
        """測試：409 包含 detail 欄位"""
        monkeypatch.setattr(main, "PortfolioClient", lambda: _StubEmptyTradesClient())
        client = TestClient(main.app)

        response = client.get(
            "/valuation/portfolio",
            params={"user_id": "empty_user"}
        )
        data = response.json()

        assert "detail" in data
        detail = data["detail"]
        assert detail["status"] == "precondition_failed"
        assert detail["user_id"] == "empty_user"
        assert "trades_count=0" in detail["message"]
        assert "sync" in detail["message"]

    def test_precondition_failed_has_evidence(self, monkeypatch):
        """測試：409 包含 evidence 欄位"""
        monkeypatch.setattr(main, "PortfolioClient", lambda: _StubEmptyTradesClient())
        client = TestClient(main.app)

        response = client.get(
            "/valuation/portfolio",
            params={"user_id": "empty_user"}
        )
        data = response.json()

        evidence = data["detail"]["evidence"]
        assert evidence["decision"] == "blocked_precondition"
        assert evidence["trades_count"] == 0
        assert evidence["distinct_symbols_count"] == 0
        assert "verification_sql" in evidence
        assert "portfolio_service_endpoints_called" in evidence
        assert "masked_env_keys" in evidence

    def test_precondition_failed_verification_sql_contains_required_fields(self, monkeypatch):
        """測試：verification_sql 包含必要的 SQL 語句"""
        monkeypatch.setattr(main, "PortfolioClient", lambda: _StubEmptyTradesClient())
        client = TestClient(main.app)

        response = client.get(
            "/valuation/portfolio",
            params={"user_id": "empty_user"}
        )
        data = response.json()

        verification_sql = data["detail"]["evidence"]["verification_sql"]
        assert "trades_count" in verification_sql
        assert "distinct_symbols" in verification_sql


class TestValuationPortfolioJsonIntegrity:
    """測試 JSON 完整性（防止 jq 爆）"""

    def test_response_can_be_parsed_by_json_loads_success(self, monkeypatch):
        """測試：成功場景的 response.text 可被 json.loads 解析"""
        monkeypatch.setattr(main, "PortfolioClient", lambda: _StubClient())
        client = TestClient(main.app)

        response = client.get(
            "/valuation/portfolio",
            params={"user_id": "tony", "base_ccy": "USD"}
        )

        # 直接用 response.text 測試（模擬 curl 輸出）
        raw_text = response.text
        parsed = json.loads(raw_text)
        assert parsed is not None

    def test_response_can_be_parsed_by_json_loads_409(self, monkeypatch):
        """測試：409 場景的 response.text 可被 json.loads 解析"""
        monkeypatch.setattr(main, "PortfolioClient", lambda: _StubEmptyTradesClient())
        client = TestClient(main.app)

        response = client.get(
            "/valuation/portfolio",
            params={"user_id": "empty_user"}
        )

        # 直接用 response.text 測試（模擬 curl 輸出）
        raw_text = response.text
        parsed = json.loads(raw_text)
        assert parsed is not None

    def test_response_not_dict_repr(self, monkeypatch):
        """測試：回傳不是 dict repr（例如 <Response ...>）"""
        monkeypatch.setattr(main, "PortfolioClient", lambda: _StubClient())
        client = TestClient(main.app)

        response = client.get(
            "/valuation/portfolio",
            params={"user_id": "tony", "base_ccy": "USD"}
        )

        raw_text = response.text
        assert not raw_text.startswith("<")
        assert not raw_text.startswith("Response")
        assert raw_text.startswith("{") or raw_text.startswith("[")
