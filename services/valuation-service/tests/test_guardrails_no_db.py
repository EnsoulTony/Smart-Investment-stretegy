"""Architecture Guardrails - Valuation Service

Sprint 1-4.B 鐵律：估值層禁止 DB 直連，只能透過 HTTP API 取數

檢查項目：
1. 禁止 requirements.txt 包含 DB driver（sqlalchemy/psycopg2/asyncpg）
2. 禁止 codebase 出現 DB 連線字串（postgresql://）
3. 禁止 codebase 出現 SQLAlchemy Session/Engine
4. 禁止 codebase 出現 psycopg2.connect
"""

import pytest
import os
import re
from pathlib import Path


# ============================================================================
# 🚫 Guardrail 1: 禁止 requirements.txt 包含 DB driver
# ============================================================================

def test_requirements_no_db_drivers():
    """檢查 requirements.txt 禁止任何 DB driver
    
    鐵律：valuation-service 只能透過 HTTP 取數，不得有任何 DB library
    """
    # 在容器中，requirements.txt 位於 /app/services/valuation-service/requirements.txt
    requirements_path = Path("/app/services/valuation-service/requirements.txt")
    
    if not requirements_path.exists():
        pytest.skip(f"requirements.txt not found at {requirements_path}")
    
    with open(requirements_path, 'r') as f:
        content = f.read().lower()
    
    # 禁止清單
    forbidden_packages = [
        "sqlalchemy",
        "psycopg2",
        "psycopg2-binary",
        "asyncpg",
        "pymysql",
        "mysqlclient",
        "psycopg",  # psycopg3
    ]
    
    violations = []
    for pkg in forbidden_packages:
        # 檢查是否出現（忽略註解中的說明）
        pattern = rf'^[^#]*\b{re.escape(pkg)}\b'
        if re.search(pattern, content, re.MULTILINE):
            violations.append(pkg)
    
    assert not violations, (
        f"❌ 違反 Sprint 1-4.B 鐵律：valuation-service 禁止 DB driver！\n"
        f"發現違規套件：{violations}\n"
        f"只能透過 HTTP API 從 portfolio-service 取數。"
    )


# ============================================================================
# 🚫 Guardrail 2: 禁止 codebase 出現 DB 連線字串
# ============================================================================

def test_codebase_no_db_connection_strings():
    """掃描 app/*.py，禁止任何 DB 連線字串
    
    違規模式：
    - postgresql://
    - mysql://
    - DATABASE_URL（直接讀取 DB URL）
    """
    app_dir = Path(__file__).parent.parent / "app"
    
    violations = []
    
    for py_file in app_dir.rglob("*.py"):
        with open(py_file, 'r') as f:
            content = f.read()
        
        # 檢查 DB 連線字串
        if re.search(r'postgresql://', content):
            violations.append(f"{py_file.name}: postgresql:// connection string")
        
        if re.search(r'mysql://', content):
            violations.append(f"{py_file.name}: mysql:// connection string")
        
        # 允許讀取 PORTFOLIO_BASE_URL（這是 HTTP URL）
        # 但禁止讀取 DATABASE_URL
        if re.search(r'DATABASE_URL', content):
            violations.append(f"{py_file.name}: DATABASE_URL (DB connection)")
    
    assert not violations, (
        f"❌ 違反 Sprint 1-4.B 鐵律：valuation-service 禁止 DB 連線！\n"
        f"發現違規：\n" + "\n".join(f"  - {v}" for v in violations) + "\n"
        f"只能使用 PORTFOLIO_BASE_URL（HTTP）取數。"
    )


# ============================================================================
# 🚫 Guardrail 3: 禁止 codebase 出現 SQLAlchemy Session/Engine
# ============================================================================

def test_codebase_no_sqlalchemy_usage():
    """掃描 app/*.py，禁止任何 SQLAlchemy 使用
    
    違規模式：
    - from sqlalchemy import
    - from sqlalchemy.orm import Session
    - create_engine(
    - sessionmaker(
    """
    app_dir = Path(__file__).parent.parent / "app"
    
    violations = []
    
    for py_file in app_dir.rglob("*.py"):
        with open(py_file, 'r') as f:
            lines = f.readlines()
        
        for i, line in enumerate(lines, 1):
            # 跳過註解
            if line.strip().startswith('#'):
                continue
            
            # 檢查 SQLAlchemy import
            if re.search(r'from sqlalchemy', line):
                violations.append(f"{py_file.name}:{i} - from sqlalchemy")
            
            if re.search(r'import sqlalchemy', line):
                violations.append(f"{py_file.name}:{i} - import sqlalchemy")
            
            # 檢查 SQLAlchemy 使用
            if re.search(r'Session\s*\(', line):
                violations.append(f"{py_file.name}:{i} - Session()")
            
            if re.search(r'create_engine\s*\(', line):
                violations.append(f"{py_file.name}:{i} - create_engine()")
            
            if re.search(r'sessionmaker\s*\(', line):
                violations.append(f"{py_file.name}:{i} - sessionmaker()")
    
    assert not violations, (
        f"❌ 違反 Sprint 1-4.B 鐵律：valuation-service 禁止 SQLAlchemy！\n"
        f"發現違規：\n" + "\n".join(f"  - {v}" for v in violations) + "\n"
        f"只能使用 httpx client 透過 HTTP 取數。"
    )


# ============================================================================
# 🚫 Guardrail 4: 禁止 codebase 出現 psycopg2.connect
# ============================================================================

def test_codebase_no_psycopg2_usage():
    """掃描 app/*.py，禁止任何 psycopg2 使用
    
    違規模式：
    - import psycopg2
    - psycopg2.connect(
    """
    app_dir = Path(__file__).parent.parent / "app"
    
    violations = []
    
    for py_file in app_dir.rglob("*.py"):
        with open(py_file, 'r') as f:
            lines = f.readlines()
        
        for i, line in enumerate(lines, 1):
            # 跳過註解
            if line.strip().startswith('#'):
                continue
            
            # 檢查 psycopg2
            if re.search(r'import psycopg2', line):
                violations.append(f"{py_file.name}:{i} - import psycopg2")
            
            if re.search(r'psycopg2\.connect', line):
                violations.append(f"{py_file.name}:{i} - psycopg2.connect")
    
    assert not violations, (
        f"❌ 違反 Sprint 1-4.B 鐵律：valuation-service 禁止 psycopg2！\n"
        f"發現違規：\n" + "\n".join(f"  - {v}" for v in violations) + "\n"
        f"只能使用 httpx client 透過 HTTP 取數。"
    )


# ============================================================================
# ✅ 正向檢查：確認有使用 HTTP client
# ============================================================================

def test_codebase_uses_http_client():
    """確認 codebase 使用 HTTP client（httpx）取數"""
    app_dir = Path(__file__).parent.parent / "app"
    
    uses_httpx = False
    uses_portfolio_client = False
    
    for py_file in app_dir.rglob("*.py"):
        with open(py_file, 'r') as f:
            content = f.read()
        
        if 'import httpx' in content or 'from httpx' in content:
            uses_httpx = True
        
        if 'PortfolioClient' in content:
            uses_portfolio_client = True
    
    assert uses_httpx, "應該使用 httpx 作為 HTTP client"
    assert uses_portfolio_client, "應該使用 PortfolioClient 從 portfolio-service 取數"
