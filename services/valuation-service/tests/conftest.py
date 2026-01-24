"""Valuation Service - Test Configuration

Sprint 1-4.B：估值層測試配置
"""

import pytest
import sys
import os

# 確保可以 import app module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def anyio_backend():
    """使用 asyncio backend（支援 async 測試）"""
    return "asyncio"
