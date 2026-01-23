"""資料庫連線與設定模組。

使用 SQLAlchemy 2.x (sync) 連接 PostgreSQL。
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 從環境變數讀取資料庫連線字串
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://investment:investment@localhost:5432/investment_db")

# 建立 engine（同步模式）
engine = create_engine(
    DATABASE_URL,
    echo=False,  # 開發時可設為 True 查看 SQL 語句
    pool_pre_ping=True,  # 自動檢測連線健康狀態
    pool_size=5,
    max_overflow=10,
)

# 建立 session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 建立 Base class 供 models 繼承
Base = declarative_base()


def get_db():
    """取得資料庫 session（用於 FastAPI dependency injection）。
    
    使用範例：
    ```python
    from fastapi import Depends
    from app.db import get_db
    
    @app.get("/example")
    def example_endpoint(db: Session = Depends(get_db)):
        # 使用 db 進行查詢
        pass
    ```
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
