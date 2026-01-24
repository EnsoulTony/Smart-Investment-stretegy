"""FX 匯率折算模組（Factory & Public API）

此模組是全專案匯率查詢與轉換的唯一入口。

⚠️ 硬禁止規則（Hard Rules）：
1. 除 app/fx/* 以外，禁止任何模組直接讀取 FX_* / VALUATION_* 等估值相關環境變數
2. 除 app/fx/* 以外，禁止任何模組直接 import 匯率 provider 實作
3. 全專案匯率與估值唯一入口：app.fx.get_fx_provider()
4. 違規 PR 直接退回

使用範例：
    ```python
    from app.fx import get_fx_provider
    from decimal import Decimal
    
    fx = get_fx_provider()
    
    # 查詢匯率
    rate = fx.get_rate('USD', 'TWD')
    
    # 轉換金額
    twd_amount = fx.convert(Decimal('100'), 'USD', 'TWD')
    ```
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
    """取得 FX Provider 實例（單例模式）
    
    根據環境變數 FX_PROVIDER 決定使用哪個實作：
    - 'stub' (預設)：StubFxProvider（僅支援同幣別，嚴格模式）
    - 'yahoo'：Yahoo Finance Provider（未來實作）
    - 'central_bank'：央行牌告匯率 Provider（未來實作）
    
    Returns:
        FxProvider 實例
        
    Raises:
        ValueError: 不支援的 FX_PROVIDER 設定
    
    Example:
        >>> fx = get_fx_provider()
        >>> fx.source()
        'stub'
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
    """重置 FX Provider 單例（僅供測試使用）
    
    ⚠️ 警告：此函數僅供單元測試使用，生產環境不得呼叫。
    """
    global _fx_provider_instance
    _fx_provider_instance = None
