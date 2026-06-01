from dataclasses import dataclass
from datetime import datetime
import pandas as pd


@dataclass
class SwingPoint:
    type: str           # 'high' or 'low'
    price: float
    index: int
    timestamp: datetime
    excursion_ticks: float


class SwingPointDetector:
    def __init__(self, window_left: int = 5, window_right: int = 3,
                 min_excursion: float = 2.5):
        self.window_left = window_left
        self.window_right = window_right
        self.min_excursion = min_excursion

    def detect(self, df: pd.DataFrame) -> list[SwingPoint]:
        if len(df) < self.window_left + self.window_right + 1:
            return []

        swings = []
        n = len(df)

        for i in range(self.window_left, n - self.window_right):
            high_i = df["high"].iloc[i]
            low_i = df["low"].iloc[i]
            ts = df.index[i]

            # Check swing high
            left_highs = df["high"].iloc[i - self.window_left:i]
            right_highs = df["high"].iloc[i + 1:i + 1 + self.window_right]
            if all(high_i > left_highs) and all(high_i > right_highs):
                local_low = min(
                    df["low"].iloc[i - self.window_left:i + self.window_right + 1]
                )
                excursion = high_i - local_low
                if excursion >= self.min_excursion:
                    swings.append(SwingPoint(
                        type="high", price=high_i, index=i,
                        timestamp=ts.to_pydatetime(), excursion_ticks=excursion,
                    ))

            # Check swing low
            left_lows = df["low"].iloc[i - self.window_left:i]
            right_lows = df["low"].iloc[i + 1:i + 1 + self.window_right]
            if all(low_i < left_lows) and all(low_i < right_lows):
                local_high = max(
                    df["high"].iloc[i - self.window_left:i + self.window_right + 1]
                )
                excursion = local_high - low_i
                if excursion >= self.min_excursion:
                    swings.append(SwingPoint(
                        type="low", price=low_i, index=i,
                        timestamp=ts.to_pydatetime(), excursion_ticks=excursion,
                    ))

        return swings
