import subprocess
import json
import os

class MarketScanner:
    def __init__(self):
        # 設定 cache 檔案路徑
        self.cache_path = "/Users/macminione/.openclaw/workspace/skills/stock-analysis/cache/hot_scan_latest.json"
        # 設定腳本路徑
        self.script_path = "skills/stock-analysis/scripts/hot_scanner.py"

    def refresh_data(self):
        """執行外部腳本更新熱門數據"""
        try:
            print("正在更新市場熱門數據...")
            # 使用 uv run 執行，並隱藏 stdout 避免干擾
            subprocess.run(
                ["uv", "run", self.script_path], 
                check=True, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
            print("更新完成！")
        except subprocess.CalledProcessError as e:
            print(f"更新數據失敗: {e}")

    def get_hot_tickers(self, refresh=True):
        """取得熱門股票代號"""
        if refresh:
            self.refresh_data()

        try:
            if not os.path.exists(self.cache_path):
                print(f"Cache file not found: {self.cache_path}")
                return []

            with open(self.cache_path, 'r') as f:
                data = json.load(f)
            
            # 從結果中提取前 5 名
            # 假設 JSON 結構有 'trending' 欄位，這需要根據實際檔案確認
            # 如果沒有 'trending'，我們可能需要看整個 JSON 結構
            # 這裡先假設有，如果報錯我們再修
            
            hot_list = []
            
            # 嘗試從不同來源提取
            if 'top_trending' in data:
                hot_list.extend([item['symbol'] for item in data['top_trending'][:5]])
            elif 'stock_highlights' in data:
                 hot_list.extend([item['symbol'] for item in data['stock_highlights'][:5]])
            
            return hot_list

        except json.JSONDecodeError:
            print("JSON 解析失敗")
            return []
        except Exception as e:
            print(f"讀取熱門數據時發生錯誤: {e}")
            return []

# 測試用
if __name__ == "__main__":
    scanner = MarketScanner()
    # 先試著讀取現有檔案看看結構，不強制更新
    result = scanner.get_hot_tickers(refresh=False) 
    print(f"熱門標的: {result}")
