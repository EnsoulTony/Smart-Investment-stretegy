import sys
from pathlib import Path

# 將服務根目錄加入 import 路徑，讓 `from app.main import app` 可用
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
