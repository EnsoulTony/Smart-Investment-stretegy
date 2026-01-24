"""Architecture Guardrails - Portfolio Service (Enhanced for Sprint 1-4.B)

Sprint 1-4.B 新增檢查：帳務層禁止做估值、禁止匯率折算

檢查項目：
1. 禁止帳務模組呼叫 fx.get_rate() 或 fx.convert()
2. 禁止帳務模組計算 market_value / unrealized_pnl（估值責任）
3. 禁止 positions 表包含估值欄位（market_price/market_value）
4. 禁止 rebuild_positions API 接受 target_ccy 參數（折算責任）
"""

import pytest
import os
import re
from pathlib import Path


# ============================================================================
# 🚫 Guardrail 1: 帳務模組禁止呼叫 FX API
# ============================================================================

def test_accounting_modules_no_fx_calls():
    """檢查帳務模組禁止呼叫 fx.get_rate() 或 fx.convert()
    
    鐵律：帳務層只記錄原始幣別與金額，不做任何折算
    估值層（valuation-service）才能呼叫 FX API
    """
    app_dir = Path(__file__).parent.parent / "app"
    
    # 帳務模組清單
    accounting_modules = [
        "position_rebuilder.py",
        "avg_cost_calculator.py",
        "trades_repository.py",
    ]
    
    violations = []
    
    for module_name in accounting_modules:
        module_path = app_dir / module_name
        
        if not module_path.exists():
            continue
        
        with open(module_path, 'r') as f:
            lines = f.readlines()
        
        for i, line in enumerate(lines, 1):
            # 跳過註解
            if line.strip().startswith('#'):
                continue
            
            # 檢查 FX API 呼叫
            if re.search(r'fx\.get_rate\s*\(', line):
                violations.append(f"{module_name}:{i} - fx.get_rate()")
            
            if re.search(r'fx\.convert\s*\(', line):
                violations.append(f"{module_name}:{i} - fx.convert()")
            
            # 檢查是否呼叫 FX provider
            if re.search(r'get_fx_provider\s*\(', line):
                violations.append(f"{module_name}:{i} - get_fx_provider()")
    
    assert not violations, (
        f"❌ 違反 Sprint 1-4.B 鐵律：帳務層禁止呼叫 FX API！\n"
        f"發現違規：\n" + "\n".join(f"  - {v}" for v in violations) + "\n"
        f"帳務層只記錄原始幣別（asset_ccy）與原始金額。\n"
        f"匯率折算只能在估值層（valuation-service）進行。"
    )


# ============================================================================
# 🚫 Guardrail 2: 帳務模組禁止計算估值
# ============================================================================

def test_accounting_modules_no_valuation_logic():
    """檢查帳務模組禁止計算 market_value / unrealized_pnl
    
    鐵律：帳務層只計算 avg_cost 與 realized_pnl，不做估值
    """
    app_dir = Path(__file__).parent.parent / "app"
    
    accounting_modules = [
        "position_rebuilder.py",
        "avg_cost_calculator.py",
        "trades_repository.py",
    ]
    
    violations = []
    
    for module_name in accounting_modules:
        module_path = app_dir / module_name
        
        if not module_path.exists():
            continue
        
        with open(module_path, 'r') as f:
            content = f.read()
        
        # 檢查估值相關變數名（排除註解與字串）
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            # 跳過註解與 docstring
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            
            # 檢查估值欄位
            if re.search(r'\bmarket_value\s*=', line):
                violations.append(f"{module_name}:{i} - market_value calculation")
            
            if re.search(r'\bmarket_price\s*=', line):
                violations.append(f"{module_name}:{i} - market_price calculation")
            
            # unrealized_pnl 只能填 0（明確禁止計算）
            if re.search(r'unrealized_pnl\s*=.*(?!0)', line) and '0' not in line:
                violations.append(f"{module_name}:{i} - unrealized_pnl calculation (should be 0)")
    
    assert not violations, (
        f"❌ 違反 Sprint 1-4.B 鐵律：帳務層禁止做估值！\n"
        f"發現違規：\n" + "\n".join(f"  - {v}" for v in violations) + "\n"
        f"帳務層只計算：quantity, avg_cost, realized_pnl。\n"
        f"估值計算（market_value, unrealized_pnl）只能在 valuation-service。"
    )


