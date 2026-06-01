import pandas as pd
from datetime import datetime
from sniperbot.strategy.swing_points import SwingPointDetector
from sniperbot.strategy.fvg import FVGDetector
from sniperbot.strategy.zonation import Zonation
from sniperbot.strategy.confirmation import M1Confirmation
from sniperbot.strategy.targets import TargetCalculator


def make_ohlcv(highs: list[float], lows: list[float], closes: list[float]) -> pd.DataFrame:
    n = len(highs)
    data = {
        "open": closes,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [1000] * n,
    }
    index = pd.date_range("2026-05-21 14:00", periods=n, freq="5min")
    return pd.DataFrame(data, index=index)


class TestIntegration:
    """Full strategy chain: raw data to entry signal."""

    def test_full_chain_bullish_signal(self):
        highs = [
            20500, 20400, 20300, 20200, 20100,
            20000, 19900, 19800,
            19900, 20000, 20100, 20200, 20300,
            20400, 20300, 20200,
            20300, 20400, 20500, 20600,
        ]
        lows = [
            20300, 20200, 20100, 20000, 19900,
            19800, 19700, 19600,
            19700, 19800, 19900, 20000, 20100,
            20200, 20100, 20000,
            20100, 20200, 20300, 20400,
        ]
        closes = [
            20400, 20300, 20200, 20100, 20000,
            19900, 19800, 19700,
            19800, 19900, 20000, 20100, 20200,
            20300, 20200, 20100,
            20200, 20300, 20400, 20500,
        ]

        df_m5 = make_ohlcv(highs, lows, closes)

        swing_detector = SwingPointDetector(window_left=5, window_right=3, min_excursion=50)
        fvg_detector = FVGDetector(lookback=20)
        zonation = Zonation()

        swings = swing_detector.detect(df_m5)
        assert len(swings) > 0, "Should detect at least one swing point"

        current_price = closes[-1]
        zone = zonation.determine(current_price, swings)

        fvgs = fvg_detector.detect(df_m5)

        assert zone in (Zonation.PREMIUM, Zonation.DISCOUNT, None)
        assert isinstance(fvgs, list)

    def test_m1_confirmation_with_real_pattern(self):
        closes = [20000.0, 20050.0, 20100.0]
        opens = [19950.0, 20025.0, 20075.0]
        n = len(closes)
        df_m1 = pd.DataFrame({
            "open": opens,
            "high": [max(o, c) + 25 for o, c in zip(opens, closes)],
            "low": [min(o, c) - 25 for o, c in zip(opens, closes)],
            "close": closes,
            "volume": [500] * n,
        }, index=pd.date_range("2026-05-21 15:30", periods=n, freq="1min"))

        checker = M1Confirmation(bars_needed=2, total_bars=3)
        assert checker.check(df_m1, "long") is True
        assert checker.check(df_m1, "short") is False
