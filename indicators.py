import numpy as np
import pandas as pd


def bollinger_bands(df: pd.DataFrame, period: int = 20, stds: float = 2.0, ddof: int = 0):
    # df columns: open_time, open, high, low, close, volume
    close = df["close"].astype(float)
    mid = close.rolling(window=period, min_periods=period).mean()
    std = close.rolling(window=period, min_periods=period).std(ddof=ddof)
    up = mid + stds * std
    dn = mid - stds * std
    return mid, up, dn