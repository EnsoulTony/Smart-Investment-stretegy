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

from .guardrails_utils import strip_comments_and_docstrings, iter_lines


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
    - DATABASE_URL / PORTFOLIO_DATABASE_URL
    - POSTGRES_* / PGHOST / PGPORT / PGUSER / PGPASSWORD
    """
    app_dir = Path(__file__).parent.parent / "app"
    
    violations = []
    
    for py_file in app_dir.rglob("*.py"):
        content = py_file.read_text()
        content = strip_comments_and_docstrings(content)
        
        # 檢查 DB 連線字串
        if re.search(r'postgresql://', content):
            violations.append(f"{py_file.name}: postgresql:// connection string")
        
        if re.search(r'mysql://', content):
            violations.append(f"{py_file.name}: mysql:// connection string")
        
        # 允許讀取 PORTFOLIO_BASE_URL（這是 HTTP URL）
        # 但禁止讀取 DB 相關 env key
        if re.search(r'DATABASE_URL', content):
            violations.append(f"{py_file.name}: DATABASE_URL (DB connection)")
        if re.search(r'PORTFOLIO_DATABASE_URL', content):
            violations.append(f"{py_file.name}: PORTFOLIO_DATABASE_URL (DB connection)")
        if re.search(r'POSTGRES_', content):
            violations.append(f"{py_file.name}: POSTGRES_ env")
        if re.search(r'PGHOST|PGPORT|PGUSER|PGPASSWORD|PGDATABASE', content):
            violations.append(f"{py_file.name}: PG* env")
    
    assert not violations, (
        f"❌ 違反 Sprint 1-4.B 鐵律：valuation-service 禁止 DB 連線！\n"
        f"發現違規：\n" + "\n".join(f"  - {v}" for v in violations) + "\n"
        f"只能使用 PORTFOLIO_BASE_URL（HTTP）取數。"
    )


# ============================================================================
# 🚫 Guardrail 5: 禁止 DB 直連關鍵字（統一掃描）
# ============================================================================

def test_codebase_no_db_keywords():
    """掃描 app/*.py，禁止 DB 直連關鍵字

    違規關鍵字：sqlalchemy | psycopg2 | postgresql://
    """
    app_dir = Path(__file__).parent.parent / "app"

    violations = []
    tokens = ["sqlalchemy", "psycopg2", "postgresql://"]

    for py_file in app_dir.rglob("*.py"):
        with open(py_file, 'r') as f:
            content = f.read().lower()

        for token in tokens:
            if token in content:
                violations.append(f"{py_file.name}: {token}")

    assert not violations, (
        "❌ 違反架構鐵律：valuation-service 禁止 DB 直連關鍵字！\n"
        + "\n".join(f"  - {v}" for v in violations)
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
        content = strip_comments_and_docstrings(py_file.read_text())

        for i, line in iter_lines(content):
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
        content = strip_comments_and_docstrings(py_file.read_text())

        for i, line in iter_lines(content):
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
# 🚫 Guardrail 5: docker-compose 禁止 valuation-service 注入 DB 連線資訊
# ============================================================================

def test_compose_no_db_env_for_valuation_service():
    """掃描 docker-compose*.yml，禁止 valuation-service 注入 DB 連線資訊"""
    repo_root = None
    for parent in Path(__file__).resolve().parents:
        if (parent / "docker-compose.yml").exists() or (parent / "docker-compose.test.yml").exists():
            repo_root = parent
            break

    if repo_root is None:
        pytest.skip("compose files not found")

    compose_files = [
        repo_root / "docker-compose.yml",
        repo_root / "docker-compose.test.yml",
    ]

    forbidden_envs = [
        "DATABASE_URL",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    ]

    violations = []
    for compose_path in compose_files:
        if not compose_path.exists():
            continue

        lines = compose_path.read_text().splitlines()
        in_service = False
        in_env_file_block = False
        env_files: list[Path] = []

        for idx, line in enumerate(lines, 1):
            if line.startswith("  ") and not line.startswith("    "):
                in_service = line.strip() == "valuation-service:"
                in_env_file_block = False

            if not in_service:
                continue

            if line.strip().startswith("env_file:"):
                in_env_file_block = True
                continue
            if in_env_file_block and line.strip().startswith("- "):
                env_files.append((compose_path.parent / line.strip().lstrip("- ")).resolve())
                continue
            if in_env_file_block and line.strip() and not line.strip().startswith("-"):
                in_env_file_block = False

            for env_key in forbidden_envs:
                if env_key in line:
                    violations.append(f"{compose_path.name}:{idx} - {env_key}")

        for env_path in env_files:
            if not env_path.exists():
                continue
            for idx, line in enumerate(env_path.read_text().splitlines(), 1):
                for env_key in forbidden_envs:
                    if line.strip().startswith(env_key + "="):
                        violations.append(f"{env_path.name}:{idx} - {env_key}")

    assert not violations, (
        "❌ 違反硬隔離規則：valuation-service 禁止注入 DB 連線設定！\n"
        + "\n".join(f"  - {v}" for v in violations)
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
