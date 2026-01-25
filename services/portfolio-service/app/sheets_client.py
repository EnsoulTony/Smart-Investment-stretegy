"""Google Sheets 客戶端（Service Account 認證）。

提供讀取 Google Sheets 的功能，用於同步交易流水帳。
認證方式：Service Account JSON（從檔案路徑 GOOGLE_SA_JSON_PATH 讀取）

使用範例：
    client = SheetsClient()
    rows = client.fetch_trades_rows()
    # rows[0] 為 header，rows[1:] 為資料列
"""

import os
import json
from typing import List, Dict, Any
import gspread
from google.oauth2.service_account import Credentials


class SheetsClient:
    """Google Sheets 客戶端。
    
    使用 Service Account 認證，讀取指定的 Google Sheets 試算表。
    """
    
    # Google Sheets API 所需的權限範圍
    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets.readonly',
        'https://www.googleapis.com/auth/drive.readonly'
    ]
    
    def __init__(self):
        """初始化 Sheets 客戶端。
        
        從環境變數讀取：
        - GOOGLE_SA_JSON_PATH: Service Account JSON 檔案路徑（推薦）
        - GOOGLE_SA_JSON: Service Account JSON 字串（已棄用，避免洩漏）
        - GOOGLE_SHEET_ID: Google Sheets 試算表 ID
        - GOOGLE_SHEET_TRADES_TAB: 交易流水帳的分頁名稱（預設 "trades"）
        
        Raises:
            ValueError: 當必要的環境變數缺失時
            json.JSONDecodeError: 當 GOOGLE_SA_JSON 格式不正確時
        """
        self.sa_json_path = os.getenv("GOOGLE_SA_JSON_PATH")
        self.sa_json_str = os.getenv("GOOGLE_SA_JSON")
        self.sheet_id = os.getenv("GOOGLE_SHEET_ID")
        self.trades_tab_name = os.getenv("GOOGLE_SHEET_TRADES_TAB", "trades")
        
        if self.sa_json_path:
            if not os.path.exists(self.sa_json_path):
                raise ValueError("GOOGLE_SA_JSON_PATH 指向的檔案不存在")
            with open(self.sa_json_path, "r", encoding="utf-8") as f:
                self.sa_json_str = f.read()
        if not self.sa_json_str:
            raise ValueError("需提供 GOOGLE_SA_JSON_PATH（推薦）或 GOOGLE_SA_JSON（已棄用）")
        if not self.sheet_id:
            raise ValueError("環境變數 GOOGLE_SHEET_ID 未設定")
        
        # 解析 Service Account JSON
        try:
            self.sa_info = json.loads(self.sa_json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"GOOGLE_SA_JSON 格式錯誤：{e}")
        
        # 建立認證與客戶端
        self._credentials = None
        self._client = None
    
    def _get_client(self) -> gspread.Client:
        """取得 gspread 客戶端（lazy initialization）。
        
        Returns:
            gspread.Client: 已認證的 gspread 客戶端
        """
        if self._client is None:
            self._credentials = Credentials.from_service_account_info(
                self.sa_info,
                scopes=self.SCOPES
            )
            self._client = gspread.authorize(self._credentials)
        return self._client
    
    def fetch_trades_rows(self) -> List[List[str]]:
        """讀取交易流水帳分頁的所有列。
        
        Returns:
            List[List[str]]: 所有列的資料，包含 header（第一列）
                            例如：[['日期', '股票', '數量', ...], ['2026-01-20', 'AAPL', '100', ...], ...]
        
        Raises:
            gspread.exceptions.SpreadsheetNotFound: 試算表不存在或無權限
            gspread.exceptions.WorksheetNotFound: 分頁不存在
        """
        client = self._get_client()
        spreadsheet = client.open_by_key(self.sheet_id)
        worksheet = spreadsheet.worksheet(self.trades_tab_name)
        
        # 取得所有列（包含 header）
        all_rows = worksheet.get_all_values()
        
        return all_rows
    
    def fetch_trades_dicts(self) -> List[Dict[str, str]]:
        """讀取交易流水帳分頁，並將每列轉為字典。
        
        使用第一列作為 key，後續列作為 value。
        空白列會被跳過。
        
        Returns:
            List[Dict[str, str]]: 每列資料的字典列表
                                 例如：[{'日期': '2026-01-20', '股票': 'AAPL', ...}, ...]
        """
        client = self._get_client()
        spreadsheet = client.open_by_key(self.sheet_id)
        worksheet = spreadsheet.worksheet(self.trades_tab_name)
        
        # 使用 gspread 內建的 get_all_records() 自動處理 header
        # 這會跳過空白列
        records = worksheet.get_all_records()
        
        return records
