"""Strategy Engine: Pluggable decision engine for investment strategies.

This module provides:
- Fixed Input/Output schemas (Pydantic)
- Plugin architecture for strategy implementations
- v1.4 plugin as the first implementation (EDS minimum viable)
"""

from .schemas import InputSchema, OutputSchema
from .engine import StrategyEngine, get_default_engine

__all__ = ["InputSchema", "OutputSchema", "StrategyEngine", "get_default_engine"]
