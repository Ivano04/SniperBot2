import pandas as pd


class M1Confirmation:
    """2/3 M1 candle confirmation for ICT strategy.

    After an M5 candle closes inside a FVG, we wait for the next N M1 candles
    and apply the bars_needed / total_bars rule: at least `bars_needed` of the
    last `total_bars` must be bullish (for LONG) or bearish (for SHORT).
    """

    def __init__(self, bars_needed: int = 2, total_bars: int = 3):
        self.bars_needed = bars_needed
        self.total_bars = total_bars

    def check(self, df_m1: pd.DataFrame, direction: str) -> bool:
        if len(df_m1) < self.total_bars:
            return False

        # Take the last N bars
        bars = df_m1.iloc[-self.total_bars:]

        if direction == "long":
            bull_count = sum(
                1 for _, row in bars.iterrows() if row["close"] > row["open"]
            )
            return bull_count >= self.bars_needed
        elif direction == "short":
            bear_count = sum(
                1 for _, row in bars.iterrows() if row["close"] < row["open"]
            )
            return bear_count >= self.bars_needed
        else:
            return False
