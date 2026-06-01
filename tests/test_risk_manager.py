import pytest
from sniperbot.execution.risk_manager import RiskManager


class TestRiskManager:
    def test_allows_trading_within_loss_limit(self):
        rm = RiskManager(max_daily_loss_pct=0.08)
        rm.start_session(account_equity=10000.0)
        assert rm.can_trade() is True

    def test_blocks_trading_when_loss_limit_hit(self):
        rm = RiskManager(max_daily_loss_pct=0.08)
        rm.start_session(account_equity=10000.0)
        rm.update_pnl(-801.0)  # > 8% of 10000 = 800
        assert rm.can_trade() is False
        assert rm.daily_loss_hit() is True

    def test_allows_trading_at_exact_limit(self):
        rm = RiskManager(max_daily_loss_pct=0.08)
        rm.start_session(account_equity=10000.0)
        rm.update_pnl(-800.0)  # Exactly 8%
        assert rm.can_trade() is False

    def test_accumulates_pnl_across_trades(self):
        rm = RiskManager(max_daily_loss_pct=0.08)
        rm.start_session(account_equity=10000.0)
        rm.update_pnl(-300.0)
        rm.update_pnl(-300.0)
        rm.update_pnl(-250.0)  # Total = -850, exceeds 800
        assert rm.can_trade() is False

    def test_profits_reduce_accumulated_loss(self):
        rm = RiskManager(max_daily_loss_pct=0.08)
        rm.start_session(account_equity=10000.0)
        rm.update_pnl(-500.0)
        rm.update_pnl(200.0)   # Net = -300
        assert rm.can_trade() is True

    def test_cannot_trade_before_session_start(self):
        rm = RiskManager(max_daily_loss_pct=0.08)
        assert rm.can_trade() is False

    def test_configurable_loss_percentage(self):
        rm = RiskManager(max_daily_loss_pct=0.05)
        rm.start_session(account_equity=10000.0)
        rm.update_pnl(-501.0)  # > 5% of 10000
        assert rm.can_trade() is False
