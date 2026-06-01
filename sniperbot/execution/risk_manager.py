class RiskManager:
    def __init__(self, max_daily_loss_pct: float = 0.08):
        self.max_daily_loss_pct = max_daily_loss_pct
        self._session_active = False
        self._max_loss_amount = 0.0
        self._realized_pnl = 0.0

    def start_session(self, account_equity: float):
        self._session_active = True
        self._max_loss_amount = account_equity * self.max_daily_loss_pct
        self._realized_pnl = 0.0

    def can_trade(self) -> bool:
        if not self._session_active:
            return False
        return not self.daily_loss_hit()

    def update_pnl(self, realized_pnl: float):
        self._realized_pnl += realized_pnl

    def daily_loss_hit(self) -> bool:
        if not self._session_active:
            return False
        return self._realized_pnl <= -self._max_loss_amount
