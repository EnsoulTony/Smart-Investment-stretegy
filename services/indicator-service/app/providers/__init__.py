"""Indicator data providers.

Provides pluggable data sources:
- StubProvider: Fixed values for testing/offline (default)
- YFinanceProvider: Live data from Yahoo Finance (optional)
"""

from .stub import StubProvider

__all__ = ["StubProvider"]
