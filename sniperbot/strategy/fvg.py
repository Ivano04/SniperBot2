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
        # Limita la scansione al lookback configurato per massima efficienza.
        # len(df)-3 garantisce che C3 (i+2) sia sempre una candela già chiusa,
        # mai quella in formazione (ultima barra del DataFrame).
        start_idx = max(0, len(df) - self.lookback)

        for i in range(start_idx, len(df) - 3):
            ts = df.index[i]

            # 1. CORRETTO BULLISH FVG: Il massimo di C1 è inferiore al minimo di C3
            # Il mercato si è espanso verso l'alto lasciando un'inefficienza vuota.
            if df["high"].iloc[i] < df["low"].iloc[i + 2]:
                fvgs.append(FVG(
                    type="bullish",
                    top=df["low"].iloc[i + 2],   # Il minimo di C3 è il tetto del gap
                    bottom=df["high"].iloc[i],  # Il massimo di C1 è il fondo del gap
                    start_index=i,
                    start_timestamp=ts.to_pydatetime(),
                ))

            # 2. CORRETTO BEARISH FVG: Il minimo di C1 è superiore al massimo di C3
            # Il mercato è crollato verso il basso lasciando un'inefficienza vuota.
            elif df["low"].iloc[i] > df["high"].iloc[i + 2]:
                fvgs.append(FVG(
                    type="bearish",
                    top=df["low"].iloc[i],       # Il minimo di C1 è il tetto del gap
                    bottom=df["high"].iloc[i + 2], # Il massimo di C3 è il fondo del gap
                    start_index=i,
                    start_timestamp=ts.to_pydatetime(),
                ))

        return fvgs

    def is_price_inside(self, price: float, fvg: FVG) -> bool:
        return fvg.bottom <= price <= fvg.top

    def update_closure(self, fvgs: list[FVG], df_recent: pd.DataFrame) -> list[FVG]:
        if df_recent.empty:
            return fvgs

        for fvg in fvgs:
            if fvg.closed:
                continue

            # Find the FVG's current position in this DataFrame by timestamp
            # (start_index is volatile across fetch cycles — timestamp is stable)
            try:
                start_pos = df_recent.index.get_loc(fvg.start_timestamp)
            except KeyError:
                continue  # bar no longer in DataFrame

            # Un FVG può essere chiuso solo dalle candele SUCCESSIVE alla sua formazione (C+3)
            start = start_pos + 3
            if start >= len(df_recent):
                continue

            for i in range(start, len(df_recent)):
                # Recuperiamo i minimi e massimi assoluti (corpi o ombre) delle candele successive
                low_price = df_recent["low"].iloc[i]
                high_price = df_recent["high"].iloc[i + 2] if (i + 2) < len(df_recent) else df_recent["high"].iloc[i]

                if fvg.type == "bullish":
                    # Un FVG Rialzista è chiuso se il minimo di una candela successiva 
                    # scende a coprire interamente il gap (raggiungendo o superando il bottom)
                    if df_recent["low"].iloc[i] <= fvg.bottom:
                        fvg.closed = True
                        break
                else:
                    # Un FVG Ribassista è chiuso se il massimo di una candela successiva 
                    # sale a coprire interamente il gap (raggiungendo o superando il top)
                    if df_recent["high"].iloc[i] >= fvg.top:
                        fvg.closed = True
                        break

        return fvgs