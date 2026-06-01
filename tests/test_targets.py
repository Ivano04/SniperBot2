import pandas as pd
from datetime import datetime
from sniperbot.strategy.swing_points import SwingPoint
from sniperbot.strategy.targets import TargetCalculator, LiquidityLevel


class TestTargetCalculator:
    def test_filters_targets_below_min_distance(self):
        calc = TargetCalculator(min_distance_ticks=40, tick_size=0.25)
        levels = [
            LiquidityLevel(type="high", price=20100.0, source="asia"),
            LiquidityLevel(type="low", price=19950.0, source="asia"),
            LiquidityLevel(type="high", price=20008.0, source="london"),
        ]
        # Entry at 20000.0, min distance = 40 * 0.25 = 10.0 points
        # 20008.0 dist = 8.0 points = 32 ticks -> FILTERED (< 40 ticks)
        result = calc.filter_by_distance(20000.0, levels)
        assert len(result) == 2
        assert all(abs(l.price - 20000.0) >= 10.0 for l in result)

    def test_entries_sorted_by_distance(self):
        calc = TargetCalculator(min_distance_ticks=0, tick_size=0.25)
        levels = [
            LiquidityLevel(type="high", price=20500.0, source="asia"),
            LiquidityLevel(type="high", price=20200.0, source="london"),
            LiquidityLevel(type="high", price=21000.0, source="prev_ny"),
        ]
        result = calc.filter_by_distance(20000.0, levels)
        assert result[0].price == 20200.0
        assert result[1].price == 20500.0
        assert result[2].price == 21000.0

    def test_long_targets_are_above_entry(self):
        calc = TargetCalculator(min_distance_ticks=0, tick_size=0.25)
        swings = [
            SwingPoint(type="high", price=20300.0, index=5,
                       timestamp=datetime(2026, 5, 21, 14, 0), excursion_ticks=150),
            SwingPoint(type="high", price=20600.0, index=10,
                       timestamp=datetime(2026, 5, 21, 15, 0), excursion_ticks=200),
            SwingPoint(type="low", price=19800.0, index=3,
                       timestamp=datetime(2026, 5, 21, 13, 0), excursion_ticks=100),
        ]
        asia = (pd.Timestamp("2026-05-21 00:00"), pd.Timestamp("2026-05-21 09:00"))
        london = (pd.Timestamp("2026-05-21 09:00"), pd.Timestamp("2026-05-21 11:00"))
        prev_ny = (pd.Timestamp("2026-05-20 13:30"), pd.Timestamp("2026-05-20 20:00"))

        targets = calc.get_targets_for_long(20000.0, swings, asia, london, prev_ny)
        assert all(t.price > 20000.0 for t in targets)
        assert targets[0].price <= targets[-1].price

    def test_short_targets_are_below_entry(self):
        calc = TargetCalculator(min_distance_ticks=0, tick_size=0.25)
        swings = [
            SwingPoint(type="low", price=19700.0, index=5,
                       timestamp=datetime(2026, 5, 21, 14, 0), excursion_ticks=150),
            SwingPoint(type="low", price=19400.0, index=10,
                       timestamp=datetime(2026, 5, 21, 15, 0), excursion_ticks=200),
            SwingPoint(type="high", price=20500.0, index=3,
                       timestamp=datetime(2026, 5, 21, 13, 0), excursion_ticks=100),
        ]
        asia = (pd.Timestamp("2026-05-21 00:00"), pd.Timestamp("2026-05-21 09:00"))
        london = (pd.Timestamp("2026-05-21 09:00"), pd.Timestamp("2026-05-21 11:00"))
        prev_ny = (pd.Timestamp("2026-05-20 13:30"), pd.Timestamp("2026-05-20 20:00"))

        targets = calc.get_targets_for_short(20010.0, swings, asia, london, prev_ny)
        assert all(t.price < 20010.0 for t in targets)

    def test_swing_targets_min_40_ticks_from_entry(self):
        calc = TargetCalculator(min_distance_ticks=40, tick_size=0.25)
        swings = [
            SwingPoint(type="high", price=20008.0, index=5,
                       timestamp=datetime(2026, 5, 21, 14, 0), excursion_ticks=150),
            SwingPoint(type="high", price=20200.0, index=10,
                       timestamp=datetime(2026, 5, 21, 15, 0), excursion_ticks=200),
        ]
        targets = calc._filter_swing_targets(20000.0, swings, "high")
        # 20008.0 dist = 8.0 points = 32 ticks -> FILTERED (< 40)
        # 20200.0 dist = 200.0 points = 800 ticks -> KEPT
        assert len(targets) == 1
        assert targets[0].price == 20200.0
