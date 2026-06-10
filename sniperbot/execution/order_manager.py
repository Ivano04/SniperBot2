import logging

from sniperbot.strategy.swing_points import SwingPoint
from sniperbot.strategy.targets import LiquidityLevel
from sniperbot.data.ib_client import IBClient
from sniperbot.execution.risk_manager import RiskManager

logger = logging.getLogger(__name__)


class OrderManager:
    def __init__(self, ib_client: IBClient, risk_manager: RiskManager):
        self.ib = ib_client
        self.risk_manager = risk_manager
        self._current_sl: float | None = None
        self._tp_levels: list[LiquidityLevel] = []
        self._entry_price: float | None = None
        self._direction: str | None = None

    def enter_trade(self, direction: str, entry_price: float,
                    initial_sl_swing: SwingPoint,
                    tp_levels: list[LiquidityLevel]) -> bool:
        if not self.risk_manager.can_trade():
            logger.warning("Entry rejected by RISK MANAGER (session_active=%s, daily_loss=%s)",
                           self.risk_manager._session_active,
                           self.risk_manager.daily_loss_hit())
            return False

        side = "buy" if direction == "long" else "sell"
        symbol = "NQ"
        qty = 1

        initial_sl_price = initial_sl_swing.price

        result = self.ib.submit_order(
            symbol=symbol, qty=qty, side=side, order_type="market",
            stop_loss=initial_sl_price,
        )

        # "PendingSubmit" è lo stato iniziale dell'ordine prima che IB
        # lo promuova a PreSubmitted/Submitted; va accettato.
        if result and result.get("status") in ("Filled", "Submitted", "PreSubmitted", "PendingSubmit"):
            self._current_sl = initial_sl_price
            self._tp_levels = tp_levels
            self._entry_price = entry_price
            self._direction = direction
            return True

        logger.warning("Entry rejected by BROKER — order_id=%s, status=%s",
                       result.get("id") if result else "None",
                       result.get("status") if result else "None")
        return False

    def update_trailing_sl(self, new_swing: SwingPoint, current_sl: float,
                           direction: str) -> bool:
        position = self.ib.get_position("NQ")
        if position is None:
            return False

        if direction == "long" and new_swing.type == "low":
            if new_swing.price > current_sl:
                self._current_sl = new_swing.price
                return True
        elif direction == "short" and new_swing.type == "high":
            if new_swing.price < current_sl:
                self._current_sl = new_swing.price
                return True
        return False

    def check_tp_hit(self, current_price: float) -> bool:
        if self._direction == "long":
            for tp in self._tp_levels:
                if current_price >= tp.price:
                    return True
        elif self._direction == "short":
            for tp in self._tp_levels:
                if current_price <= tp.price:
                    return True
        return False

    def close_position(self) -> bool:
        # Snapshot unrealized PnL before flattening so risk manager stays accurate
        position = self.ib.get_position("NQ")
        if position is not None:
            self.risk_manager.update_pnl(position.get("unrealized_pl", 0))

        result = self.ib.close_position("NQ")
        return result.get("status") != "error"
