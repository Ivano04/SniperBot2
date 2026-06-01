import pandas as pd
import pytest
from sniperbot.strategy.confirmation import M1Confirmation


def make_m1_df(closes: list[float], opens: list[float] | None = None) -> pd.DataFrame:
    if opens is None:
        opens = closes
    n = len(closes)
    data = {
        "open": opens,
        "high": [max(o, c) + 0.5 for o, c in zip(opens, closes)],
        "low": [min(o, c) - 0.5 for o, c in zip(opens, closes)],
        "close": closes,
        "volume": [1000] * n,
    }
    index = pd.date_range("2026-05-21 15:00", periods=n, freq="1min")
    return pd.DataFrame(data, index=index)


class TestM1Confirmation:
    def test_3_bullish_candles_confirm_long(self):
        df = make_m1_df(closes=[310, 311, 312], opens=[309, 310, 311])
        checker = M1Confirmation(bars_needed=2, total_bars=3)
        assert checker.check(df, "long") is True

    def test_2_bullish_1_bearish_confirm_long(self):
        df = make_m1_df(closes=[311, 310, 312], opens=[310, 311, 311])
        checker = M1Confirmation(bars_needed=2, total_bars=3)
        assert checker.check(df, "long") is True

    def test_1_bullish_2_bearish_rejects_long(self):
        df = make_m1_df(closes=[311, 309, 308], opens=[310, 311, 310])
        checker = M1Confirmation(bars_needed=2, total_bars=3)
        assert checker.check(df, "long") is False

    def test_2_bearish_1_bullish_confirm_short(self):
        df = make_m1_df(closes=[309, 308, 310], opens=[310, 310, 309])
        checker = M1Confirmation(bars_needed=2, total_bars=3)
        assert checker.check(df, "short") is True

    def test_1_bearish_2_bullish_rejects_short(self):
        df = make_m1_df(closes=[309, 311, 312], opens=[310, 310, 310])
        checker = M1Confirmation(bars_needed=2, total_bars=3)
        assert checker.check(df, "short") is False

    def test_fewer_than_required_bars_returns_false(self):
        df = make_m1_df(closes=[310, 311], opens=[309, 310])
        checker = M1Confirmation(bars_needed=2, total_bars=3)
        assert checker.check(df, "long") is False

    def test_doji_candles_not_counted_as_bullish_or_bearish(self):
        df = make_m1_df(closes=[310, 311, 311], opens=[310, 310, 311])
        checker = M1Confirmation(bars_needed=2, total_bars=3)
        assert checker.check(df, "long") is False

    def test_unknown_direction_returns_false(self):
        df = make_m1_df(closes=[310, 311, 312], opens=[309, 310, 311])
        checker = M1Confirmation(bars_needed=2, total_bars=3)
        assert checker.check(df, "invalid") is False

    def test_bars_needed_exact_dynamic(self):
        df = make_m1_df(closes=[310, 311, 312, 313], opens=[309, 310, 311, 312])
        checker = M1Confirmation(bars_needed=3, total_bars=4)
        assert checker.check(df, "long") is True

    def test_empty_dataframe_returns_false(self):
        df = make_m1_df(closes=[], opens=[])
        checker = M1Confirmation(bars_needed=2, total_bars=3)
        assert checker.check(df, "long") is False
