import unittest
from indicators import calculate_ma

class TestIndicators(unittest.TestCase):
    def test_calculate_ma_normal(self):
        """正常數據測試"""
        prices = [10.0, 20.0, 30.0, 40.0, 50.0]
        window = 3
        result = calculate_ma(prices, window)
        
        self.assertEqual(len(result), len(prices))
        self.assertIsNone(result[0])
        self.assertIsNone(result[1])
        self.assertAlmostEqual(result[2], 20.0)
        self.assertAlmostEqual(result[3], 30.0)
        self.assertAlmostEqual(result[4], 40.0)

    def test_calculate_ma_empty(self):
        """空列表測試"""
        prices = []
        window = 3
        result = calculate_ma(prices, window)
        self.assertEqual(result, [])

    def test_calculate_ma_window_larger_than_data(self):
        """窗口大於數據長度測試"""
        prices = [1.0, 2.0]
        window = 5
        result = calculate_ma(prices, window)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(x is None for x in result))

    def test_calculate_ma_window_1(self):
        """窗口為 1 的邊界測試"""
        prices = [1.0, 2.0, 3.0]
        window = 1
        result = calculate_ma(prices, window)
        self.assertEqual(result, prices)

if __name__ == '__main__':
    unittest.main()
