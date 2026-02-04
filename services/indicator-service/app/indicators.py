def calculate_ma(prices: list[float], window: int) -> list[float]:
    """
    計算移動平均線（Moving Average）。

    Parameters:
    - prices (list[float]): 需要計算的價格列表。
    - window (int): 移動平均線的窗口大小。

    Returns:
    - ma_values (list[float]): 移動平均線結果列表。

    Notes:
    - 這個函數會根據 inputprices 和 window 來計算移動平均線，然後回傳結果列表。
    - 如果 prices 是空列表或window 小於 1，則返回一個空列表。
    """
    if not prices or window < 1:
        return []

    ma_values = []
    
    # 修正邏輯：初始窗口處理需要更嚴謹
    # 使用簡單的切片平均法來確保正確性
    for i in range(len(prices)):
        if i + 1 < window:
            ma_values.append(None) # 或者 0，視需求而定，通常 MA 前面幾天是沒有值的
        else:
            window_slice = prices[i - window + 1 : i + 1]
            avg = sum(window_slice) / window
            ma_values.append(avg)

    return ma_values