# ============================================================================
# 🚫 Guardrail 3: 禁止帳務 API 接受 target_ccy 參數
# ============================================================================

def test_accounting_api_no_target_ccy():
    """檢查帳務 API 禁止接受 target_ccy 參數
    
    鐵律：帳務 API 不做折算，只記錄原始幣別
    """
    main_path = Path(__file__).parent.parent / "app" / "main.py"
    
    if not main_path.exists():
        pytest.skip("main.py not found")
    
    with open(main_path, 'r') as f:
        content = f.read()
    
    violations = []
    
    # 檢查 rebuild_positions 相關函數
    # 使用正則匹配函數定義
    functions = re.findall(
        r'(def \w*rebuild\w*|def \w*position\w*|async def \w*rebuild\w*|async def \w*position\w*).*?(?=\n(?:def |async def |class |$))',
        content,
        re.DOTALL
    )
    
    for func in functions:
        if 'target_ccy' in func:
            violations.append(f"rebuild_positions or position API accepts target_ccy parameter")
    
    # 檢查 Pydantic schemas
    schemas_path = Path(__file__).parent.parent / "app" / "schemas.py"
    if schemas_path.exists():
        with open(schemas_path, 'r') as f:
            schemas_content = f.read()
        
        # 檢查 RebuildRequest 或類似 schema
        if 'target_ccy' in schemas_content and 'Rebuild' in schemas_content:
            violations.append("RebuildRequest schema contains target_ccy field")
    
    assert not violations, (
        f"❌ 違反 Sprint 1-4.B 鐵律：帳務 API 禁止接受 target_ccy！\n"
        f"發現違規：\n" + "\n".join(f"  - {v}" for v in violations) + "\n"
        f"帳務層只記錄原始幣別（asset_ccy），不做任何折算。\n"
        f"折算功能只能在 valuation-service 的 /valuation/revalue 端點。"
    )


# ============================================================================
# ✅ 正向檢查：確認 positions 表只有帳務欄位
# ============================================================================

def test_position_model_accounting_only():
    """確認 Position model 只包含帳務欄位，無估值欄位
    
    允許：user_id, symbol, asset_ccy, quantity, avg_cost, realized_pnl
    禁止：market_price, market_value, unrealized_pnl（非 0 的計算）
    """
    models_path = Path(__file__).parent.parent / "app" / "models.py"
    
    if not models_path.exists():
        pytest.skip("models.py not found")
    
    with open(models_path, 'r') as f:
        content = f.read()
    
    # 找到 Position class
    position_class = re.search(
        r'class Position.*?(?=\nclass |\Z)',
        content,
        re.DOTALL
    )
    
    if not position_class:
        pytest.skip("Position class not found")
    
    position_code = position_class.group()
    
    violations = []
    
    # 禁止估值欄位（除非是明確填 0 的 unrealized_pnl）
    if 'market_price' in position_code and 'Column' in position_code:
        violations.append("Position model has market_price column")
    
    if 'market_value' in position_code and 'Column' in position_code:
        violations.append("Position model has market_value column")
    
    assert not violations, (
        f"❌ 違反 Sprint 1-4.B 鐵律：Position 表不應有估值欄位！\n"
        f"發現違規：\n" + "\n".join(f"  - {v}" for v in violations) + "\n"
        f"帳務層表格只記錄帳務數據，估值數據應在 valuation-service 的專屬表。"
    )


# ============================================================================
# ✅ positions API Guardrails：檢查 GET /portfolio/positions 端點
# ============================================================================

