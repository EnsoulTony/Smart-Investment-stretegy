"""Service layer for core holdings settings (DB-only)."""

from typing import List, Tuple
from sqlalchemy.orm import Session

from app.repositories.core_holdings_repo import CoreHoldingsRepository


class CoreHoldingsService:
    """Manage core holdings list for a user."""

    def __init__(self, session: Session):
        self.session = session
        self.core_repo = CoreHoldingsRepository(session)

    def list_core_symbols(self, user_id: str) -> List[str]:
        return self.core_repo.list_core_symbols(user_id)

    def save_core_holdings(self, user_id: str, symbols: List[str]) -> int:
        """Replace user's core holdings with given symbols."""
        return self.core_repo.replace_core_holdings(user_id, symbols)
