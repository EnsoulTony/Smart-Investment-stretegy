"""FX 匯率折算模組測試

測試範圍：
1. StubFxProvider 基本行為
2. 同幣別轉換（正常）
3. 跨幣別轉換（拋出 NotImplementedError）
4. Factory 函數正確性
"""
import pytest
from decimal import Decimal
from datetime import date

from app.fx import get_fx_provider, reset_fx_provider
from app.fx.stub_provider import StubFxProvider
from app.fx.interfaces import FxProvider


class TestStubFxProvider:
    """StubFxProvider 測試"""
    
    def test_same_currency_get_rate(self):
        """測試同幣別匯率查詢回傳 1"""
        provider = StubFxProvider()
        rate = provider.get_rate('TWD', 'TWD')
        assert rate == Decimal('1')
    
    def test_same_currency_convert(self):
        """測試同幣別轉換回傳原值"""
        provider = StubFxProvider()
        amount = Decimal('12345.67')
        result = provider.convert(amount, 'USD', 'USD')
        assert result == amount
    
    def test_different_currency_get_rate_raises(self):
        """測試跨幣別匯率查詢拋出 NotImplementedError"""
        provider = StubFxProvider()
        with pytest.raises(NotImplementedError, match="StubFxProvider 不支援跨幣別匯率查詢"):
            provider.get_rate('USD', 'TWD')
    
    def test_different_currency_convert_raises(self):
        """測試跨幣別轉換拋出 NotImplementedError"""
        provider = StubFxProvider()
        with pytest.raises(NotImplementedError, match="StubFxProvider 不支援跨幣別轉換"):
            provider.convert(Decimal('100'), 'USD', 'TWD')
    
    def test_source_returns_stub(self):
        """測試 source() 回傳 'stub'"""
        provider = StubFxProvider()
        assert provider.source() == 'stub'
    
    def test_is_stub_returns_true(self):
        """測試 is_stub() 回傳 True"""
        provider = StubFxProvider()
        assert provider.is_stub() is True
    
    def test_with_asof_date(self):
        """測試帶日期參數的同幣別轉換（應忽略日期）"""
        provider = StubFxProvider()
        amount = Decimal('999.99')
        result = provider.convert(amount, 'EUR', 'EUR', asof_date=date(2025, 1, 1))
        assert result == amount


class TestFxFactory:
    """get_fx_provider() 工廠函數測試"""
    
    def setup_method(self):
        """每個測試前重置單例"""
        reset_fx_provider()
    
    def teardown_method(self):
        """每個測試後重置單例"""
        reset_fx_provider()
    
    def test_default_provider_is_stub(self, monkeypatch):
        """測試預設 provider 為 stub"""
        monkeypatch.delenv('FX_PROVIDER', raising=False)
        provider = get_fx_provider()
        assert isinstance(provider, StubFxProvider)
        assert provider.is_stub() is True
    
    def test_explicit_stub_provider(self, monkeypatch):
        """測試明確設定 FX_PROVIDER=stub"""
        monkeypatch.setenv('FX_PROVIDER', 'stub')
        provider = get_fx_provider()
        assert isinstance(provider, StubFxProvider)
    
    def test_singleton_pattern(self):
        """測試單例模式（同一個實例）"""
        provider1 = get_fx_provider()
        provider2 = get_fx_provider()
        assert provider1 is provider2
    
    def test_unsupported_provider_raises(self, monkeypatch):
        """測試不支援的 provider 拋出 ValueError"""
        monkeypatch.setenv('FX_PROVIDER', 'unsupported_provider')
        with pytest.raises(ValueError, match="不支援的 FX_PROVIDER"):
            get_fx_provider()
    
    def test_interface_compliance(self):
        """測試回傳的 provider 符合 FxProvider 介面"""
        provider = get_fx_provider()
        assert isinstance(provider, FxProvider)
        
        # 確認介面方法存在且可呼叫
        assert hasattr(provider, 'get_rate')
        assert hasattr(provider, 'convert')
        assert hasattr(provider, 'source')
        assert hasattr(provider, 'is_stub')


class TestFxIntegration:
    """整合測試：完整工作流程"""
    
    def setup_method(self):
        reset_fx_provider()
    
    def teardown_method(self):
        reset_fx_provider()
    
    def test_full_workflow_same_currency(self):
        """測試完整工作流程：同幣別"""
        fx = get_fx_provider()
        
        # 查詢匯率
        rate = fx.get_rate('JPY', 'JPY')
        assert rate == Decimal('1')
        
        # 轉換金額
        amount = Decimal('10000.50')
        result = fx.convert(amount, 'JPY', 'JPY')
        assert result == amount
    
    def test_full_workflow_cross_currency_fails(self):
        """測試完整工作流程：跨幣別失敗"""
        fx = get_fx_provider()
        
        # 查詢匯率應失敗
        with pytest.raises(NotImplementedError):
            fx.get_rate('USD', 'TWD')
        
        # 轉換應失敗
        with pytest.raises(NotImplementedError):
            fx.convert(Decimal('100'), 'USD', 'TWD')
