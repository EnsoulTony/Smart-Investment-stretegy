"""FX 模組規範守門測試（Guardrail Tests）

此測試確保 FX 邊界規範被嚴格遵守：
1. 除 app/fx/** 外，禁止直接讀取 FX_* / VALUATION_* 環境變數
2. 除 app/fx/** 外，禁止直接 import provider 實作
3. 唯一允許入口：from app.fx import get_fx_provider

⚠️ 此測試是「守門員」：一旦有人違規，CI 立刻失敗。
"""
import ast
import os
from pathlib import Path
import pytest


# 禁止的環境變數前綴
FORBIDDEN_ENV_PREFIXES = ['FX_', 'VALUATION_']

# 禁止的 import 模式
FORBIDDEN_IMPORTS = [
    'app.fx.stub_provider',
    'app.fx.interfaces',
    'app.fx.types',
]

# 允許的 import（白名單）
ALLOWED_IMPORTS = [
    'app.fx',  # 僅允許 from app.fx import get_fx_provider
]


class EnvVarVisitor(ast.NodeVisitor):
    """AST 訪問器：檢測環境變數讀取"""
    
    def __init__(self):
        self.violations = []
    
    def visit_Call(self, node):
        """檢查 os.getenv() / os.environ.get() 等呼叫"""
        # os.getenv('FX_PROVIDER')
        if (isinstance(node.func, ast.Attribute) and
            isinstance(node.func.value, ast.Name) and
            node.func.value.id == 'os' and
            node.func.attr in ['getenv', 'environ']):
            
            if node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant):
                    env_name = arg.value
                    if any(env_name.startswith(prefix) for prefix in FORBIDDEN_ENV_PREFIXES):
                        self.violations.append({
                            'line': node.lineno,
                            'type': 'env_access',
                            'detail': f"直接讀取環境變數 '{env_name}'"
                        })
        
        # os.environ['FX_PROVIDER']
        if (isinstance(node.func, ast.Attribute) and
            node.func.attr == 'get'):
            if (isinstance(node.func.value, ast.Subscript) and
                isinstance(node.func.value.value, ast.Attribute) and
                isinstance(node.func.value.value.value, ast.Name) and
                node.func.value.value.value.id == 'os' and
                node.func.value.value.attr == 'environ'):
                
                if isinstance(node.func.value.slice, ast.Constant):
                    env_name = node.func.value.slice.value
                    if any(env_name.startswith(prefix) for prefix in FORBIDDEN_ENV_PREFIXES):
                        self.violations.append({
                            'line': node.lineno,
                            'type': 'env_access',
                            'detail': f"直接讀取環境變數 '{env_name}'"
                        })
        
        self.generic_visit(node)
    
    def visit_Subscript(self, node):
        """檢查 os.environ['FX_PROVIDER']"""
        if (isinstance(node.value, ast.Attribute) and
            isinstance(node.value.value, ast.Name) and
            node.value.value.id == 'os' and
            node.value.attr == 'environ'):
            
            if isinstance(node.slice, ast.Constant):
                env_name = node.slice.value
                if any(env_name.startswith(prefix) for prefix in FORBIDDEN_ENV_PREFIXES):
                    self.violations.append({
                        'line': node.lineno,
                        'type': 'env_access',
                        'detail': f"直接讀取環境變數 '{env_name}'"
                    })
        
        self.generic_visit(node)


class ImportVisitor(ast.NodeVisitor):
    """AST 訪問器：檢測 import 語句"""
    
    def __init__(self):
        self.violations = []
    
    def visit_Import(self, node):
        """檢查 import app.fx.stub_provider"""
        for alias in node.names:
            if any(alias.name.startswith(forbidden) for forbidden in FORBIDDEN_IMPORTS):
                self.violations.append({
                    'line': node.lineno,
                    'type': 'forbidden_import',
                    'detail': f"禁止直接 import '{alias.name}'"
                })
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node):
        """檢查 from app.fx.stub_provider import ..."""
        if node.module:
            # 檢查是否為禁止的 import
            if any(node.module.startswith(forbidden) for forbidden in FORBIDDEN_IMPORTS):
                self.violations.append({
                    'line': node.lineno,
                    'type': 'forbidden_import',
                    'detail': f"禁止直接 from {node.module} import ..."
                })
        self.generic_visit(node)


def get_app_python_files():
    """取得所有需要檢查的 Python 檔案（排除 app/fx/**）"""
    app_dir = Path(__file__).parent.parent / 'app'
    fx_dir = app_dir / 'fx'
    
    python_files = []
    for py_file in app_dir.rglob('*.py'):
        # 排除 fx 目錄內的檔案
        if fx_dir in py_file.parents or py_file.parent == fx_dir:
            continue
        # 排除 __pycache__
        if '__pycache__' in py_file.parts:
            continue
        python_files.append(py_file)
    
    return python_files


