from dataclasses import dataclass, field
import pandas as pd
from sniperbot.strategy.swing_points import SwingPoint


@dataclass
class LiquidityLevel:
    type: str          # 'high' or 'low'
    price: float
    source: str        # 'asia', 'london', 'prev_ny', 'same_level', 'swing_m5'
    distance_ticks: float = 0.0


class TargetCalculator:
    def __init__(self, min_distance_ticks: int = 40, tick_size: float = 0.25):
        self.min_distance_ticks = min_distance_ticks
        self.tick_size = tick_size

    def filter_by_distance(self, entry_price: float,
                           levels: list[LiquidityLevel]) -> list[LiquidityLevel]:
        min_dist = self.min_distance_ticks * self.tick_size
        filtered = []
        for level in levels:
            dist = abs(level.price - entry_price)
            if dist >= min_dist:
                level.distance_ticks = dist / self.tick_size
                filtered.append(level)
        filtered.sort(key=lambda l: l.distance_ticks)
        return filtered

    def _filter_swing_targets(self, entry_price: float, swings: list[SwingPoint],
                              target_type: str) -> list[LiquidityLevel]:
        levels = []
        for s in swings:
            if s.type == target_type:
                levels.append(LiquidityLevel(
                    type=s.type, price=s.price, source="swing_m5"
                ))
        return self.filter_by_distance(entry_price, levels)

    def get_targets_for_long(self, entry_price: float, swing_points: list[SwingPoint],
                             asia_session: tuple[pd.Timestamp, pd.Timestamp],
                             london_session: tuple[pd.Timestamp, pd.Timestamp],
                             prev_ny_session: tuple[pd.Timestamp, pd.Timestamp],
                             asia_df: pd.DataFrame | None = None,
                             london_df: pd.DataFrame | None = None,
                             prev_ny_df: pd.DataFrame | None = None) -> list[LiquidityLevel]:
        levels = []

        for df, source in [(asia_df, "asia"), (london_df, "london"), (prev_ny_df, "prev_ny")]:
            if df is not None and not df.empty:
                session_high = df["high"].max()
                session_low = df["low"].min()
                levels.append(LiquidityLevel(type="high", price=session_high, source=source))
                levels.append(LiquidityLevel(type="low", price=session_low, source=source))

        levels.extend(self._filter_swing_targets(entry_price, swing_points, "high"))

        levels = [l for l in levels if l.price > entry_price]
        return self.filter_by_distance(entry_price, levels)

    def get_targets_for_short(self, entry_price: float, swing_points: list[SwingPoint],
                              asia_session: tuple[pd.Timestamp, pd.Timestamp],
                              london_session: tuple[pd.Timestamp, pd.Timestamp],
                              prev_ny_session: tuple[pd.Timestamp, pd.Timestamp],
                              asia_df: pd.DataFrame | None = None,
                              london_df: pd.DataFrame | None = None,
                              prev_ny_df: pd.DataFrame | None = None) -> list[LiquidityLevel]:
        levels = []

        for df, source in [(asia_df, "asia"), (london_df, "london"), (prev_ny_df, "prev_ny")]:
            if df is not None and not df.empty:
                session_high = df["high"].max()
                session_low = df["low"].min()
                levels.append(LiquidityLevel(type="high", price=session_high, source=source))
                levels.append(LiquidityLevel(type="low", price=session_low, source=source))

        levels.extend(self._filter_swing_targets(entry_price, swing_points, "low"))

        levels = [l for l in levels if l.price < entry_price]
        return self.filter_by_distance(entry_price, levels)
