"""同步服務協調器 - 串接 Google Sheets 與 DB 寫入。

負責協調整個同步流程：
1. 建立 sync_run 記錄
2. 從 Google Sheets 讀取資料
3. 標準化與驗證
4. 批次寫入 trades 表
5. 更新 sync_run 狀態
"""

import json
import uuid
from typing import Dict, List, Any
from sqlalchemy.orm import Session

from app.sheets_client import SheetsClient
from app.trade_normalizer import TradeNormalizer
from app.repositories.trades_repo import TradesRepository
from app.repositories.sync_runs_repo import SyncRunsRepository


class SyncResult:
    """同步結果資料類別。"""
    
    def __init__(
        self,
        run_id: uuid.UUID,
        inserted_count: int,
        updated_count: int,
        skipped_count: int,
        errors_count: int,
        status: str = "succeeded"
    ):
        self.run_id = run_id
        self.inserted_count = inserted_count
        self.updated_count = updated_count
        self.skipped_count = skipped_count
        self.errors_count = errors_count
        self.status = status
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典（用於 API 回應）。"""
        return {
            "run_id": str(self.run_id),
            "inserted_count": self.inserted_count,
            "updated_count": self.updated_count,
            "skipped_count": self.skipped_count,
            "errors_count": self.errors_count,
            "status": self.status
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
            SyncResult: 同步結果（含 run_id, inserted/skipped/errors 統計）
        
        Raises:
            Exception: 當同步過程發生嚴重錯誤時
        """
        # Step 1: 建立 sync_run 記錄
        sync_run = self.sync_runs_repo.create_run()
        run_id = sync_run.run_id
        
        try:
            # Step 2: 從 Google Sheets 讀取資料
            rows_dicts = self.sheets_client.fetch_trades_dicts()
            
            # Step 3: 標準化與驗證
            valid_trades, failed_rows = self.normalizer.normalize_rows(rows_dicts)
            
            errors_count = len(failed_rows)
            
            # Step 4: 批次寫入 trades 表（使用 ON CONFLICT DO NOTHING 去重）
            inserted_count, skipped_count = 0, 0
            
            if valid_trades:
                inserted_count, skipped_by_hash = self.trades_repo.bulk_insert_trades(valid_trades)
                # skipped_count 包含：source_hash 重複的筆數 + 驗證失敗的筆數
                skipped_count = skipped_by_hash + errors_count
            else:
                skipped_count = errors_count
            
            # Step 5: 建立錯誤摘要（最多保留前 20 筆，包含原始資料）
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
            
            # Step 6: 判斷同步狀態
            if errors_count == 0:
                status = "succeeded"
            elif inserted_count + 0 > 0:  # updated_count 目前固定為 0
                status = "partial_succeeded"
            else:
                status = "failed"
            
            # Step 7: 更新 sync_run 狀態
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
                status=status
            )
            
        except Exception as e:
            # 發生錯誤：更新 sync_run 狀態（failed）
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
