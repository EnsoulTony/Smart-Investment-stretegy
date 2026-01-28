"""Positions Repository - 持倉查詢資料存取層。"""

from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Position
from app.schemas import PositionItem


def list_positions_for_user(
    db: Session,
    user_id: str,
    asof: Optional[str] = None,
    limit: int = 500,
    cursor: Optional[str] = None
) -> Tuple[List[PositionItem], Optional[str]]:
    """查詢指定使用者的持倉快照（只讀）。

    Args:
        db: SQLAlchemy session
        user_id: 使用者 ID
        asof: 查詢時點（未來擴充）
        limit: 回傳筆數上限
        cursor: 分頁游標（未來擴充）

    Returns:
        Tuple[List[PositionItem], Optional[str]]: (items, next_cursor)
    """
    positions = (
        db.query(Position)
        .filter(Position.user_id == user_id)
        .limit(limit)
        .all()
    )

    items: List[PositionItem] = []
    for pos in positions:
        cost_basis = Decimal(pos.quantity) * Decimal(pos.avg_cost)
        items.append(
            PositionItem(
                symbol=pos.symbol,
                asset_ccy=pos.asset_ccy,
                quantity=pos.quantity,
                avg_cost=pos.avg_cost,
                realized_pnl=pos.realized_pnl,
                cost_basis=cost_basis,
                name_zh=getattr(pos, "name_zh", None),
            )
        )

    return items, None