def check_file_violations(file_path: Path):
    """檢查單一檔案的違規情況"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content, filename=str(file_path))
        
        # 檢查環境變數讀取
        env_visitor = EnvVarVisitor()
        env_visitor.visit(tree)
        
        # 檢查 import
        import_visitor = ImportVisitor()
        import_visitor.visit(tree)
        
        violations = env_visitor.violations + import_visitor.violations
        return violations
    
    except SyntaxError:
        # 語法錯誤由其他測試處理
        return []


class TestFxGuardrails:
    """FX 模組邊界規範測試"""
    
    def test_no_direct_fx_env_access_outside_fx_module(self):
        """測試：app/fx/** 以外禁止直接讀取 FX_* / VALUATION_* 環境變數"""
        python_files = get_app_python_files()
        
        assert len(python_files) > 0, "應該至少有一些 Python 檔案需要檢查"
        
        all_violations = {}
        for py_file in python_files:
            violations = check_file_violations(py_file)
            env_violations = [v for v in violations if v['type'] == 'env_access']
            if env_violations:
                rel_path = py_file.relative_to(Path(__file__).parent.parent)
                all_violations[str(rel_path)] = env_violations
        
        if all_violations:
            error_msg = "\n🚨 違反 FX 邊界規範：檢測到直接讀取環境變數\n\n"
            for file_path, violations in all_violations.items():
                error_msg += f"檔案: {file_path}\n"
                for v in violations:
                    error_msg += f"  ❌ 第 {v['line']} 行: {v['detail']}\n"
                error_msg += "\n"
            
            error_msg += "💡 修正方式：\n"
            error_msg += "  1. 移除直接的環境變數讀取\n"
            error_msg += "  2. 使用 'from app.fx import get_fx_provider' 取得 FX 服務\n"
            error_msg += "  3. 環境變數讀取應該只在 app/fx/ 模組內進行\n"
            
            pytest.fail(error_msg)
    
    def test_no_direct_provider_import_outside_fx_module(self):
        """測試：app/fx/** 以外禁止直接 import provider 實作"""
        python_files = get_app_python_files()
        
        all_violations = {}
        for py_file in python_files:
            violations = check_file_violations(py_file)
            import_violations = [v for v in violations if v['type'] == 'forbidden_import']
            if import_violations:
                rel_path = py_file.relative_to(Path(__file__).parent.parent)
                all_violations[str(rel_path)] = import_violations
        
        if all_violations:
            error_msg = "\n🚨 違反 FX 邊界規範：檢測到直接 import provider 實作\n\n"
            for file_path, violations in all_violations.items():
                error_msg += f"檔案: {file_path}\n"
                for v in violations:
                    error_msg += f"  ❌ 第 {v['line']} 行: {v['detail']}\n"
                error_msg += "\n"
            
            error_msg += "💡 修正方式：\n"
            error_msg += "  1. 移除直接 import provider 的程式碼\n"
            error_msg += "  2. 使用 'from app.fx import get_fx_provider' 作為唯一入口\n"
            error_msg += "  3. Provider 實作只應在 app/fx/ 模組內被使用\n"
            
            pytest.fail(error_msg)
    
    def test_fx_module_exists_and_has_public_api(self):
        """測試：確認 fx 模組存在且有正確的 public API"""
        fx_init = Path(__file__).parent.parent / 'app' / 'fx' / '__init__.py'
        assert fx_init.exists(), "app/fx/__init__.py 不存在"
        
        # 檢查 __init__.py 有 export get_fx_provider
        with open(fx_init, 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert 'get_fx_provider' in content, "__init__.py 應該定義 get_fx_provider"
        assert '__all__' in content, "__init__.py 應該定義 __all__"
        assert "'get_fx_provider'" in content or '"get_fx_provider"' in content, \
            "__all__ 應該包含 'get_fx_provider'"


class TestGuardrailEffectiveness:
    """測試 Guardrail 本身是否有效"""
    
    def test_guardrail_can_detect_env_access_violation(self, tmp_path):
        """測試：Guardrail 能夠檢測到環境變數讀取違規"""
        # 建立一個違規的測試檔案
        test_file = tmp_path / "violation.py"
        test_file.write_text("""
import os

def bad_function():
    fx_provider = os.getenv('FX_PROVIDER')
    return fx_provider
""")
        
        violations = check_file_violations(test_file)
        assert len(violations) > 0, "應該檢測到違規"
        assert any(v['type'] == 'env_access' for v in violations), "應該檢測到環境變數讀取"
    
    def test_guardrail_can_detect_import_violation(self, tmp_path):
        """測試：Guardrail 能夠檢測到 import 違規"""
        # 建立一個違規的測試檔案
        test_file = tmp_path / "violation.py"
        test_file.write_text("""
from app.fx.stub_provider import StubFxProvider

def bad_function():
    provider = StubFxProvider()
    return provider
""")
        
        violations = check_file_violations(test_file)
        assert len(violations) > 0, "應該檢測到違規"
        assert any(v['type'] == 'forbidden_import' for v in violations), "應該檢測到 import 違規"
    
    def test_guardrail_allows_correct_usage(self, tmp_path):
        """測試：Guardrail 允許正確的用法"""
        # 建立一個合規的測試檔案
        test_file = tmp_path / "correct.py"
        test_file.write_text("""
from app.fx import get_fx_provider
from decimal import Decimal

def good_function():
    fx = get_fx_provider()
    rate = fx.get_rate('USD', 'TWD')
    return rate
""")
        
        violations = check_file_violations(test_file)
        assert len(violations) == 0, "正確的用法不應被標記為違規"
