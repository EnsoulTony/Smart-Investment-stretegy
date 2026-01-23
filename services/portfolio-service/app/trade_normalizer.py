"""交易資料標準化與 hash 計算。

負責將 Google Sheets 的原始資料轉換為標準化的 TradeRecord，
並計算 source_hash 用於去重。
"""

import os
import math
import hashlib
from typing import List, Dict, Tuple, Optional
from decimal import Decimal
from datetime import timezone
from pydantic import ValidationError

from app.schemas import TradeRecord


# Hash 版本控制：避免未來 canonical 規則變動造成 hash 衝突
# v1: 初始版本（user_id|symbol|asset_ccy|side|quantity|price|fee|trade_date|broker）
CANONICAL_VERSION = "v1"


def safe_str(v) -> str:
    """安全地將任意值轉換為字串。
    
    處理各種類型：
    - None → ""
    - int → str(v)
    - float (整數值，如 9805.0) → str(int(v))
    - float (NaN) → ""
    - str → 直接 strip
    - 其他 → str(v)
    
    Args:
        v: 任意值
        
    Returns:
        str: 安全轉換後的字串（已 strip）
    """
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, int):
        return str(v).strip()
    if isinstance(v, float):
        if math.isnan(v):
            return ""
        if v.is_integer():
            return str(int(v)).strip()
        return str(v).strip()
    return str(v).strip()


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
        
        # 台股 ETF 白名單（用於判斷要補到幾碼）
        self.tw_etf_prefixes = {
            "0050", "0051", "0052", "0053", "0055", "0056", "0057", "0061",
            "00625", "00631", "00632", "00635", "00636", "00637", "00638", "00639",
            "00642", "00643", "00645", "00646", "00647", "00648", "00650", "00651",
            "00652", "00653", "00654", "00655", "00656", "00657", "00660", "00661",
            "00662", "00663", "00664", "00665", "00668", "00669", "00670", "00671",
            "00672", "00673", "00675", "00676", "00677", "00678", "00679", "00680",
            "00681", "00682", "00683", "00685", "00686", "00687", "00688", "00690",
            "00692", "00693", "00694", "00695", "00696", "00697", "00698", "00699",
            "00700", "00701", "00702", "00703", "00704", "00705", "00706", "00707",
            "00708", "00709", "00710", "00711", "00712", "00713", "00714", "00715",
            "00716", "00717", "00718", "00719", "00720", "00721", "00722", "00723",
            "00724", "00725", "00726", "00727", "00728", "00729", "00730", "00731",
            "00732", "00733", "00734", "00735", "00736", "00737", "00738", "00739",
            "00850", "00851", "00852", "00853", "00854", "00855", "00856", "00857",
            "00878", "00881", "00882", "00883", "00884", "00885", "00886", "00887",
            "00888", "00889", "00891", "00892", "00893", "00894", "00895", "00896",
            "00897", "00900", "00901", "00902", "00903", "00904", "00905", "00906",
            "00907", "00908", "00909", "00910", "00911", "00912", "00913", "00914",
            "00915", "00916", "00917", "00918", "00919", "00920", "00921", "00922",
            "00923", "00927", "00928", "00929", "00930", "00931", "00932", "00933",
            "00934", "00935", "00936", "00937", "00938", "00939", "00940", "00941",
            "00942", "00943", "00944", "00945", "00946", "00947", "00948", "00949",
            "00950", "00951", "00952", "00953", "00954", "00955", "00956", "00957",
            "00958", "00959", "00960", "00961", "00962", "00963", "00964", "00965",
            "00966", "00967", "00968", "00969", "00970", "00971", "00972", "00973",
            "009812",
        }
    
    @staticmethod
    def normalize_tw_symbol(symbol, asset_ccy) -> str:
        """正規化台股代號。
        
        規則：
        - 若 asset_ccy == "TWD" 且 symbol 為純數字：
          - 2位數字 → 補到4位 → xxxx.TW (如 52 → 0052.TW)
          - 3位數字 → 補到5位 → 0xxxx.TW (如 713 → 00713.TW)
          - 4位數字：
            - 若以 9xxx/6xxx 開頭 → 補到5位（常見 ETF，如 9805→00965.TW）
            - 否則保持4位 (如 1519 → 1519.TW)
          - 5位數字 → 直接加 .TW (如 00713 → 00713.TW)
          - 6位數字 → 直接加 .TW (如 009812 → 009812.TW)
        - 若已含字母（如 00983A），直接加 .TW
        - 若已含 .TW，直接返回
        
        Args:
            symbol: 原始股票代號（可能是 str, int, float, None）
            asset_ccy: 資產幣別（可能是 str, int, float, None）
            
        Returns:
            str: 正規化後的股票代號
        """
        # 使用 safe_str 安全轉換
        symbol_str = safe_str(symbol)
        asset_ccy_str = safe_str(asset_ccy)
        
        if not symbol_str:
            return symbol_str
        
        if asset_ccy_str.upper() != "TWD":
            return symbol_str
        
        # 若已含 .TW 或 .TWO，直接返回
        if ".TW" in symbol_str.upper():
            return symbol_str
        
        # 若為純數字，執行補零邏輯
        if symbol_str.isdigit():
            num_len = len(symbol_str)
            if num_len == 2:
                # 2位數字 → 補到4位 (如 52 → 0052)
                symbol_str = symbol_str.zfill(4)
            elif num_len == 3:
                # 3位數字 → 補到5位（ETF，如 713 → 00713）
                symbol_str = symbol_str.zfill(5)
            elif num_len == 4:
                # 4位數字 → 判斷是否需要補到5位
                # 常見 ETF 代號：9xxx (如 9805, 9812), 00xx
                first_digit = symbol_str[0]
                if first_digit == '0':
                    # 以 0 開頭 → 補到5位（如 0052 但實際應該是 00052）
                    symbol_str = symbol_str.zfill(5)
                elif first_digit in ['6', '7', '8', '9']:
                    # 6xxx, 7xxx, 8xxx, 9xxx → 可能是 ETF，補到5位
                    # (如 9805 → 09805，但實際常見是 00xxxx，這裡簡化處理)
                    # 更保險的做法：檢查是否為常見 ETF 範圍
                    if first_digit == '9' and int(symbol_str) >= 9000:
                        # 9xxx → 補到5位 (如 9805 → 09805)
                        symbol_str = symbol_str.zfill(5)
                    elif first_digit in ['6', '7', '8']:
                        # 6xxx/7xxx/8xxx 一般為個股，保持4位
                        pass
                # 否則保持4位（一般個股，如 1519, 4979, 6442, 6789）
            elif num_len == 5:
                # 5位數字 → 檢查是否為 009XX 格式，需補到6位
                if symbol_str.startswith("009"):
                    symbol_str = symbol_str.zfill(6)
                elif symbol_str.startswith("0") and not symbol_str.startswith("00"):
                    # 09xxx (如 09805) → 補到 00xxxx (如 009805)
                    # 但這會變成6位，先檢查是否已經是 00xxx
                    pass
            # 6位數字以上直接用
        
        # 加上 .TW 後綴
        return f"{symbol_str}.TW"
    
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
            
            # 台股 symbol 正規化（在 Pydantic 驗證前）
            if "symbol" in mapped_data and "asset_ccy" in mapped_data:
                try:
                    mapped_data["symbol"] = self.normalize_tw_symbol(
                        mapped_data["symbol"], 
                        mapped_data["asset_ccy"]
                    )
                except Exception as e:
                    return None, f"symbol 正規化失敗：{str(e)}"
            
            # trade_date 防呆：提前檢查是否為明顯錯誤的值
            if "trade_date" in mapped_data:
                trade_date_str = str(mapped_data["trade_date"]).strip()
                # 若只有單個字元（如 ":"），或明顯不是日期格式，提前報錯
                if len(trade_date_str) < 8 or trade_date_str in [":", "-", "/", "N/A", "NA", ""]:
                    return None, f"trade_date 格式錯誤：'{trade_date_str}'"
            
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
        Hash 包含版本前綴，避免未來規則變動造成衝突。
        
        Hash 計算方式：
        1. 將所有欄位按固定順序串接成 canonical 字串
        2. 前綴版本標識（CANONICAL_VERSION）
        3. 使用 SHA-256 計算 hash
        
        Canonical 字串格式：
        {version}|user_id|symbol|asset_ccy|side|quantity|price|fee|trade_date|broker
        
        注意事項：
        - Decimal 欄位統一格式化為字串（避免 1.0 vs 1.00 的差異）
        - 日期統一格式化為 ISO 8601（YYYY-MM-DD HH:MM:SS）
        - 版本前綴確保未來 canonical 規則變更時不會產生相同 hash
        
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
        
        # 按固定順序串接（使用 | 分隔），包含版本前綴
        canonical = f"{CANONICAL_VERSION}|" + "|".join([
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
