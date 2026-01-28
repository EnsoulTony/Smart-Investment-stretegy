"""同步服務協調器 - 串接 Google Sheets 與 DB 寫入。

負責協調整個同步流程：
1. 建立 sync_run 記錄
2. 從 Google Sheets 讀取資料
3. 標準化與驗證
4. 批次寫入 trades 表
5. 更新 sync_run 狀態
"""

import json
import logging
import uuid
from typing import Dict, List, Any
from sqlalchemy.orm import Session

from app.sheets_client import SheetsClient
from app.trade_normalizer import TradeNormalizer
from app.repositories.trades_repo import TradesRepository
from app.repositories.symbol_name_mappings_repo import SymbolNameMappingsRepository
from app.repositories.sync_runs_repo import SyncRunsRepository
from app.symbol_name_resolver import SymbolNameResolver

# 設定 logger
logger = logging.getLogger(__name__)


class SyncResult:
    """同步結果資料類別。"""
    
    def __init__(
        self,
        run_id: uuid.UUID,
        inserted_count: int,
        updated_count: int,
        skipped_count: int,
        errors_count: int,
        status: str = "succeeded",
        sheet_rows_count: int = 0,
        normalized_valid_count: int = 0,
        normalized_invalid_count: int = 0,
        duplicates_count: int = 0
    ):
        self.run_id = run_id
        self.inserted_count = inserted_count
        self.updated_count = updated_count
        self.skipped_count = skipped_count
        self.errors_count = errors_count
        self.status = status
        # 可觀測性欄位
        self.sheet_rows_count = sheet_rows_count
        self.normalized_valid_count = normalized_valid_count
        self.normalized_invalid_count = normalized_invalid_count
        self.duplicates_count = duplicates_count
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典（用於 API 回應）。"""
        return {
            "run_id": str(self.run_id),
            "inserted_count": self.inserted_count,
            "updated_count": self.updated_count,
            "skipped_count": self.skipped_count,
            "errors_count": self.errors_count,
            "status": self.status,
            # 可觀測性欄位
            "sheet_rows_count": self.sheet_rows_count,
            "normalized_valid_count": self.normalized_valid_count,
            "normalized_invalid_count": self.normalized_invalid_count,
            "duplicates_count": self.duplicates_count
        }


class SyncService:
    """同步服務協調器。
    
    負責整個 Google Sheets → DB 的同步流程。
    """
    
    def __init__(
        self, 
        session: Session,
        sheets_client: SheetsClient = None
    ):
        """初始化同步服務。
        
        Args:
            session: SQLAlchemy session
            sheets_client: Google Sheets 客戶端（可選，用於測試時注入 mock）
        """
        self.session = session
        self.sheets_client = sheets_client or SheetsClient()
        self.trades_repo = TradesRepository(session)
        self.sync_runs_repo = SyncRunsRepository(session)
        self.symbol_repo = SymbolNameMappingsRepository(session)
        self.symbol_resolver = SymbolNameResolver(self.symbol_repo)
        self.normalizer = TradeNormalizer()
    
    def run_sync(self) -> SyncResult:
        """執行完整同步流程。
        
        流程：
        1. 建立 sync_run(status=started)
        2. 從 Google Sheets 讀取資料
        3. 標準化與驗證（TradeNormalizer）
        4. 批次寫入 trades 表（ON CONFLICT DO NOTHING）
        5. 更新 sync_run 狀態與統計
        
        Returns:
            SyncResult: 同步結果（含 run_id, inserted/skipped/errors 統計與可觀測性欄位）
        
        Raises:
            Exception: 當同步過程發生嚴重錯誤時
        """
        # Step 1: 建立 sync_run 記錄
        sync_run = self.sync_runs_repo.create_run()
        run_id = sync_run.run_id
        logger.info(f"同步開始 run_id={run_id}")
        
        try:
            # Step 2: 從 Google Sheets 讀取資料
            rows_dicts = self.sheets_client.fetch_trades_dicts()
            sheet_rows_count = len(rows_dicts)
            logger.info(f"從 Google Sheets 讀取 {sheet_rows_count} 列資料")
            
            # Step 3: 標準化與驗證
            valid_trades, failed_rows = self.normalizer.normalize_rows(rows_dicts)
            normalized_valid_count = len(valid_trades)
            normalized_invalid_count = len(failed_rows)
            logger.info(f"標準化結果：成功 {normalized_valid_count} 筆，失敗 {normalized_invalid_count} 筆")
            
            errors_count = normalized_invalid_count
            
            # Step 4: 補齊 name_zh（mapping table + provider）
            if valid_trades:
                symbol_cache: Dict[str, str] = {}
                for trade in valid_trades:
                    if trade.name_zh:
                        continue
                    key = f"{trade.symbol}|{trade.asset_ccy}"
                    if key not in symbol_cache:
                        symbol_cache[key] = self.symbol_resolver.resolve(
                            trade.symbol, trade.asset_ccy
                        )
                    trade.name_zh = symbol_cache[key]

            # Step 5: 批次寫入 trades 表（使用 ON CONFLICT DO NOTHING 去重）
            inserted_count, duplicates_count = 0, 0
            
            if valid_trades:
                logger.info(f"準備寫入 {len(valid_trades)} 筆交易記錄到資料庫")
                inserted_count, duplicates_count = self.trades_repo.bulk_insert_trades(valid_trades)
                logger.info(f"寫入完成：插入 {inserted_count} 筆，重複跳過 {duplicates_count} 筆")
            else:
                logger.warning("無有效交易記錄可寫入")

            # 正確的 normalized_valid_count 應包含後續被判定為重複的筆數
            normalized_valid_count = inserted_count + duplicates_count
            
            # skipped_count = 重複筆數 + 驗證失敗筆數
            skipped_count = duplicates_count + errors_count
            
            # Step 6: 建立錯誤摘要（最多保留前 20 筆，包含原始資料）
            error_message = None
            if errors_count > 0:
                error_summary = {
                    "errors_count": errors_count,
                    "errors": [
                        {
                            "row": failed_row["row_index"],
                            "reason": failed_row["error"],
                            "raw": failed_row["raw_data"]
                        }
                        for failed_row in failed_rows[:20]  # 限制最多 20 筆
                    ]
                }
                error_message = json.dumps(error_summary, ensure_ascii=False)
            
            # Step 7: 判斷同步狀態
            if inserted_count > 0 and (errors_count > 0 or duplicates_count > 0):
                status = "partial_succeeded"
            elif inserted_count > 0 and errors_count == 0 and duplicates_count == 0:
                status = "succeeded"
            elif inserted_count == 0 and errors_count > 0:
                status = "failed"
            else:
                # inserted_count == 0 且只因重複跳過 → 視為成功
                status = "succeeded"
            
            logger.info(f"同步狀態：{status}")
            
            # Step 8: 更新 sync_run 狀態
            self.sync_runs_repo.finish_run(
                run_id=run_id,
                status=status,
                inserted_count=inserted_count,
                updated_count=0,  # 目前版本不支援更新，固定為 0
                skipped_count=skipped_count,
                error_message=error_message
            )
            
            return SyncResult(
                run_id=run_id,
                inserted_count=inserted_count,
                updated_count=0,
                skipped_count=skipped_count,
                errors_count=errors_count,
                status=status,
                # 可觀測性欄位
                sheet_rows_count=sheet_rows_count,
                normalized_valid_count=normalized_valid_count,
                normalized_invalid_count=normalized_invalid_count,
                duplicates_count=duplicates_count
            )
            
        except Exception as e:
            # 發生錯誤：更新 sync_run 狀態（failed）
            logger.exception(f"同步過程發生錯誤 run_id={run_id}: {e}")
            error_message = f"{type(e).__name__}: {str(e)}"
            
            try:
                self.sync_runs_repo.finish_run(
                    run_id=run_id,
                    status="failed",
                    inserted_count=0,
                    updated_count=0,
                    skipped_count=0,
                    error_message=error_message[:500]  # 限制長度避免超過欄位限制
                )
            except Exception as db_error:
                # 若更新 sync_run 失敗，記錄但不影響原本的錯誤
                print(f"警告：無法更新 sync_run 狀態：{db_error}")
            
            # Re-raise 原始錯誤
            raise
