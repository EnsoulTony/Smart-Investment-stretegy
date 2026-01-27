"""Repository for core_holdings settings (persisted from trades is_core flags)."""

from typing import List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from datetime import datetime, timezone

from app.models import CoreHolding


class CoreHoldingsRepository:
    """CRUD for core_holdings table."""

    def __init__(self, session: Session):
        self.session = session

    def upsert_core_holdings(self, rows: List[Tuple[str, str, bool]]) -> Tuple[int, int]:
        """Upsert (user_id, symbol, is_core) rows.

        Returns (inserted, updated)
        """
        if not rows:
            return 0, 0

        now = datetime.now(timezone.utc)
        values = [
            {"user_id": u, "symbol": s, "is_core": is_core, "updated_at": now}
            for (u, s, is_core) in rows
        ]

        stmt = insert(CoreHolding).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[CoreHolding.user_id, CoreHolding.symbol],
            set_={
                "is_core": stmt.excluded.is_core,
                "updated_at": now,
            },
        )
        result = self.session.execute(stmt)
        self.session.commit()
        # result.rowcount in PG includes inserts+updates
        return len(rows), result.rowcount or 0

    def list_core_symbols(self, user_id: str) -> List[str]:
        return [row[0] for row in self.session.query(CoreHolding.symbol).filter(CoreHolding.user_id == user_id, CoreHolding.is_core == True).all()]  # noqa: E712

    def replace_core_holdings(self, user_id: str, symbols: List[str]) -> int:
        """Replace user's core holdings with provided symbols list.

        Returns number of symbols stored.
        """
        # Normalize symbols to upper and unique
        norm_symbols = []
        seen = set()
        for s in symbols:
            su = s.upper().strip()
            if not su or su in seen:
                continue
            seen.add(su)
            norm_symbols.append(su)

        # delete old
        self.session.query(CoreHolding).filter(CoreHolding.user_id == user_id).delete()
        self.session.flush()

        if norm_symbols:
            now = datetime.now(timezone.utc)
            rows = [
                CoreHolding(user_id=user_id, symbol=s, is_core=True, updated_at=now)
                for s in norm_symbols
            ]
            self.session.add_all(rows)
        self.session.commit()
        return len(norm_symbols)
