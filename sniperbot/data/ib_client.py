"""IBClient — Interactive Brokers gateway data fetch and order submission.

Wraps ib_insync for connecting to IB Gateway, fetching historical bars,
and managing futures orders. All public methods return plain dicts or
DataFrames — no IB types leak to strategy code.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from ib_insync import IB, Future, MarketOrder, StopOrder, Contract


class IBClient:
    """Client for Interactive Brokers Gateway via ib_insync."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4002,
        client_id: int = 1,
        exchange: str = "CME",
        currency: str = "USD",
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib = IB()
        self._connected = False
        self._contract: Contract | None = None
        self._symbol = "NQ"
        self._exchange = exchange
        self._currency = currency

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Connect to IB Gateway.

        Returns:
            True if the connection succeeded, False otherwise.
        """
        try:
            self.ib.connect(self.host, self.port, clientId=self.client_id)
            self.ib.reqMarketDataType(3)  # 3 = delayed (not frozen, needed for historical data)
            self._connected = True
            return True
        except Exception:
            return False

    def disconnect(self) -> None:
        """Disconnect from IB Gateway."""
        if self._connected:
            self.ib.disconnect()
            self._connected = False

    # ------------------------------------------------------------------
    # Contract helpers
    # ------------------------------------------------------------------

    def _get_contract(self, symbol: str) -> Contract:
        """Return a qualified Future contract for *symbol* (front month)."""
        from datetime import date as dt_date

        if self._contract is None or symbol != self._symbol:
            # Compute front-month expiry for quarterly futures (H=Mar,M=Jun,U=Sep,Z=Dec)
            today = dt_date.today()
            quarterly = [3, 6, 9, 12]
            expiry_month = next(m for m in quarterly if m >= today.month)
            expiry = f"{today.year:04d}{expiry_month:02d}"

            contract = Future(
                symbol=symbol,
                lastTradeDateOrContractMonth=expiry,
                exchange=self._exchange,
                currency=self._currency,
            )
            qualified = self.ib.qualifyContracts(contract)
            self._contract = qualified[0] if qualified else contract
            self._symbol = symbol
        return self._contract

    # ------------------------------------------------------------------
    # Historical bars
    # ------------------------------------------------------------------

    def fetch_bars(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> pd.DataFrame:
        """Fetch historical bars for *symbol*.

        Args:
            symbol: Futures ticker (e.g. "NQ", "ES").
            timeframe: Bar size, one of ``"1Min"``, ``"5Min"``, ``"15Min"``,
                ``"1Hour"``, ``"1Day"``.
            limit: Number of bars to return.

        Returns:
            DataFrame with columns ``open, high, low, close, volume`` and
            a ``DatetimeIndex`` named ``timestamp``.  Empty DataFrame when
            not connected or no data is available.
        """
        if not self._connected:
            return pd.DataFrame()

        contract = self._get_contract(symbol)

        bar_size_map = {
            "1Min": "1 min",
            "5Min": "5 mins",
            "15Min": "15 mins",
            "1Hour": "1 hour",
            "1Day": "1 day",
        }
        bar_size = bar_size_map.get(timeframe, "5 mins")

        # Build a duration string long enough to cover *limit* bars plus
        # some headroom so IB does not complain about an undersized request.
        if timeframe == "5Min":
            duration_str = "2 D"
        elif "min" in bar_size:
            total_minutes = int(bar_size.split()[0]) * limit * 2
            if total_minutes < 60:
                duration_str = f"{total_minutes * 60} S"
            elif total_minutes < 3600:
                duration_str = f"{total_minutes // 60} D"
            else:
                duration_str = f"{total_minutes // 3600 + 1} D"
        else:
            duration_str = f"{limit * 2} D"

        try:
            bars = self.ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr=duration_str,
                barSizeSetting=bar_size,
                whatToShow="TRADES",
                useRTH=False,
                formatDate=1,
            )

            if not bars:
                return pd.DataFrame()

            data = [
                {
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume,
                }
                for b in bars
            ]

            df = pd.DataFrame(
                data,
                index=pd.DatetimeIndex([b.date for b in bars]),
            )
            df.index.name = "timestamp"

            return df.tail(limit)
        except Exception:
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def submit_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str = "market",
        limit_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict[str, Any]:
        """Submit an order for *symbol*.

        Args:
            symbol: Futures ticker.
            qty: Number of contracts.
            side: ``"buy"`` or ``"sell"``.
            order_type: ``"market"`` or ``"limit"``.
            limit_price: Required when *order_type* is ``"limit"``.
            stop_loss: Optional stop-loss price (submitted as a separate
                StopOrder).
            take_profit: Optional take-profit price (reserved for future
                use).

        Returns:
            Dict with keys ``id``, ``status``, and optionally
            ``sl_order_id``.
        """
        if not self._connected:
            return {"id": 0, "status": "error", "error": "not connected"}

        contract = self._get_contract(symbol)
        action = "BUY" if side == "buy" else "SELL"

        if order_type == "market":
            order = MarketOrder(action, qty, tif="DAY")
        else:
            from ib_insync import LimitOrder

            order = LimitOrder(action, qty, limit_price, tif="DAY")

        trade = self.ib.placeOrder(contract, order)
        result: dict[str, Any] = {
            "id": trade.order.orderId,
            "status": trade.orderStatus.status,
        }

        if stop_loss is not None:
            sl_action = "SELL" if side == "buy" else "BUY"
            sl_order = StopOrder(sl_action, qty, stop_loss, tif="DAY")
            sl_trade = self.ib.placeOrder(contract, sl_order)
            result["sl_order_id"] = sl_trade.order.orderId

        return result

    def cancel_order(self, order_id: int) -> dict[str, Any]:
        """Cancel an open order by its IB order id."""
        if not self._connected:
            return {"id": order_id, "status": "error"}
        self.ib.cancelOrder(order_id)
        return {"id": order_id, "status": "cancelled"}

    # ------------------------------------------------------------------
    # Positions & Account
    # ------------------------------------------------------------------

    def get_position(self, symbol: str) -> dict[str, Any] | None:
        """Return current position information for *symbol*, or ``None``."""
        if not self._connected:
            return None
        self.ib.reqPositions()
        positions = self.ib.positions()
        for pos in positions:
            if (
                pos.contract.symbol == symbol
                and pos.contract.exchange == self._exchange
            ):
                return {
                    "symbol": pos.contract.symbol,
                    "qty": abs(float(pos.position)),
                    "side": "long" if float(pos.position) > 0 else "short",
                    "avg_entry_price": float(pos.avgCost),
                    "unrealized_pl": (
                        float(pos.unrealizedPNL)
                        if hasattr(pos, "unrealizedPNL")
                        else 0.0
                    ),
                    "current_price": (
                        float(pos.markPrice) if hasattr(pos, "markPrice") else 0.0
                    ),
                }
        return None

    def get_account(self) -> dict[str, Any]:
        """Return account summary dict with keys ``equity`` and ``cash``."""
        if not self._connected:
            return {"equity": 0.0, "cash": 0.0}

        try:
            summary = self.ib.accountSummary()
            values: dict[str, float] = {}
            for v in summary:
                try:
                    if v.currency == "USD" and v.tag in ("NetLiquidation", "AvailableFunds"):
                        values[v.tag] = float(v.value)
                except (ValueError, TypeError, AttributeError):
                    pass

            if "NetLiquidation" in values:
                return {"equity": values["NetLiquidation"], "cash": values.get("AvailableFunds", 0.0)}
        except Exception:
            pass

        # Fallback: use safe defaults for paper trading
        return {"equity": 1_000_000.0, "cash": 500_000.0}

    def close_position(self, symbol: str) -> dict[str, Any]:
        """Flatten any existing position for *symbol*."""
        if not self._connected:
            return {"symbol": symbol, "status": "error"}
        pos = self.get_position(symbol)
        if pos is None:
            return {"symbol": symbol, "status": "no position"}

        contract = self._get_contract(symbol)
        action = "SELL" if pos["side"] == "long" else "BUY"
        qty = int(pos["qty"])

        if qty > 0:
            order = MarketOrder(action, qty)
            trade = self.ib.placeOrder(contract, order)
            return {"symbol": symbol, "status": trade.orderStatus.status}

        return {"symbol": symbol, "status": "no position"}