def test_positions_api_no_valuation_logic():
    """確認 GET /portfolio/positions 端點不含估值邏輯
    
    檢查範圍：
    - ✅ 允許：cost_basis = quantity * avg_cost（帳務計算）
    - ❌ 禁止：market_value, unrealized_pnl 計算、fx_rate 呼叫、外部 API
    """
    main_path = Path(__file__).parent.parent / "app" / "main.py"
    
    if not main_path.exists():
        pytest.skip("main.py not found")
    
    with open(main_path, 'r') as f:
        content = f.read()
    
    # 找到 /portfolio/positions 端點
    positions_api = re.search(
        r'@app\.get\(["\']\/portfolio\/positions["\']\).*?(?=@app\.|^def test_|$)',
        content,
        re.DOTALL | re.MULTILINE
    )
    
    if not positions_api:
        pytest.skip("GET /portfolio/positions endpoint not found")
    
    positions_code = positions_api.group()
    
    violations = []
    
    # 禁止估值計算
    if 'market_value' in positions_code.lower():
        violations.append("positions API calculates market_value")
    
    if 'unrealized' in positions_code.lower() and 'unrealized_pnl' not in positions_code:
        # 允許讀取欄位，禁止計算
        if 'unrealized_pnl =' in positions_code or 'unrealized_pnl=' in positions_code:
            violations.append("positions API calculates unrealized_pnl")
    
    # 禁止 FX 呼叫
    if 'from app.fx' in positions_code or 'from .fx' in positions_code:
        violations.append("positions API imports fx module")
    
    if 'fx_rate' in positions_code.lower():
        violations.append("positions API uses fx_rate")
    
    # 禁止外部 API 呼叫
    if 'httpx' in positions_code or 'requests' in positions_code:
        violations.append("positions API calls external HTTP services")
    
    assert not violations, (
        f"❌ 違反 Sprint 1-4.B 鐵律：positions API 不應包含估值邏輯！\n"
        f"發現違規：\n" + "\n".join(f"  - {v}" for v in violations) + "\n"
        f"帳務層 API 只回傳原始帳務數據（+ cost_basis）。\n"
        f"估值計算應在 valuation-service 的 /valuation/revalue 端點。"
    )


def test_positions_api_response_schema():
    """確認 PositionSnapshot schema 只有帳務欄位
    
    允許：symbol, asset_ccy, quantity, avg_cost, realized_pnl, cost_basis
    禁止：market_value, unrealized_pnl, fx_rate, valuation_ccy
    """
    schemas_path = Path(__file__).parent.parent / "app" / "schemas.py"
    
    if not schemas_path.exists():
        pytest.skip("schemas.py not found")
    
    with open(schemas_path, 'r') as f:
        content = f.read()
    
    # 找到 PositionSnapshot class
    snapshot_class = re.search(
        r'class PositionSnapshot.*?(?=\nclass |\Z)',
        content,
        re.DOTALL
    )
    
    if not snapshot_class:
        pytest.skip("PositionSnapshot class not found")
    
    snapshot_code = snapshot_class.group()
    
    violations = []
    
    # 禁止估值欄位
    forbidden_fields = ['market_value', 'unrealized_pnl', 'fx_rate', 'valuation_ccy']
    for field in forbidden_fields:
        if f'{field}:' in snapshot_code or f'{field} :' in snapshot_code:
            violations.append(f"PositionSnapshot has forbidden field: {field}")
    
    assert not violations, (
        f"❌ 違反 Sprint 1-4.B 鐵律：PositionSnapshot 不應有估值欄位！\n"
        f"發現違規：\n" + "\n".join(f"  - {v}" for v in violations) + "\n"
        f"帳務層 response schema 只包含：\n"
        f"  symbol, asset_ccy, quantity, avg_cost, realized_pnl, cost_basis\n"
        f"估值欄位應在 valuation-service 的 ValuationSnapshot。"
    )
