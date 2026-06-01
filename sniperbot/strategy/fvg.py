from dataclasses import dataclass
from datetime import datetime
import pandas as pd


@dataclass
class FVG:
    type: str          # 'bullish' or 'bearish'
    top: float          # upper bound of the gap
    bottom: float       # lower bound of the gap
    start_index: int
    start_timestamp: datetime
    closed: bool = False


class FVGDetector:
    def __init__(self, lookback: int = 300):
        self.lookback = lookback

    def detect(self, df: pd.DataFrame) -> list[FVG]:
        if len(df) < 3:
            return []

        fvgs = []
        # Scan all bars — FVGs have no expiry, they persist until closed
        start_idx = 0

        for i in range(start_idx, len(df) - 2):
            ts = df.index[i]

            # Bullish FVG: low[i] > high[i+2]
            if df["low"].iloc[i] > df["high"].iloc[i + 2]:
                fvgs.append(FVG(
                    type="bullish",
                    top=df["low"].iloc[i],
                    bottom=df["high"].iloc[i + 2],
                    start_index=i,
                    start_timestamp=ts.to_pydatetime(),
                ))

            # Bearish FVG: high[i] < low[i+2]
            if df["high"].iloc[i] < df["low"].iloc[i + 2]:
                fvgs.append(FVG(
                    type="bearish",
                    top=df["low"].iloc[i + 2],
                    bottom=df["high"].iloc[i],
                    start_index=i,
                    start_timestamp=ts.to_pydatetime(),
                ))

        return fvgs

    def is_price_inside(self, price: float, fvg: FVG) -> bool:
        return fvg.bottom < price < fvg.top

    def update_closure(self, fvgs: list[FVG], df_recent: pd.DataFrame) -> list[FVG]:
        if df_recent.empty:
            return fvgs

        for fvg in fvgs:
            if fvg.closed:
                continue
            # Only check bars AFTER the FVG was created
            start = fvg.start_index + 3
            for i in range(start, len(df_recent)):
                close = df_recent["close"].iloc[i]
                if fvg.type == "bullish":
                    if close <= fvg.bottom:
                        fvg.closed = True
                        break
                else:
                    if close >= fvg.top:
                        fvg.closed = True
                        break

        return fvgs
