import pandas as pd
from datetime import datetime
from sniperbot.strategy.swing_points import SwingPoint
from sniperbot.strategy.zonation import Zonation

# Test constants
PREMIUM = "premium"
DISCOUNT = "discount"


class TestZonation:
    def test_premium_zone_triggers_short_only(self):
        swings = [
            SwingPoint(type="high", price=400.0, index=5,
                       timestamp=datetime(2026, 5, 21, 14, 0), excursion_ticks=150),
            SwingPoint(type="low", price=350.0, index=10,
                       timestamp=datetime(2026, 5, 21, 14, 30), excursion_ticks=150),
        ]
        zonation = Zonation()
        # 50% of range = (400 + 350) / 2 = 375
        # Price at 380: above 375 and below 400 -> PREMIUM
        result = zonation.determine(380.0, swings)
        assert result == PREMIUM

    def test_discount_zone_triggers_long_only(self):
        swings = [
            SwingPoint(type="high", price=400.0, index=5,
                       timestamp=datetime(2026, 5, 21, 14, 0), excursion_ticks=150),
            SwingPoint(type="low", price=350.0, index=10,
                       timestamp=datetime(2026, 5, 21, 14, 30), excursion_ticks=150),
        ]
        zonation = Zonation()
        # 50% of range = 375
        # Price at 360: below 375 and above 350 -> DISCOUNT
        result = zonation.determine(360.0, swings)
        assert result == DISCOUNT

    def test_returns_none_when_no_valid_swings(self):
        zonation = Zonation()
        result = zonation.determine(380.0, [])
        assert result is None

    def test_returns_none_when_price_outside_swing_range(self):
        swings = [
            SwingPoint(type="high", price=400.0, index=5,
                       timestamp=datetime(2026, 5, 21, 14, 0), excursion_ticks=150),
            SwingPoint(type="low", price=350.0, index=10,
                       timestamp=datetime(2026, 5, 21, 14, 30), excursion_ticks=150),
        ]
        zonation = Zonation()
        assert zonation.determine(410.0, swings) is None
        assert zonation.determine(340.0, swings) is None

    def test_uses_most_significant_swings_for_range(self):
        swings = [
            SwingPoint(type="high", price=410.0, index=2,
                       timestamp=datetime(2026, 5, 21, 13, 0), excursion_ticks=100),
            SwingPoint(type="high", price=400.0, index=5,
                       timestamp=datetime(2026, 5, 21, 14, 0), excursion_ticks=500),
            SwingPoint(type="low", price=360.0, index=8,
                       timestamp=datetime(2026, 5, 21, 14, 20), excursion_ticks=100),
            SwingPoint(type="low", price=350.0, index=10,
                       timestamp=datetime(2026, 5, 21, 14, 30), excursion_ticks=500),
        ]
        zonation = Zonation()
        # Most significant: high=400 (excursion 500), low=350 (excursion 500)
        # 50% = 375
        result = zonation.determine(360.0, swings)
        assert result == DISCOUNT
