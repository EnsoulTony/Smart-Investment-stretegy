"""Repository for symbol_name_mappings table."""

from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models_core import SymbolNameMapping


class SymbolNameMappingsRepository:
    """CRUD for symbol_name_mappings table."""

    def __init__(self, session: Session):
        self.session = session

    def get_mapping(self, symbol: str, market: str) -> Optional[SymbolNameMapping]:
        return (
            self.session.query(SymbolNameMapping)
            .filter(SymbolNameMapping.symbol == symbol, SymbolNameMapping.market == market)
            .first()
        )

    def list_mappings(self, query: Optional[str] = None, limit: int = 200) -> List[SymbolNameMapping]:
        q = self.session.query(SymbolNameMapping)
        if query:
            like = f"%{query.upper()}%"
            q = q.filter(SymbolNameMapping.symbol.ilike(like))
        return q.order_by(SymbolNameMapping.symbol.asc()).limit(limit).all()

    def upsert_mapping(
        self,
        symbol: str,
        market: str,
        name_zh: str,
        source: str,
    ) -> SymbolNameMapping:
        now = datetime.now(timezone.utc)
        mapping = self.get_mapping(symbol, market)
        if mapping:
            mapping.name_zh = name_zh
            mapping.source = source
            mapping.updated_at = now
        else:
            mapping = SymbolNameMapping(
                symbol=symbol,
                market=market,
                name_zh=name_zh,
                source=source,
                updated_at=now,
            )
            self.session.add(mapping)
        self.session.commit()
        return mapping
