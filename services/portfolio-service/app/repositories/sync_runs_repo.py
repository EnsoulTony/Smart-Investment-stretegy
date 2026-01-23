"""SyncRuns Repository - 同步執行記錄資料存取層。

負責 sync_runs 表的所有 SQL 操作，記錄每次同步的執行狀態。
"""

import uuid
from typing import Optional
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.models import SyncRun


class SyncRunsRepository:
    """同步執行記錄 Repository。
    
    提供 sync_runs 表的資料存取方法，封裝 SQL 操作。
    """
    
    def __init__(self, session: Session):
        """初始化 Repository。
        
        Args:
            session: SQLAlchemy session
        """
        self.session = session
    
    def create_run(self) -> SyncRun:
        """建立新的同步執行記錄（status=started）。
        
        Returns:
            SyncRun: 新建立的同步記錄（已 commit）
        """
        sync_run = SyncRun(
            run_id=uuid.uuid4(),
            status="started",
            inserted_count=0,
            updated_count=0,
            skipped_count=0,
        )
        
        self.session.add(sync_run)
        self.session.commit()
        self.session.refresh(sync_run)  # 重新載入以取得 created_at 等欄位
        
        return sync_run
    
    def finish_run(
        self,
        run_id: uuid.UUID,
        status: str,
        inserted_count: int = 0,
        updated_count: int = 0,
        skipped_count: int = 0,
        error_message: Optional[str] = None
    ) -> SyncRun:
        """完成同步執行（更新狀態與統計）。
        
        Args:
            run_id: 同步執行 ID
            status: 最終狀態（"succeeded" 或 "failed"）
            inserted_count: 實際插入筆數
            updated_count: 更新筆數（目前版本固定為 0）
            skipped_count: 跳過筆數（重複或錯誤）
            error_message: 錯誤訊息（失敗時填寫）
        
        Returns:
            SyncRun: 更新後的同步記錄
        
        Raises:
            ValueError: 當 run_id 不存在時
        """
        sync_run = self.session.query(SyncRun).filter(SyncRun.run_id == run_id).first()
        
        if not sync_run:
            raise ValueError(f"SyncRun {run_id} 不存在")
        
        # 更新狀態與統計
        sync_run.status = status
        sync_run.inserted_count = inserted_count
        sync_run.updated_count = updated_count
        sync_run.skipped_count = skipped_count
        sync_run.finished_at = datetime.now(timezone.utc)
        
        if error_message:
            sync_run.error_message = error_message
        
        self.session.commit()
        self.session.refresh(sync_run)
        
        return sync_run
    
    def get_run(self, run_id: uuid.UUID) -> Optional[SyncRun]:
        """取得指定的同步執行記錄。
        
        Args:
            run_id: 同步執行 ID
        
        Returns:
            Optional[SyncRun]: 同步記錄，若不存在則回傳 None
        """
        return self.session.query(SyncRun).filter(SyncRun.run_id == run_id).first()
    
    def get_latest_runs(self, limit: int = 10) -> list[SyncRun]:
        """取得最近的同步執行記錄。
        
        Args:
            limit: 最多回傳筆數
        
        Returns:
            list[SyncRun]: 同步記錄列表（依 created_at 降冪排序）
        """
        return (
            self.session.query(SyncRun)
            .order_by(SyncRun.created_at.desc())
            .limit(limit)
            .all()
        )
