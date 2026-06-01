import pandas as pd
import pytest
from sniperbot.strategy.fvg import FVG, FVGDetector


def make_df(highs: list[float], lows: list[float]) -> pd.DataFrame:
    n = len(highs)
    data = {
        "open": [(h + l) / 2 for h, l in zip(highs, lows)],
        "high": highs,
        "low": lows,
        "close": [(h + l) / 2 for h, l in zip(highs, lows)],
        "volume": [1000] * n,
    }
    index = pd.date_range("2026-05-21 14:00", periods=n, freq="5min")
    return pd.DataFrame(data, index=index)


class TestFVGDetector:
    def test_detects_bullish_fvg(self):
        # Bullish: low[i] > high[i+2]
        highs = [310, 308, 305, 307, 308]
        lows = [309, 307, 304, 306, 307]
        df = make_df(highs, lows)
        detector = FVGDetector(lookback=10)
        fvgs = detector.detect(df)

        bullish = [f for f in fvgs if f.type == "bullish"]
        assert len(bullish) >= 1
        fvg = bullish[0]
        assert fvg.bottom == 305.0  # high[i+2]
        assert fvg.top == 309.0     # low[i]

    def test_detects_bearish_fvg(self):
        # Bearish: high[i] < low[i+2]
        highs = [305, 307, 308, 307, 308]
        lows = [304, 306, 308, 306, 307]
        df = make_df(highs, lows)
        detector = FVGDetector(lookback=10)
        fvgs = detector.detect(df)

        bearish = [f for f in fvgs if f.type == "bearish"]
        assert len(bearish) >= 1
        fvg = bearish[0]
        assert fvg.top == 308.0    # low[i+2]
        assert fvg.bottom == 305.0  # high[i]

    def test_no_fvg_when_candles_overlap(self):
        highs = [310, 310, 310, 310, 310]
        lows = [305, 305, 305, 305, 305]
        df = make_df(highs, lows)
        detector = FVGDetector(lookback=10)
        fvgs = detector.detect(df)
        assert len(fvgs) == 0

    def test_price_inside_bullish_fvg(self):
        fvg = FVG(type="bullish", top=310.0, bottom=305.0, start_index=0,
                  start_timestamp=pd.Timestamp("2026-05-21 14:00"))
        detector = FVGDetector()
        assert detector.is_price_inside(307.0, fvg) is True
        assert detector.is_price_inside(312.0, fvg) is False
        assert detector.is_price_inside(303.0, fvg) is False

    def test_price_inside_bearish_fvg(self):
        fvg = FVG(type="bearish", top=310.0, bottom=305.0, start_index=0,
                  start_timestamp=pd.Timestamp("2026-05-21 14:00"))
        detector = FVGDetector()
        assert detector.is_price_inside(307.0, fvg) is True
        assert detector.is_price_inside(312.0, fvg) is False

    def test_fvg_closed_when_price_traverses_entire_gap(self):
        fvg = FVG(type="bullish", top=310.0, bottom=305.0, start_index=0,
                  start_timestamp=pd.Timestamp("2026-05-21 14:00"))
        later_highs = [306, 304, 303, 302, 302]
        later_lows = [305, 303, 302, 301, 301]
        df_later = make_df(later_highs, later_lows)
        detector = FVGDetector()
        detector.update_closure([fvg], df_later)
        assert fvg.closed is True

    def test_fvg_not_closed_when_price_does_not_cross_entire_gap(self):
        fvg = FVG(type="bullish", top=310.0, bottom=305.0, start_index=0,
                  start_timestamp=pd.Timestamp("2026-05-21 14:00"))
        later_highs = [308, 307, 308, 307, 308]
        later_lows = [306, 306, 306, 306, 307]
        df_later = make_df(later_highs, later_lows)
        detector = FVGDetector()
        detector.update_closure([fvg], df_later)
        assert fvg.closed is False

    def test_lookback_limit_respected(self):
        highs = [310, 308, 305, 307, 308, 310, 308, 305, 307, 308]
        lows = [309, 307, 304, 306, 307, 309, 307, 304, 306, 307]
        df = make_df(highs, lows)
        detector = FVGDetector(lookback=3)
        fvgs = detector.detect(df)
        for f in fvgs:
            assert f.start_index >= len(df) - 3
