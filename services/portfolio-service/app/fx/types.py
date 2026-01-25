"""匯率折算模組：類型定義

此檔案定義匯率折算相關的資料類型。
"""
from typing import NewType
from decimal import Decimal

# 幣別代碼型別（ISO 4217）
Currency = NewType('Currency', str)

# 匯率型別（必須使用 Decimal 避免浮點誤差）
ExchangeRate = NewType('ExchangeRate', Decimal)
