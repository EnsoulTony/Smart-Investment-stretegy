"""匯率折算模組（Factory & Public API）。

此模組是全專案匯率查詢與轉換的唯一入口。

⚠️ 硬禁止規則（Hard Rules）：
1. 除本模組以外，禁止任何模組直接讀取匯率相關環境變數
2. 除本模組以外，禁止任何模組直接 import 匯率 provider 實作
3. 全專案匯率唯一入口：get_fx_provider()
4. 違規 PR 直接退回
"""
import os
from typing import Optional

from .interfaces import FxProvider
from .stub_provider import StubFxProvider

# 暴露公開 API
__all__ = ['get_fx_provider', 'FxProvider']


# 全域單例（lazy initialization）
_fx_provider_instance: Optional[FxProvider] = None


def get_fx_provider() -> FxProvider:
    """取得匯率 Provider 實例（單例模式）
    
    根據環境變數 FX_PROVIDER 決定使用哪個實作：
    - 'stub' (預設)：StubFxProvider（僅支援同幣別，嚴格模式）
    - 'yahoo'：Yahoo Finance Provider（未來實作）
    - 'central_bank'：央行牌告匯率 Provider（未來實作）
    
    Returns:
        FxProvider 實例
        
    Raises:
        ValueError: 不支援的 FX_PROVIDER 設定
    """
    global _fx_provider_instance
    
    if _fx_provider_instance is not None:
        return _fx_provider_instance
    
    # 讀取環境變數（僅在此模組內讀取，對外隱藏）
    provider_name = os.getenv('FX_PROVIDER', 'stub').lower()
    
    if provider_name == 'stub':
        _fx_provider_instance = StubFxProvider()
    else:
        # 未來擴充其他 provider
        raise ValueError(
            f"不支援的 FX_PROVIDER: {provider_name}。"
            f"目前支援：['stub']"
        )
    
    return _fx_provider_instance


def reset_fx_provider() -> None:
    """重置匯率 Provider 單例（僅供測試使用）
    
    ⚠️ 警告：此函數僅供單元測試使用，生產環境不得呼叫。
    """
    global _fx_provider_instance
    _fx_provider_instance = None
