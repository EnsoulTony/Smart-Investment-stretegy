"""Pydantic 資料模型定義。

定義 API 請求/回應的資料結構與驗證規則。
"""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from datetime import date


class TradeRecord(BaseModel):
    """交易記錄資料模型。
    
    用於驗證從 Google Sheets 讀取的交易資料。
    """
    user_id: str = Field(..., min_length=1, description="使用者 ID")
    symbol: str = Field(..., min_length=1, description="股票代碼（例如：AAPL、QQQ）")
    asset_ccy: str = Field(..., min_length=1, description="資產幣別（例如：USD、TWD）")
    side: str = Field(..., description="交易方向：BUY 或 SELL")
    quantity: Decimal = Field(..., description="交易數量（買入為正，賣出為負）")
    price: Decimal = Field(..., gt=0, description="成交價格，必須 > 0")
    fee: Decimal = Field(default=Decimal("0"), ge=0, description="手續費，必須 >= 0")
    trade_date: datetime = Field(..., description="交易日期時間")
    broker: str = Field(..., min_length=1, description="券商名稱（例如：IB、Firstrade）")
    name_zh: Optional[str] = Field(default=None, description="資產中文名稱（由系統查詢）")
    
    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str) -> str:
        """驗證並轉換交易方向。
        
        接受：BUY、SELL、買、賣（不區分大小寫）
        輸出：統一為大寫的 BUY 或 SELL
        
        Args:
            v: 原始的交易方向字串
            
        Returns:
            str: 標準化的交易方向（BUY 或 SELL）
            
        Raises:
            ValueError: 當輸入不是合法的交易方向時
        """
        v_upper = v.strip().upper()
        
        # 中文轉英文
        if v_upper in ["買", "BUY"]:
            return "BUY"
        elif v_upper in ["賣", "SELL"]:
            return "SELL"
        else:
            raise ValueError(f"交易方向必須是 BUY/SELL 或 買/賣，收到：{v}")
    
    @field_validator("quantity", "price", "fee", mode="before")
    @classmethod
    def validate_decimal(cls, v):
        """將數值轉換為 Decimal（避免浮點數精度問題）。
        
        Args:
            v: 原始數值（可能是 str、int、float）
            
        Returns:
            Decimal: 轉換後的 Decimal 物件
        """
        if isinstance(v, Decimal):
            return v
        if isinstance(v, str):
            # 移除可能的逗號分隔符（例如：1,000.50）
            v = v.replace(",", "")
        return Decimal(str(v))
    
    @field_validator("trade_date", mode="before")
    @classmethod
    def validate_trade_date(cls, v):
        """解析交易日期。
        
        支援格式：
        - YYYY-MM-DD（例如：2026-01-20）
        - YYYY-MM-DD HH:MM:SS（例如：2026-01-20 09:30:00）
        - ISO 8601 格式（例如：2026-01-20T09:30:00）
        
        Args:
            v: 原始日期字串或 datetime 物件
            
        Returns:
            datetime: 解析後的 datetime 物件
            
        Raises:
            ValueError: 當日期格式無法解析時
        """
        if isinstance(v, datetime):
            return v
        
        if isinstance(v, str):
            v = v.strip()
            
            # 嘗試多種日期格式
            formats = [
                "%Y-%m-%d",           # 2026-01-20
                "%Y-%m-%d %H:%M:%S",  # 2026-01-20 09:30:00
                "%Y-%m-%d %H:%M",     # 2026-01-20 09:30
                "%Y/%m/%d",           # 2026/01/20
                "%Y/%m/%d %H:%M:%S",  # 2026/01/20 09:30:00
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(v, fmt)
                except ValueError:
                    continue
            
            # 嘗試 ISO 8601 格式
            try:
                return datetime.fromisoformat(v)
            except ValueError:
                pass
            
            raise ValueError(f"無法解析日期格式：{v}，支援格式：YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS")
        
        raise ValueError(f"trade_date 必須是字串或 datetime，收到：{type(v)}")


class CoreHolding(BaseModel):
    """核心持股設定。"""

    model_config = ConfigDict(extra="ignore")

    user_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    is_core: bool = Field(default=True)
    
    # Pydantic V2 配置（使用 model_config 取代 class Config）
    model_config = ConfigDict(
        # 允許使用 Decimal（SQLAlchemy Numeric 欄位會回傳 Decimal）
        arbitrary_types_allowed=True,
        # Pydantic V2: json_encoders 已棄用，Decimal 會自動序列化為 float
    )


class RebuildPositionsRequest(BaseModel):
    """持倉重算請求資料模型。
    
    用於 POST /portfolio/rebuild_positions 端點。
    """
    user_id: str = Field(..., min_length=1, description="使用者 ID，不可為空")


class RebuildPositionsResponse(BaseModel):
    """持倉重算回應（Sprint 1-4.3）。"""
    status: str = Field(..., description="執行狀態：succeeded 或 failed")
    user_id: str = Field(..., description="使用者 ID")
    symbols_count: int = Field(..., ge=0, description="受影響的標的數量")
    upserted_count: int = Field(..., ge=0, description="寫入/更新的筆數")
    deleted_or_zeroed_count: int = Field(..., ge=0, description="刪除或歸零的筆數")
    run_id: str = Field(..., description="本次執行識別碼")
    positions_hash: Optional[str] = Field(None, description="持倉狀態的 SHA256 Hash")
    evidence: dict = Field(..., description="可證偽的結構化證據")


class PositionItem(BaseModel):
    """持倉查詢項目（帳務層只讀）。
    
    限制：
    - 僅包含帳務欄位（symbol, asset_ccy, quantity, avg_cost, realized_pnl, cost_basis）
    - cost_basis = quantity * avg_cost
    """
    symbol: str = Field(..., description="股票代碼")
    asset_ccy: str = Field(..., description="資產幣別（原始交易幣別）")
    quantity: Decimal = Field(..., description="持倉數量")
    avg_cost: Decimal = Field(..., description="均價（會計成本）")
    realized_pnl: Decimal = Field(..., description="已實現損益")
    cost_basis: Decimal = Field(..., description="成本基礎（quantity * avg_cost）")
    name_zh: Optional[str] = Field(default=None, description="資產中文名稱（交易來源）")
    
    model_config = ConfigDict(from_attributes=True)


class PositionsResponse(BaseModel):
    """持倉查詢回應（帳務層只讀 API）。"""
    user_id: str
    asof: Optional[str] = None
    items: List[PositionItem]
    next_cursor: Optional[str] = None


class TradesSummaryResponse(BaseModel):
    """交易記錄摘要回應（輕量級探針端點）。
    
    用途：
    - 提供輕量級探針端點，讓其他服務或腳本先確認前置條件
    - 不回傳完整交易記錄，只回傳統計資訊
    - 可證偽：提供 verification_sql 讓使用者驗證
    
    使用場景：
    - automation 腳本在呼叫 rebuild_positions 前先確認是否有交易記錄
    - 下游服務確認 portfolio-service 的資料範圍
    - 診斷工具（確認 sync 是否成功）
    """
    user_id: str = Field(..., description="使用者 ID")
    trades_count: int = Field(..., ge=0, description="交易記錄總筆數")
    symbols_count: int = Field(..., ge=0, description="不重複標的數量")
    min_trade_date: Optional[str] = Field(None, description="最早交易日期（YYYY-MM-DD）")
    max_trade_date: Optional[str] = Field(None, description="最晚交易日期（YYYY-MM-DD）")
    evidence: dict = Field(..., description="可證偽證據（包含 verification_sql）")
    
    model_config = ConfigDict(from_attributes=True)


class SymbolMappingItem(BaseModel):
    symbol: str
    market: str
    name_zh: str
    source: str
    updated_at: Optional[str] = None


class SymbolMappingsResponse(BaseModel):
    items: List[SymbolMappingItem]


class SymbolMappingUpsertRequest(BaseModel):
    symbol: str = Field(..., min_length=1)
    market: str = Field(..., min_length=1)
    name_zh: str = Field(..., min_length=1)
    source: Optional[str] = "manual"


class SymbolMappingResolveRequest(BaseModel):
    symbol: str = Field(..., min_length=1)
    asset_ccy: Optional[str] = None
    market: Optional[str] = None


class OutcomeUpsertRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    as_of: date
    plugin: str = Field(..., min_length=1)
    decision_inputs_hash: str = Field(..., min_length=1)
    outcome_label: str = Field(..., min_length=1)
    outcome_note: Optional[str] = None
    horizon: Optional[str] = "D1"


class OutcomeItem(BaseModel):
    user_id: str
    as_of: str
    plugin: str
    decision_inputs_hash: str
    outcome_label: str
    outcome_note: Optional[str] = None
    labeled_at: Optional[str] = None
    horizon: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class OutcomeListResponse(BaseModel):
    items: List[OutcomeItem]
