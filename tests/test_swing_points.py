import pandas as pd
import pytest
from sniperbot.strategy.swing_points import SwingPoint, SwingPointDetector


def make_df(prices: list[float]) -> pd.DataFrame:
    """Helper: create M5 OHLCV where highs and lows oscillate around given prices."""
    n = len(prices)
    data = {
        "open": prices,
        "high": [p + 2 for p in prices],
        "low": [p - 2 for p in prices],
        "close": prices,
        "volume": [1000] * n,
    }
    index = pd.date_range("2026-05-21 14:00", periods=n, freq="5min")
    return pd.DataFrame(data, index=index)


class TestSwingPointDetector:
    def test_detects_swing_high_with_min_excursion(self):
        # Peak at index 5 with high=122.0, visible with window_left=5
        prices = [60, 70, 80, 90, 100, 120, 100, 90, 80, 70, 60]
        df = make_df(prices)
        detector = SwingPointDetector(window_left=5, window_right=3, min_excursion=50)
        swings = detector.detect(df)

        highs = [s for s in swings if s.type == "high"]
        assert len(highs) >= 1
        assert any(s.price == 122.0 for s in highs)

    def test_detects_swing_low_with_min_excursion(self):
        # Trough at index 5 with low=58.0, visible with window_left=5
        prices = [120, 110, 100, 90, 80, 60, 80, 90, 100, 110, 120]
        df = make_df(prices)
        detector = SwingPointDetector(window_left=5, window_right=3, min_excursion=50)
        swings = detector.detect(df)

        lows = [s for s in swings if s.type == "low"]
        assert len(lows) >= 1
        assert any(s.price == 58.0 for s in lows)

    def test_filters_swing_below_excursion_threshold(self):
        prices = [100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100]
        df = make_df(prices)
        detector = SwingPointDetector(window_left=5, window_right=3, min_excursion=500)
        swings = detector.detect(df)
        assert len(swings) == 0

    def test_swing_point_has_correct_structure(self):
        prices = [60, 70, 80, 90, 100, 120, 100, 90, 80, 70, 60]
        df = make_df(prices)
        detector = SwingPointDetector(window_left=5, window_right=3, min_excursion=50)
        swings = detector.detect(df)

        for s in swings:
            assert isinstance(s, SwingPoint)
            assert s.type in ("high", "low")
            assert s.price > 0
            assert s.index >= 0
            assert s.excursion_ticks > 0

    def test_empty_dataframe_returns_empty_list(self):
        df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        detector = SwingPointDetector()
        swings = detector.detect(df)
        assert swings == []
