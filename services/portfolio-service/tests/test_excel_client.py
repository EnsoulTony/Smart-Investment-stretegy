"""測試 Excel 客戶端。

測試從遠端 URL 和本地檔案讀取 Excel。
"""

import pytest
from unittest.mock import Mock, patch
from app.excel_client import ExcelClient


class TestExcelClient:
    """測試 Excel 客戶端功能。"""
    
    def test_init_with_file_path(self):
        """測試使用檔案路徑初始化。"""
        client = ExcelClient(file_path="/path/to/file.xlsx")
        assert client.file_path == "/path/to/file.xlsx"
        assert client.source_url is None
    
    def test_init_with_url(self):
        """測試使用 URL 初始化。"""
        client = ExcelClient(source_url="https://example.com/trades.xlsx")
        assert client.source_url == "https://example.com/trades.xlsx"
        assert client.file_path is None
    
    def test_init_without_source_raises_error(self):
        """測試未提供來源時拋出錯誤。"""
        with pytest.raises(ValueError, match="必須提供 file_path 或 source_url"):
            ExcelClient()
    
    @patch('app.excel_client.httpx.get')
    @patch('app.excel_client.pd.read_excel')
    def test_fetch_from_url(self, mock_read_excel, mock_get):
        """測試從 URL 讀取 Excel。"""
        # Mock HTTP response
        mock_response = Mock()
        mock_response.content = b'fake excel content'
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        # Mock pandas DataFrame
        mock_df = Mock()
        mock_df.dropna.return_value = mock_df
        mock_df.fillna.return_value = mock_df
        mock_df.astype.return_value = mock_df
        mock_df.to_dict.return_value = [
            {'user_id': 'tony', 'symbol': 'AAPL', 'quantity': '100'},
            {'user_id': 'tony', 'symbol': 'GOOGL', 'quantity': '50'}
        ]
        mock_read_excel.return_value = mock_df
        
        # Test
        client = ExcelClient(source_url="https://example.com/trades.xlsx")
        records = client.fetch_trades_dicts()
        
        assert len(records) == 2
        assert records[0]['symbol'] == 'AAPL'
        assert records[1]['symbol'] == 'GOOGL'
        
        # Verify httpx.get was called
        mock_get.assert_called_once()
        assert 'example.com/trades.xlsx' in str(mock_get.call_args)
