"""交易資料標準化與 hash 計算。

負責將 Google Sheets 的原始資料轉換為標準化的 TradeRecord，
並計算 source_hash 用於去重。
"""

import os
import hashlib
from typing import List, Dict, Tuple, Optional
from decimal import Decimal
from datetime import timezone
from pydantic import ValidationError

from app.schemas import TradeRecord


class TradeNormalizer:
    """交易資料標準化器。
    
    負責：
    1. 欄位 mapping（將 Google Sheets 的欄位名稱對應到標準欄位）
    2. 資料驗證與轉換（透過 Pydantic）
    3. 計算 source_hash（用於去重）
    """
    
    def __init__(self):
        """初始化標準化器。
        
        從環境變數讀取欄位 mapping：
        - SHEET_COL_USER_ID: 使用者 ID 欄位名稱（預設 "user_id"）
        - SHEET_COL_SYMBOL: 股票代碼欄位名稱（預設 "symbol"）
        - SHEET_COL_ASSET_CCY: 資產幣別欄位名稱（預設 "asset_ccy"）
        - SHEET_COL_SIDE: 交易方向欄位名稱（預設 "side"）
        - SHEET_COL_QUANTITY: 數量欄位名稱（預設 "quantity"）
        - SHEET_COL_PRICE: 價格欄位名稱（預設 "price"）
        - SHEET_COL_FEE: 手續費欄位名稱（預設 "fee"）
        - SHEET_COL_TRADE_DATE: 交易日期欄位名稱（預設 "trade_date"）
        - SHEET_COL_BROKER: 券商欄位名稱（預設 "broker"）
        """
        self.column_mapping = {
            "user_id": os.getenv("SHEET_COL_USER_ID", "user_id"),
            "symbol": os.getenv("SHEET_COL_SYMBOL", "symbol"),
            "asset_ccy": os.getenv("SHEET_COL_ASSET_CCY", "asset_ccy"),
            "side": os.getenv("SHEET_COL_SIDE", "side"),
            "quantity": os.getenv("SHEET_COL_QUANTITY", "quantity"),
            "price": os.getenv("SHEET_COL_PRICE", "price"),
            "fee": os.getenv("SHEET_COL_FEE", "fee"),
            "trade_date": os.getenv("SHEET_COL_TRADE_DATE", "trade_date"),
            "broker": os.getenv("SHEET_COL_BROKER", "broker"),
        }
    
    def normalize_row(self, row_dict: Dict[str, str]) -> Tuple[Optional[TradeRecord], Optional[str]]:
        """標準化單一列資料。
        
        Args:
            row_dict: 原始列資料（key 為 Google Sheets 的欄位名稱或 canonical key）
        
        Returns:
            Tuple[Optional[TradeRecord], Optional[str]]:
                - 成功：(TradeRecord, None)
                - 失敗：(None, 錯誤訊息)
        """
        try:
            # 根據 column_mapping 提取資料，支援 fallback 到 canonical key
            mapped_data = {}
            for standard_col, sheet_col in self.column_mapping.items():
                # 優先使用 mapping 欄位，若不存在則嘗試使用 canonical key（測試用）
                if sheet_col in row_dict:
                    mapped_data[standard_col] = row_dict[sheet_col]
                elif standard_col in row_dict:
                    # Fallback: 直接使用 canonical key（例如測試提供的 mock dict）
                    mapped_data[standard_col] = row_dict[standard_col]
                else:
                    return None, f"缺少必要欄位：{sheet_col}（或 {standard_col}）"
            
            # 使用 Pydantic 驗證與轉換
            trade_record = TradeRecord(**mapped_data)
            return trade_record, None
            
        except ValidationError as e:
            # 提取 Pydantic 驗證錯誤訊息
            errors = []
            for err in e.errors():
                field = ".".join(str(x) for x in err["loc"])
                msg = err["msg"]
                errors.append(f"{field}: {msg}")
            return None, f"資料驗證失敗 - {'; '.join(errors)}"
        except Exception as e:
            return None, f"處理失敗：{str(e)}"
    
    def normalize_rows(
        self, 
        rows_dicts: List[Dict[str, str]]
    ) -> Tuple[List[TradeRecord], List[Dict[str, str]]]:
        """批次標準化多列資料。
        
        Args:
            rows_dicts: 多列原始資料
        
        Returns:
            Tuple[List[TradeRecord], List[Dict[str, str]]]:
                - 成功的 TradeRecord 列表
                - 失敗的列資料（包含原始資料與錯誤訊息）
        """
        success_records = []
        failed_rows = []
        
        for idx, row_dict in enumerate(rows_dicts, start=1):
            # 跳過空白列（所有值都是空字串）
            if all(not str(v).strip() for v in row_dict.values()):
                continue
            
            # 表頭/空行防呆：檢查關鍵欄位 symbol
            symbol_value = None
            for standard_col, sheet_col in self.column_mapping.items():
                if standard_col == "symbol":
                    symbol_value = row_dict.get(sheet_col) or row_dict.get("symbol")
                    break
            
            # 若 symbol 為空或看起來是表頭（常見表頭詞），直接跳過不計入錯誤
            if not symbol_value or str(symbol_value).strip().upper() in ["", "SYMBOL", "股票代碼", "代碼", "TICKER"]:
                continue
            
            trade_record, error = self.normalize_row(row_dict)
            
            if trade_record:
                success_records.append(trade_record)
            else:
                # 收集關鍵欄位原始資料（處理 None/NaN）
                raw_data_snippet = {}
                key_fields = ["user_id", "symbol", "asset_ccy", "side", "quantity", "price", "fee", "trade_date", "broker"]
                for field in key_fields:
                    sheet_col = self.column_mapping.get(field)
                    value = row_dict.get(sheet_col) or row_dict.get(field)
                    # 處理 None/NaN/空值
                    if value is None or (isinstance(value, float) and str(value).lower() == 'nan'):
                        raw_data_snippet[field] = ""
                    else:
                        # 截斷過長字串（最多 100 字元）
                        raw_data_snippet[field] = str(value)[:100] if value else ""
                
                failed_rows.append({
                    "row_index": idx,
                    "raw_data": raw_data_snippet,
                    "error": error
                })
        
        return success_records, failed_rows
    
    @staticmethod
    def compute_source_hash(trade: TradeRecord) -> str:
        """計算交易記錄的 source_hash。
        
        使用固定的欄位順序與格式，確保相同的交易資料產生相同的 hash。
        
        Hash 計算方式：
        1. 將所有欄位按固定順序串接成 canonical 字串
        2. 使用 SHA-256 計算 hash
        
        Canonical 字串格式：
        user_id|symbol|asset_ccy|side|quantity|price|fee|trade_date|broker
        
        注意事項：
        - Decimal 欄位統一格式化為字串（避免 1.0 vs 1.00 的差異）
        - 日期統一格式化為 ISO 8601（YYYY-MM-DD HH:MM:SS）
        
        Args:
            trade: TradeRecord 物件
        
        Returns:
            str: SHA-256 hash（十六進位字串）
        """
        # 將 Decimal 格式化為固定小數位數的字串
        quantity_str = f"{trade.quantity:.8f}".rstrip('0').rstrip('.')
        price_str = f"{trade.price:.8f}".rstrip('0').rstrip('.')
        fee_str = f"{trade.fee:.8f}".rstrip('0').rstrip('.')
        
        # 日期格式化為 ISO 8601（移除時區資訊以確保 hash 穩定性）
        # 無論 datetime 是否有時區，都統一為 naive 格式進行 hash
        if trade.trade_date.tzinfo is not None:
            # Timezone-aware: 轉換為 UTC 再移除時區資訊
            trade_date_naive = trade.trade_date.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            # Naive datetime: 直接使用
            trade_date_naive = trade.trade_date
        trade_date_str = trade_date_naive.strftime("%Y-%m-%d %H:%M:%S")
        
        # 按固定順序串接（使用 | 分隔）
        canonical = "|".join([
            trade.user_id,
            trade.symbol,
            trade.asset_ccy,
            trade.side,
            quantity_str,
            price_str,
            fee_str,
            trade_date_str,
            trade.broker,
        ])
        
        # 計算 SHA-256 hash
        hash_obj = hashlib.sha256(canonical.encode("utf-8"))
        return hash_obj.hexdigest()
    
    @staticmethod
    def get_canonical_string(trade: TradeRecord) -> str:
        """取得交易記錄的 canonical 字串（用於除錯與驗證）。
        
        Args:
            trade: TradeRecord 物件
        
        Returns:
            str: Canonical 字串
        """
        quantity_str = f"{trade.quantity:.8f}".rstrip('0').rstrip('.')
        price_str = f"{trade.price:.8f}".rstrip('0').rstrip('.')
        fee_str = f"{trade.fee:.8f}".rstrip('0').rstrip('.')
        
        # 日期格式化（與 compute_source_hash 一致）
        if trade.trade_date.tzinfo is not None:
            trade_date_naive = trade.trade_date.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            trade_date_naive = trade.trade_date
        trade_date_str = trade_date_naive.strftime("%Y-%m-%d %H:%M:%S")
        
        return "|".join([
            trade.user_id,
            trade.symbol,
            trade.asset_ccy,
            trade.side,
            quantity_str,
            price_str,
            fee_str,
            trade_date_str,
            trade.broker,
        ])
