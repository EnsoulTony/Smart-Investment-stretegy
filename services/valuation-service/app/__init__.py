"""Valuation Service - Sprint 1-4.B

估值層骨架，遵守架構鐵律：
- 只能透過 portfolio-service HTTP API 取數
- 禁止任何 DB 連線（sqlalchemy/psycopg2/asyncpg）
- 真實 FX provider/cache 只能放這裡（portfolio-service 只有 stub）
"""

__version__ = "1.4.B-skeleton"
