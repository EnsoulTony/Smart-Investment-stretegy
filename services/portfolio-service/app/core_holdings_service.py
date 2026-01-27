"""Service layer to derive core holdings from trades (is_core flags)."""

from typing import List, Tuple
from sqlalchemy.orm import Session

from app.repositories.trades_repo import TradesRepository
from app.repositories.core_holdings_repo import CoreHoldingsRepository


class CoreHoldingsService:
    """Compute and persist core holdings snapshot for a user."""

    def __init__(self, session: Session):
        self.session = session
        self.trades_repo = TradesRepository(session)
        self.core_repo = CoreHoldingsRepository(session)

    def rebuild_core_holdings(self, user_id: str) -> Tuple[int, int]:
        """Derive core holdings from trades with is_core flag.

        Returns (total_rows, upserted_rows)
        """
        trades = self.trades_repo.get_trades_by_user(user_id=user_id, limit=5000)
        rows = []
        for t in trades:
            # Only rows explicitly marked is_core True
            if getattr(t, "is_core", False):
                rows.append((t.user_id, t.symbol, True))
        inserted, updated = self.core_repo.upsert_core_holdings(rows)
        return len(rows), updated

    def list_core_symbols(self, user_id: str) -> List[str]:
        return self.core_repo.list_core_symbols(user_id)

    def save_core_holdings(self, user_id: str, symbols: List[str]) -> int:
        """Replace user's core holdings with given symbols."""
        return self.core_repo.replace_core_holdings(user_id, symbols)
