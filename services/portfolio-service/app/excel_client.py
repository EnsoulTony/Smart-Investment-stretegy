"""Excel 檔案客戶端（支援本地與遠端檔案）。

提供讀取 Excel 檔案的功能，用於同步交易流水帳。
支援：
- 本地檔案路徑
- 遠端 URL（HTTP/HTTPS）

使用範例：
    # 從 URL 讀取
    client = ExcelClient(source_url="https://example.com/trades.xlsx")
    rows = client.fetch_trades_dicts()
    
    # 從本地檔案讀取
    client = ExcelClient(file_path="/path/to/trades.xlsx")
    rows = client.fetch_trades_dicts()
"""

import os
import tempfile
from typing import List, Dict, Optional
import pandas as pd
import httpx


class ExcelClient:
    """Excel 檔案客戶端。
    
    支援讀取本地或遠端的 Excel 檔案。
    """
    
    def __init__(
        self,
        file_path: Optional[str] = None,
        source_url: Optional[str] = None,
        sheet_name: str = "Sheet1",
        header_row: int = 0
    ):
        """初始化 Excel 客戶端。
        
        Args:
            file_path: 本地 Excel 檔案路徑
            source_url: 遠端 Excel 檔案 URL（HTTP/HTTPS）
            sheet_name: 工作表名稱（預設 "Sheet1"）
            header_row: 標題列的索引（預設 0，即第一列）
        
        Raises:
            ValueError: 當 file_path 和 source_url 都未提供時
        """
        if not file_path and not source_url:
            raise ValueError("必須提供 file_path 或 source_url 其中之一")
        
        self.file_path = file_path
        self.source_url = source_url
        self.sheet_name = sheet_name
        self.header_row = header_row
        self._temp_file: Optional[str] = None
    
    def _download_file(self, url: str) -> str:
        """從 URL 下載檔案到臨時目錄。
        
        Args:
            url: 檔案 URL
        
        Returns:
            str: 臨時檔案路徑
        
        Raises:
            httpx.HTTPError: 下載失敗時
        """
        response = httpx.get(url, follow_redirects=True, timeout=30.0)
        response.raise_for_status()
        
        # 創建臨時檔案
        suffix = ".xlsx"
        if url.lower().endswith(".xls"):
            suffix = ".xls"
        
        temp_file = tempfile.NamedTemporaryFile(
            mode='wb',
            suffix=suffix,
            delete=False
        )
        temp_file.write(response.content)
        temp_file.close()
        
        self._temp_file = temp_file.name
        return temp_file.name
    
    def _get_file_path(self) -> str:
        """取得要讀取的檔案路徑。
        
        如果是遠端 URL，先下載到臨時目錄。
        
        Returns:
            str: 檔案路徑
        """
        if self.file_path:
            if not os.path.exists(self.file_path):
                raise FileNotFoundError(f"Excel 檔案不存在: {self.file_path}")
            return self.file_path
        
        if self.source_url:
            return self._download_file(self.source_url)
        
        raise ValueError("無有效的檔案來源")
    
    def fetch_trades_dicts(self) -> List[Dict[str, str]]:
        """讀取 Excel 檔案並轉換為字典列表。
        
        使用第一列作為 key，後續列作為 value。
        空白列會被跳過。
        
        Returns:
            List[Dict[str, str]]: 每列資料的字典列表
                                 例如：[{'user_id': 'tony', 'symbol': 'AAPL', ...}, ...]
        
        Raises:
            FileNotFoundError: 檔案不存在
            ValueError: Excel 格式錯誤
            httpx.HTTPError: 遠端檔案下載失敗
        """
        try:
            file_path = self._get_file_path()
            
            # 讀取 Excel 檔案
            df = pd.read_excel(
                file_path,
                sheet_name=self.sheet_name,
                header=self.header_row
            )
            
            # 移除完全空白的列
            df = df.dropna(how='all')
            
            # 轉換為字典列表，並將所有值轉為字串
            records = df.fillna('').astype(str).to_dict('records')
            
            return records
            
        finally:
            # 清理臨時檔案
            if self._temp_file and os.path.exists(self._temp_file):
                try:
                    os.unlink(self._temp_file)
                except Exception:
                    pass  # 忽略清理錯誤
    
    def __del__(self):
        """清理臨時檔案。"""
        if hasattr(self, '_temp_file') and self._temp_file and os.path.exists(self._temp_file):
            try:
                os.unlink(self._temp_file)
            except Exception:
                pass
