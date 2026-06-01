import pytest
from unittest.mock import MagicMock
from sniperbot.strategy.swing_points import SwingPoint
from sniperbot.strategy.targets import LiquidityLevel
from sniperbot.execution.order_manager import OrderManager
from sniperbot.execution.risk_manager import RiskManager
from datetime import datetime


@pytest.fixture
def mock_ib():
    client = MagicMock()
    client.submit_order.return_value = {"id": 1, "status": "Filled"}
    client.get_position.return_value = None
    return client


@pytest.fixture
def risk_manager():
    rm = RiskManager(max_daily_loss_pct=0.08)
    rm.start_session(10000.0)
    return rm


@pytest.fixture
def order_manager(mock_ib, risk_manager):
    return OrderManager(ib_client=mock_ib, risk_manager=risk_manager)


class TestOrderManager:
    def test_enter_long_sends_buy_order(self, order_manager, mock_ib):
        tp_levels = [LiquidityLevel(type="high", price=20100.0, source="swing_m5")]
        sw_penultimate = SwingPoint(type="low", price=19900.0, index=5,
                                     timestamp=datetime(2026, 5, 21, 14, 0),
                                     excursion_ticks=150)

        result = order_manager.enter_trade("long", 20000.0, sw_penultimate, tp_levels)

        assert result is True
        mock_ib.submit_order.assert_called_once()
        call_kwargs = mock_ib.submit_order.call_args[1]
        assert call_kwargs["side"] == "buy"

    def test_enter_short_sends_sell_order(self, order_manager, mock_ib):
        tp_levels = [LiquidityLevel(type="low", price=19800.0, source="swing_m5")]
        sw_penultimate = SwingPoint(type="high", price=20100.0, index=5,
                                     timestamp=datetime(2026, 5, 21, 14, 0),
                                     excursion_ticks=150)

        result = order_manager.enter_trade("short", 20000.0, sw_penultimate, tp_levels)

        assert result is True
        call_kwargs = mock_ib.submit_order.call_args[1]
        assert call_kwargs["side"] == "sell"

    def test_entry_blocked_when_risk_manager_says_no(self, order_manager, mock_ib, risk_manager):
        risk_manager.update_pnl(-900.0)  # Hit loss limit
        tp_levels = [LiquidityLevel(type="high", price=20100.0, source="swing_m5")]
        sw = SwingPoint(type="low", price=19900.0, index=5,
                        timestamp=datetime(2026, 5, 21, 14, 0), excursion_ticks=150)

        result = order_manager.enter_trade("long", 20000.0, sw, tp_levels)
        assert result is False
        mock_ib.submit_order.assert_not_called()

    def test_trailing_sl_updates_only_when_better(self, order_manager, mock_ib):
        mock_ib.get_position.return_value = {
            "symbol": "NQ", "qty": 1, "side": "long",
            "avg_entry_price": 20000.0, "current_price": 20100.0
        }
        current_sl = 19900.0

        new_swing = SwingPoint(type="low", price=19950.0, index=10,
                               timestamp=datetime(2026, 5, 21, 15, 0),
                               excursion_ticks=100)

        result = order_manager.update_trailing_sl(new_swing, current_sl, "long")
        assert result is True
        assert order_manager._current_sl == 19950.0

    def test_trailing_sl_not_updated_when_worse(self, order_manager):
        current_sl = 19950.0
        new_swing = SwingPoint(type="low", price=19900.0, index=10,
                               timestamp=datetime(2026, 5, 21, 15, 0),
                               excursion_ticks=100)

        result = order_manager.update_trailing_sl(new_swing, current_sl, "long")
        assert result is False
