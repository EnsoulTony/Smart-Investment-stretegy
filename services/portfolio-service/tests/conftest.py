import sys
from pathlib import Path
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

# 將服務根目錄加入 import 路徑，讓 `from app.main import app` 可用
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import Base
import os

os.environ.setdefault("SYMBOL_NAME_PROVIDER", "disabled")


@pytest.fixture(scope="function")
def db_engine():
    """每個測試使用獨立的 engine，連接到相同的 DB。
    
    雷 B 修復：使用 nested transaction (SAVEPOINT) 保證測試隔離，不污染資料。
    """
    database_url = os.getenv("DATABASE_URL", "postgresql://investment:investment@postgres:5432/investment_db")
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    """每個測試使用獨立的 session，基於 SAVEPOINT 機制實現完全隔離。
    
    修復 SAWarning: transaction already deassociated from connection
    
    原因：
    - 當測試中呼叫 session.commit() 時，SQLAlchemy 會結束當前 transaction
    - 但我們希望測試結束後能 rollback 所有變更，包括已 commit 的內容
    
    解決方案（SAVEPOINT 模式）：
    1. 在外層開啟一個 transaction（不會被 commit 影響）
    2. 在內層開啟 nested transaction (SAVEPOINT)
    3. 監聽 session.after_transaction_end 事件，當 SAVEPOINT 結束時自動重開新的 SAVEPOINT
    4. 測試結束後 rollback 外層 transaction，所有變更（包括 commit）都會被撤銷
    
    這樣測試中的 commit() 實際上只是提交到 SAVEPOINT，不會真正寫入 DB。
    
    測試隔離增強：
    - 每個測試開始前清空 trades, sync_runs, positions 表
    - 使用 DELETE 而非 TRUNCATE（TRUNCATE 無法在 transaction 內回滾）
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    
    # 清空測試相關的表（在 transaction 內，確保可回滾）
    # 注意：使用 DELETE 而非 TRUNCATE，因為 TRUNCATE 會立即提交
    from app.models import Trade, SyncRun, Position, SymbolNameMapping
    session.query(Trade).delete()
    session.query(SyncRun).delete()
    session.query(Position).delete()
    session.query(SymbolNameMapping).delete()
    session.commit()  # 提交清空操作到外層 transaction
    
    # 開啟第一個 nested transaction (SAVEPOINT)
    nested = connection.begin_nested()
    
    # 監聽 session 的 after_transaction_end 事件
    # 當 nested transaction 結束時（例如測試中呼叫 commit），自動重開一個新的 SAVEPOINT
    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(session, transaction):
        if transaction.nested and not transaction._parent.nested:
            session.expire_all()
            session.begin_nested()
    
    yield session
    
    # 清理：關閉 session、rollback 外層 transaction、關閉連接
    session.close()
    transaction.rollback()
    connection.close()
