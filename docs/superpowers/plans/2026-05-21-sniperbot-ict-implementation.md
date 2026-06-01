# SniperBot ICT — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a headless sniperbot that monitors NQ Futures (E-mini NASDAQ-100) via Interactive Brokers during the 13:30-15:30 GMT killzone and executes ICT-strategy trades.

**Architecture:** Modular Python pipeline: data layer (IB Gateway + ib_insync) → strategy engine (swing points, FVG, zonation, confirmation, targets) → execution layer (order manager, risk manager), orchestrated by a time-scheduled main loop.

**Tech Stack:** Python 3.11+, `ib_insync` (IB API wrapper), `pandas`, `pytest`

**Instrument:** NQ Futures (CME). Tick size: 0.25 punti indice ($5/tick). 1 punto = 4 tick = $20. Leva intraday ~20:1.

---

## File Structure

```
Sniperbot2/
├── sniperbot/
│   ├── __init__.py                  # Empty
│   ├── config.py                    # Task 1: All constants
│   ├── data/
│   │   ├── __init__.py              # Empty
│   │   └── ib_client.py             # Task 2: IB Gateway + ib_insync wrapper
│   ├── strategy/
│   │   ├── __init__.py              # Empty
│   │   ├── swing_points.py          # Task 3: Swing point detection
│   │   ├── fvg.py                   # Task 4: FVG detection + tracking
│   │   ├── zonation.py              # Task 5: Premium/Discount
│   │   ├── confirmation.py          # Task 6: M1 2/3 confirmation
│   │   └── targets.py               # Task 7: TP liquidity levels
│   ├── execution/
│   │   ├── __init__.py              # Empty
│   │   ├── risk_manager.py          # Task 8: Daily loss gate
│   │   └── order_manager.py         # Task 9: Entry, SL trailing, TP
│   └── main.py                      # Task 10: Orchestrator + scheduler
├── tests/
│   ├── __init__.py
│   ├── test_swing_points.py
│   ├── test_fvg.py
│   ├── test_zonation.py
│   ├── test_confirmation.py
│   ├── test_targets.py
│   ├── test_risk_manager.py
│   └── test_order_manager.py
├── logs/                            # Created at runtime
├── requirements.txt                 # Task 1
└── README.md
```

---

### Task 1: Project setup — config, requirements, directory skeleton

**Files:**
- Create: `sniperbot/__init__.py`, `sniperbot/config.py`
- Create: `sniperbot/data/__init__.py`, `sniperbot/strategy/__init__.py`, `sniperbot/execution/__init__.py`
- Create: `tests/__init__.py`
- Create: `requirements.txt`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p sniperbot/data sniperbot/strategy sniperbot/execution tests logs
```

- [ ] **Step 2: Create empty `__init__.py` files**

All `__init__.py` files are empty (touch them).

- [ ] **Step 3: Write `requirements.txt`**

```
ib-insync>=0.9.86
pandas>=2.0.0
pytest>=8.0.0
python-dotenv>=1.0.0
```

- [ ] **Step 4: Write `sniperbot/config.py`**

```python
import os
from dotenv import load_dotenv

load_dotenv()

# Interactive Brokers connection
IB_HOST = os.getenv("IB_HOST", "127.0.0.1")
IB_PORT = int(os.getenv("IB_PORT", "4002"))  # 4002=paper, 4001=live
IB_CLIENT_ID = int(os.getenv("IB_CLIENT_ID", "1"))

# Trading instrument — NQ Futures
SYMBOL = "NQ"
EXCHANGE = "CME"
CURRENCY = "USD"
POSITION_SIZE = 1
TICK_SIZE = 0.25  # NQ tick = 0.25 punti indice

# Killzone (Italy time, GMT+2 summer / GMT+1 winter)
KILLZONE_START = "15:30"
KILLZONE_END = "17:30"

# Swing point detection (M5)
SWING_WINDOW_LEFT = 5
SWING_WINDOW_RIGHT = 3
MIN_SWING_EXCURSION_TICKS = 100  # 100 tick NQ = 25 punti indice

# FVG detection
FVG_LOOKBACK_CANDLES = 300

# M1 confirmation
M1_CONFIRMATION_BARS = 3
M1_BULLISH_NEEDED = 2
M1_BEARISH_NEEDED = 2

# Take profit
MIN_TP_DISTANCE_TICKS = 40  # 40 tick NQ = 10 punti indice

# Risk management
MAX_DAILY_LOSS_PCT = 0.08  # 8%

# Sessions (GMT)
ASIA_START = "00:00"
ASIA_END = "09:00"
LONDON_START = "09:00"
LONDON_END = "11:00"

# Retry
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1  # seconds, exponential backoff
```

- [ ] **Step 5: Create `.env.example`**

```
IB_HOST=127.0.0.1
IB_PORT=4002
IB_CLIENT_ID=1
```

- [ ] **Step 6: Install dependencies and verify**

```bash
pip install -r requirements.txt
python -c "from sniperbot.config import SYMBOL; print(SYMBOL)"
```

Expected: prints `NQ`

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore: project setup with config, requirements, directory skeleton"
```

---

### Task 2: IBClient — data fetch and order submission via Interactive Brokers

**Files:**
- Create: `sniperbot/data/ib_client.py`
- Create: `tests/test_ib_client.py`

The module wraps `ib_insync` for connecting to IB Gateway, fetching historical bars, and managing futures orders. All methods return plain dicts or DataFrames — no IB types leak to strategy code. IB Gateway must be running before the bot starts.

- [ ] **Step 1: Write the test file `tests/test_ib_client.py`**

```python
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch
from sniperbot.data.ib_client import IBClient


@pytest.fixture
def mock_ib():
    with patch("sniperbot.data.ib_client.IB") as mock_ib_class:
        mock_ib = MagicMock()
        mock_ib_class.return_value = mock_ib
        client = IBClient(host="127.0.0.1", port=4002, client_id=1)
        yield client, mock_ib


class TestIBClientInit:
    def test_stores_connection_params(self, mock_ib):
        client, _ = mock_ib
        assert client.host == "127.0.0.1"
        assert client.port == 4002
        assert client.client_id == 1


class TestConnect:
    def test_connect_calls_ib_connect(self, mock_ib):
        client, ib = mock_ib
        client.connect()
        ib.connect.assert_called_once_with("127.0.0.1", 4002, clientId=1)

    def test_connect_returns_true_on_success(self, mock_ib):
        client, ib = mock_ib
        assert client.connect() is True

    def test_connect_returns_false_on_failure(self, mock_ib):
        client, ib = mock_ib
        ib.connect.side_effect = ConnectionRefusedError
        assert client.connect() is False

    def test_disconnect_calls_ib_disconnect(self, mock_ib):
        client, ib = mock_ib
        client.connect()
        client.disconnect()
        ib.disconnect.assert_called_once()


class TestFetchBars:
    def test_returns_dataframe_with_expected_columns(self, mock_ib):
        client, ib = mock_ib
        # Mock ib.reqHistoricalData return
        mock_bar = MagicMock()
        mock_bar.open = 20000.0
        mock_bar.high = 20100.0
        mock_bar.low = 19900.0
        mock_bar.close = 20050.0
        mock_bar.volume = 5000
        mock_bar.date = pd.Timestamp("2026-05-21 14:00:00")

        ib.reqHistoricalData.return_value = [mock_bar]

        df = client.fetch_bars("NQ", "5Min", limit=10)

        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert len(df) == 1
        assert df.iloc[0]["close"] == 20050.0
        assert df.index.name == "timestamp"

    def test_requests_correct_duration_and_bar_size(self, mock_ib):
        client, ib = mock_ib
        ib.reqHistoricalData.return_value = []

        client.fetch_bars("NQ", "5Min", limit=300)

        call_args = ib.reqHistoricalData.call_args[1]
        assert call_args["barSizeSetting"] == "5 mins"
        assert "D" in call_args["durationStr"]

    def test_returns_empty_dataframe_when_no_data(self, mock_ib):
        client, ib = mock_ib
        ib.reqHistoricalData.return_value = []
        df = client.fetch_bars("NQ", "5Min", limit=10)
        assert len(df) == 0


class TestSubmitOrder:
    def test_submits_market_buy_order_correctly(self, mock_ib):
        client, ib = mock_ib
        mock_trade = MagicMock()
        mock_trade.order.orderId = 123
        mock_trade.orderStatus.status = "Filled"
        ib.placeOrder.return_value = mock_trade

        result = client.submit_order("NQ", 1, "buy", "market")

        ib.placeOrder.assert_called_once()
        assert result["id"] == 123
        assert result["status"] == "Filled"

    def test_submits_sell_order_with_stop_loss(self, mock_ib):
        client, ib = mock_ib
        mock_trade = MagicMock()
        mock_trade.order.orderId = 456
        mock_trade.orderStatus.status = "Submitted"
        ib.placeOrder.return_value = mock_trade

        result = client.submit_order("NQ", 1, "sell", "market", stop_loss=19900.0)

        assert result["id"] == 456
        assert result["status"] == "Submitted"


class TestGetAccount:
    def test_returns_account_summary(self, mock_ib):
        client, ib = mock_ib
        mock_value = MagicMock()
        mock_value.value = "100000.0"
        ib.accountSummary.return_value = [
            MagicMock(tag="NetLiquidation", value="100000.0", currency="USD"),
            MagicMock(tag="AvailableFunds", value="50000.0", currency="USD"),
        ]
        # Simpler approach: mock accountValues
        ib.accountValues.return_value = [
            MagicMock(tag="NetLiquidation", value="100000.0", currency="USD"),
            MagicMock(tag="AvailableFunds", value="50000.0", currency="USD"),
        ]

        account = client.get_account()
        assert account["equity"] == 100000.0
        assert account["cash"] == 50000.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_ib_client.py -v
```
Expected: FAIL — module not found

- [ ] **Step 3: Write `sniperbot/data/ib_client.py`**

```python
import pandas as pd
from ib_insync import IB, Future, MarketOrder, StopOrder, Contract


class IBClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 4002, client_id: int = 1):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib = IB()
        self._connected = False
        self._contract: Contract | None = None
        self._symbol = "NQ"
        self._exchange = "CME"
        self._currency = "USD"

    def connect(self) -> bool:
        try:
            self.ib.connect(self.host, self.port, clientId=self.client_id)
            self._connected = True
            return True
        except Exception:
            return False

    def disconnect(self):
        if self._connected:
            self.ib.disconnect()
            self._connected = False

    def _get_contract(self, symbol: str) -> Contract:
        """Get or create a Future contract for the front month."""
        if self._contract is None or symbol != self._symbol:
            # Get the front-month future
            contract = Future(
                symbol=symbol,
                exchange=self._exchange,
                currency=self._currency,
                includeExpired=False,
            )
            # Qualify the contract to get conId
            qualified = self.ib.qualifyContracts(contract)
            if qualified:
                self._contract = qualified[0]
            else:
                self._contract = contract
        return self._contract

    def fetch_bars(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        if not self._connected:
            return pd.DataFrame()

        contract = self._get_contract(symbol)

        # Map timeframe to IB bar size and duration
        bar_size_map = {
            "1Min": "1 min",
            "5Min": "5 mins",
            "15Min": "15 mins",
            "1Hour": "1 hour",
            "1Day": "1 day",
        }
        bar_size = bar_size_map.get(timeframe, "5 mins")

        # Calculate duration: approximate based on limit and timeframe
        if "min" in bar_size:
            minutes = int(bar_size.split()[0]) * limit * 2  # 2x safety margin
            if minutes < 60:
                duration_str = f"{minutes * 60} S"
            elif minutes < 3600:
                duration_str = f"{minutes // 60} D"
            else:
                duration_str = f"{minutes // 3600 + 1} D"
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

            data = [{
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            } for b in bars]

            df = pd.DataFrame(data, index=pd.DatetimeIndex([b.date for b in bars]))
            df.index.name = "timestamp"

            # Return only the last `limit` rows
            return df.tail(limit)
        except Exception:
            return pd.DataFrame()

    def submit_order(self, symbol: str, qty: int, side: str, order_type: str = "market",
                     limit_price: float | None = None, stop_loss: float | None = None,
                     take_profit: float | None = None) -> dict:
        if not self._connected:
            return {"id": 0, "status": "error", "error": "not connected"}

        contract = self._get_contract(symbol)

        if order_type == "market":
            action = "BUY" if side == "buy" else "SELL"
            order = MarketOrder(action, qty)
        else:
            action = "BUY" if side == "buy" else "SELL"
            from ib_insync import LimitOrder
            order = LimitOrder(action, qty, limit_price)

        trade = self.ib.placeOrder(contract, order)

        result = {"id": trade.order.orderId, "status": trade.orderStatus.status}

        # Submit stop loss as a separate order if requested
        if stop_loss is not None:
            sl_action = "SELL" if side == "buy" else "BUY"
            sl_order = StopOrder(sl_action, qty, stop_loss)
            sl_trade = self.ib.placeOrder(contract, sl_order)
            result["sl_order_id"] = sl_trade.order.orderId

        return result

    def cancel_order(self, order_id: int) -> dict:
        if not self._connected:
            return {"id": order_id, "status": "error"}
        self.ib.cancelOrder(order_id)
        return {"id": order_id, "status": "cancelled"}

    def get_position(self, symbol: str) -> dict | None:
        if not self._connected:
            return None
        self.ib.reqPositions()
        positions = self.ib.positions()
        for pos in positions:
            if pos.contract.symbol == symbol and pos.contract.exchange == self._exchange:
                return {
                    "symbol": pos.contract.symbol,
                    "qty": abs(float(pos.position)),
                    "side": "long" if float(pos.position) > 0 else "short",
                    "avg_entry_price": float(pos.avgCost),
                    "unrealized_pl": float(pos.unrealizedPNL) if hasattr(pos, "unrealizedPNL") else 0.0,
                    "current_price": float(pos.markPrice) if hasattr(pos, "markPrice") else 0.0,
                }
        return None

    def get_account(self) -> dict:
        if not self._connected:
            return {"equity": 0.0, "cash": 0.0}
        values = {v.tag: float(v.value) for v in self.ib.accountValues()
                  if v.currency == "USD"}
        return {
            "equity": values.get("NetLiquidation", 0.0),
            "cash": values.get("AvailableFunds", 0.0),
        }

    def close_position(self, symbol: str) -> dict:
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_ib_client.py -v
```
Expected: 9 PASS

- [ ] **Step 5: Commit**

```bash
git add sniperbot/data/ib_client.py tests/test_ib_client.py
git commit -m "feat: add IBClient for IB Gateway data fetch and order submission"
```

---

### Task 3: SwingPointDetector — M5 swing point detection

**Files:**
- Create: `sniperbot/strategy/swing_points.py`
- Create: `tests/test_swing_points.py`

- [ ] **Step 1: Write test file `tests/test_swing_points.py`**

```python
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
        # Create a clear swing high at index 6: 100 -> 120 -> 100
        prices = [100, 105, 110, 115, 120, 115, 110, 105, 100, 95, 90]
        df = make_df(prices)
        detector = SwingPointDetector(window_left=5, window_right=3, min_excursion_ticks=50)
        swings = detector.detect(df)

        highs = [s for s in swings if s.type == "high"]
        assert len(highs) >= 1
        assert any(s.price == 122.0 for s in highs)  # high column is price + 2

    def test_detects_swing_low_with_min_excursion(self):
        # Create a clear swing low at index 6: 100 -> 80 -> 100
        prices = [100, 95, 90, 85, 80, 85, 90, 95, 100, 105, 110]
        df = make_df(prices)
        detector = SwingPointDetector(window_left=5, window_right=3, min_excursion_ticks=50)
        swings = detector.detect(df)

        lows = [s for s in swings if s.type == "low"]
        assert len(lows) >= 1
        assert any(s.price == 78.0 for s in lows)  # low column is price - 2

    def test_filters_swing_below_excursion_threshold(self):
        # Small oscillation, no real swing
        prices = [100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100]
        df = make_df(prices)
        detector = SwingPointDetector(window_left=5, window_right=3, min_excursion_ticks=500)
        swings = detector.detect(df)
        assert len(swings) == 0

    def test_swing_point_has_correct_structure(self):
        prices = [100, 105, 110, 115, 120, 115, 110, 105, 100, 95, 90]
        df = make_df(prices)
        detector = SwingPointDetector(window_left=5, window_right=3, min_excursion_ticks=50)
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_swing_points.py -v
```
Expected: FAIL — module not found

- [ ] **Step 3: Write `sniperbot/strategy/swing_points.py`**

```python
from dataclasses import dataclass
from datetime import datetime
import pandas as pd


@dataclass
class SwingPoint:
    type: str           # 'high' or 'low'
    price: float
    index: int
    timestamp: datetime
    excursion_ticks: float


class SwingPointDetector:
    def __init__(self, window_left: int = 5, window_right: int = 3,
                 min_excursion_ticks: int = 100):
        self.window_left = window_left
        self.window_right = window_right
        self.min_excursion_ticks = min_excursion_ticks

    def detect(self, df: pd.DataFrame) -> list[SwingPoint]:
        if len(df) < self.window_left + self.window_right + 1:
            return []

        swings = []
        n = len(df)

        for i in range(self.window_left, n - self.window_right):
            high_i = df["high"].iloc[i]
            low_i = df["low"].iloc[i]
            ts = df.index[i]

            # Check swing high
            left_highs = df["high"].iloc[i - self.window_left:i]
            right_highs = df["high"].iloc[i + 1:i + 1 + self.window_right]
            if all(high_i > left_highs) and all(high_i > right_highs):
                # Calculate excursion: range from this high to lowest low in local area
                local_low = min(
                    df["low"].iloc[i - self.window_left:i + self.window_right + 1]
                )
                excursion = high_i - local_low
                if excursion >= self.min_excursion_ticks:
                    swings.append(SwingPoint(
                        type="high", price=high_i, index=i,
                        timestamp=ts.to_pydatetime(), excursion_ticks=excursion,
                    ))

            # Check swing low
            left_lows = df["low"].iloc[i - self.window_left:i]
            right_lows = df["low"].iloc[i + 1:i + 1 + self.window_right]
            if all(low_i < left_lows) and all(low_i < right_lows):
                local_high = max(
                    df["high"].iloc[i - self.window_left:i + self.window_right + 1]
                )
                excursion = local_high - low_i
                if excursion >= self.min_excursion_ticks:
                    swings.append(SwingPoint(
                        type="low", price=low_i, index=i,
                        timestamp=ts.to_pydatetime(), excursion_ticks=excursion,
                    ))

        return swings
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_swing_points.py -v
```
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add sniperbot/strategy/swing_points.py tests/test_swing_points.py
git commit -m "feat: add SwingPointDetector for M5 swing point detection"
```

---

### Task 4: FVGDetector — Fair Value Gap detection and tracking

**Files:**
- Create: `sniperbot/strategy/fvg.py`
- Create: `tests/test_fvg.py`

- [ ] **Step 1: Write test file `tests/test_fvg.py`**

```python
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
        # Bullish: low[i] > high[i+2], gap between high[i+2] and low[i]
        highs = [310, 309, 305, 306, 307]  # high[2]=305, low[0]=? no
        # Let's be precise: bullish FVG at i=0: low[0] > high[2]
        # low[0]=309, high[2]=305 -> 309 > 305 -> gap is (305, 309)
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
        # Bearish: high[i] < low[i+2], gap between high[i] and low[i+2]
        highs = [305, 307, 308, 307, 308]
        lows = [304, 306, 307, 306, 307]
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
        # Later price went below bottom of bullish FVG (closed)
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
        # Only FVGs from last 3 candles should be present
        for f in fvgs:
            assert f.start_index >= len(df) - 3
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_fvg.py -v
```
Expected: FAIL — module not found

- [ ] **Step 3: Write `sniperbot/strategy/fvg.py`**

```python
from dataclasses import dataclass
from datetime import datetime
import pandas as pd


@dataclass
class FVG:
    type: str          # 'bullish' or 'bearish'
    top: float          # upper bound of the gap
    bottom: float       # lower bound of the gap
    start_index: int
    start_timestamp: datetime
    closed: bool = False


class FVGDetector:
    def __init__(self, lookback: int = 300):
        self.lookback = lookback

    def detect(self, df: pd.DataFrame) -> list[FVG]:
        if len(df) < 3:
            return []

        fvgs = []
        # Only scan within lookback window from the end
        start_idx = max(0, len(df) - self.lookback)

        for i in range(start_idx, len(df) - 2):
            ts = df.index[i]

            # Bullish FVG: low[i] > high[i+2]
            if df["low"].iloc[i] > df["high"].iloc[i + 2]:
                fvgs.append(FVG(
                    type="bullish",
                    top=df["low"].iloc[i],
                    bottom=df["high"].iloc[i + 2],
                    start_index=i,
                    start_timestamp=ts.to_pydatetime(),
                ))

            # Bearish FVG: high[i] < low[i+2]
            if df["high"].iloc[i] < df["low"].iloc[i + 2]:
                fvgs.append(FVG(
                    type="bearish",
                    top=df["low"].iloc[i + 2],
                    bottom=df["high"].iloc[i],
                    start_index=i,
                    start_timestamp=ts.to_pydatetime(),
                ))

        return fvgs

    def is_price_inside(self, price: float, fvg: FVG) -> bool:
        return fvg.bottom < price < fvg.top

    def update_closure(self, fvgs: list[FVG], df_recent: pd.DataFrame) -> list[FVG]:
        if df_recent.empty:
            return fvgs

        for fvg in fvgs:
            if fvg.closed:
                continue
            for i in range(len(df_recent)):
                close = df_recent["close"].iloc[i]
                if fvg.type == "bullish":
                    # Bullish FVG is "closed" when price drops below its bottom
                    if close <= fvg.bottom:
                        fvg.closed = True
                        break
                else:
                    # Bearish FVG is "closed" when price rises above its top
                    if close >= fvg.top:
                        fvg.closed = True
                        break

        return fvgs
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_fvg.py -v
```
Expected: 8 PASS

- [ ] **Step 5: Commit**

```bash
git add sniperbot/strategy/fvg.py tests/test_fvg.py
git commit -m "feat: add FVGDetector for Fair Value Gap detection and tracking"
```

---

### Task 5: Zonation — Premium/Discount determination

**Files:**
- Create: `sniperbot/strategy/zonation.py`
- Create: `tests/test_zonation.py`

- [ ] **Step 1: Write test file `tests/test_zonation.py`**

```python
import pandas as pd
from datetime import datetime
from sniperbot.strategy.swing_points import SwingPoint
from sniperbot.strategy.zonation import Zonation

# Test constants
PREMIUM = "premium"
DISCOUNT = "discount"


class TestZonation:
    def test_premium_zone_triggers_short_only(self):
        # Price is below a significant swing high but above 50% of the range
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
        # Price above all swing highs -> no zone
        assert zonation.determine(410.0, swings) is None
        # Price below all swing lows -> no zone
        assert zonation.determine(340.0, swings) is None

    def test_uses_closest_swings_for_range(self):
        # Multiple swings: should use the most significant high and low
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_zonation.py -v
```
Expected: FAIL

- [ ] **Step 3: Write `sniperbot/strategy/zonation.py`**

```python
from sniperbot.strategy.swing_points import SwingPoint


class Zonation:
    PREMIUM = "premium"
    DISCOUNT = "discount"

    def determine(self, price: float, swing_points: list[SwingPoint]) -> str | None:
        if not swing_points:
            return None

        highs = [s for s in swing_points if s.type == "high"]
        lows = [s for s in swing_points if s.type == "low"]

        if not highs or not lows:
            return None

        # Use the most significant (largest excursion) swing high and low
        significant_high = max(highs, key=lambda s: s.excursion_ticks)
        significant_low = max(lows, key=lambda s: s.excursion_ticks)

        range_top = significant_high.price
        range_bottom = significant_low.price
        midpoint = (range_top + range_bottom) / 2

        # Premium: price is in upper half of range (below swing high, above midpoint)
        # Only SHORT signals
        if midpoint < price < range_top:
            return self.PREMIUM

        # Discount: price is in lower half of range (above swing low, below midpoint)
        # Only LONG signals
        if range_bottom < price < midpoint:
            return self.DISCOUNT

        # Price outside the range entirely
        return None

    def allowed_direction(self, zone: str | None) -> str | None:
        if zone == self.PREMIUM:
            return "short"
        elif zone == self.DISCOUNT:
            return "long"
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_zonation.py -v
```
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add sniperbot/strategy/zonation.py tests/test_zonation.py
git commit -m "feat: add Zonation for premium/discount determination"
```

---

### Task 6: M1Confirmation — 2/3 M1 candle confirmation

**Files:**
- Create: `sniperbot/strategy/confirmation.py`
- Create: `tests/test_confirmation.py`

- [ ] **Step 1: Write test file `tests/test_confirmation.py`**

```python
import pandas as pd
import pytest
from sniperbot.strategy.confirmation import M1Confirmation


def make_m1_df(closes: list[float], opens: list[float] | None = None) -> pd.DataFrame:
    if opens is None:
        opens = closes  # default: doji candles if not specified
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
        # close > open for all 3 = 3 bullish
        df = make_m1_df(closes=[310, 311, 312], opens=[309, 310, 311])
        checker = M1Confirmation(bars_needed=2, total_bars=3)
        assert checker.check(df, "long") is True

    def test_2_bullish_1_bearish_confirm_long(self):
        df = make_m1_df(closes=[311, 310, 312], opens=[310, 311, 311])
        # candle 0: bullish (311>310), candle 1: bearish (310<311), candle 2: bullish (312>311)
        checker = M1Confirmation(bars_needed=2, total_bars=3)
        assert checker.check(df, "long") is True

    def test_1_bullish_2_bearish_rejects_long(self):
        df = make_m1_df(closes=[311, 309, 308], opens=[310, 311, 310])
        # candle 0: bullish, 1: bearish, 2: bearish -> only 1/3 bullish
        checker = M1Confirmation(bars_needed=2, total_bars=3)
        assert checker.check(df, "long") is False

    def test_2_bearish_1_bullish_confirm_short(self):
        df = make_m1_df(closes=[309, 308, 310], opens=[310, 310, 309])
        # candle 0: bearish, 1: bearish, 2: bullish -> 2/3 bearish
        checker = M1Confirmation(bars_needed=2, total_bars=3)
        assert checker.check(df, "short") is True

    def test_1_bearish_2_bullish_rejects_short(self):
        df = make_m1_df(closes=[309, 311, 312], opens=[310, 310, 310])
        # candle 0: bearish, 1: bullish, 2: bullish -> only 1/3 bearish
        checker = M1Confirmation(bars_needed=2, total_bars=3)
        assert checker.check(df, "short") is False

    def test_fewer_than_required_bars_returns_false(self):
        df = make_m1_df(closes=[310, 311], opens=[309, 310])  # only 2 bars
        checker = M1Confirmation(bars_needed=2, total_bars=3)
        assert checker.check(df, "long") is False

    def test_doji_candles_not_counted_as_bullish_or_bearish(self):
        # Doji: close == open. Not bullish, not bearish.
        df = make_m1_df(closes=[310, 311, 311], opens=[310, 310, 311])
        # candle 0: doji, 1: bullish, 2: doji -> 1/3
        checker = M1Confirmation(bars_needed=2, total_bars=3)
        assert checker.check(df, "long") is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_confirmation.py -v
```
Expected: FAIL

- [ ] **Step 3: Write `sniperbot/strategy/confirmation.py`**

```python
import pandas as pd


class M1Confirmation:
    def __init__(self, bars_needed: int = 2, total_bars: int = 3):
        self.bars_needed = bars_needed
        self.total_bars = total_bars

    def check(self, df_m1: pd.DataFrame, direction: str) -> bool:
        if len(df_m1) < self.total_bars:
            return False

        # Take the last N bars
        bars = df_m1.iloc[-self.total_bars:]

        if direction == "long":
            bull_count = sum(1 for _, row in bars.iterrows() if row["close"] > row["open"])
            return bull_count >= self.bars_needed
        elif direction == "short":
            bear_count = sum(1 for _, row in bars.iterrows() if row["close"] < row["open"])
            return bear_count >= self.bars_needed
        else:
            return False
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_confirmation.py -v
```
Expected: 7 PASS

- [ ] **Step 5: Commit**

```bash
git add sniperbot/strategy/confirmation.py tests/test_confirmation.py
git commit -m "feat: add M1Confirmation for 2/3 candle confirmation"
```

---

### Task 7: TargetCalculator — TP liquidity levels

**Files:**
- Create: `sniperbot/strategy/targets.py`
- Create: `tests/test_targets.py`

- [ ] **Step 1: Write test file `tests/test_targets.py`**

```python
import pandas as pd
from datetime import datetime, timedelta
from sniperbot.strategy.swing_points import SwingPoint
from sniperbot.strategy.targets import TargetCalculator, LiquidityLevel


def make_session_df(high: float, low: float, start_hour: int, end_hour: int) -> pd.DataFrame:
    data = {
        "open": [(high + low) / 2],
        "high": [high],
        "low": [low],
        "close": [(high + low) / 2],
        "volume": [1000],
    }
    index = [pd.Timestamp(f"2026-05-21 {start_hour:02d}:00:00")]
    return pd.DataFrame(data, index=index)


class TestTargetCalculator:
    def test_filters_targets_below_min_distance(self):
        calc = TargetCalculator(min_distance_ticks=40, tick_size=0.01)
        levels = [
            LiquidityLevel(type="high", price=401.0, source="asia"),
            LiquidityLevel(type="low", price=399.5, source="asia"),
            LiquidityLevel(type="high", price=400.2, source="london"),
        ]
        # Entry at 400.0, min distance = 40 * 0.01 = $0.40
        # 401.0 -> distance $1.00 = 100 ticks (OK)
        # 399.5 -> distance $0.50 = 50 ticks (OK)
        # 400.2 -> distance $0.20 = 20 ticks (FILTERED)
        result = calc.filter_by_distance(400.0, levels)
        assert len(result) == 2
        assert all(abs(l.price - 400.0) >= 0.40 for l in result)

    def test_entries_sorted_by_distance(self):
        calc = TargetCalculator(min_distance_ticks=0, tick_size=0.01)
        levels = [
            LiquidityLevel(type="high", price=405.0, source="asia"),
            LiquidityLevel(type="high", price=402.0, source="london"),
            LiquidityLevel(type="high", price=410.0, source="prev_ny"),
        ]
        result = calc.filter_by_distance(400.0, levels)
        assert result[0].price == 402.0
        assert result[1].price == 405.0
        assert result[2].price == 410.0

    def test_long_targets_are_above_entry(self):
        calc = TargetCalculator(min_distance_ticks=0, tick_size=0.01)
        swings = [
            SwingPoint(type="high", price=403.0, index=5,
                       timestamp=datetime(2026, 5, 21, 14, 0), excursion_ticks=150),
            SwingPoint(type="high", price=406.0, index=10,
                       timestamp=datetime(2026, 5, 21, 15, 0), excursion_ticks=200),
            SwingPoint(type="low", price=398.0, index=3,
                       timestamp=datetime(2026, 5, 21, 13, 0), excursion_ticks=100),
        ]
        asia = (pd.Timestamp("2026-05-21 00:00"), pd.Timestamp("2026-05-21 09:00"))
        london = (pd.Timestamp("2026-05-21 09:00"), pd.Timestamp("2026-05-21 11:00"))
        prev_ny = (pd.Timestamp("2026-05-20 13:30"), pd.Timestamp("2026-05-20 20:00"))

        # For a long entry at 400, targets are above entry: swing highs
        targets = calc.get_targets_for_long(400.0, swings, asia, london, prev_ny)
        # Should get swing highs (403, 406), both > 400
        assert all(t.price > 400.0 for t in targets)
        # Sorted by distance
        assert targets[0].price <= targets[-1].price

    def test_short_targets_are_below_entry(self):
        calc = TargetCalculator(min_distance_ticks=0, tick_size=0.01)
        swings = [
            SwingPoint(type="low", price=397.0, index=5,
                       timestamp=datetime(2026, 5, 21, 14, 0), excursion_ticks=150),
            SwingPoint(type="low", price=394.0, index=10,
                       timestamp=datetime(2026, 5, 21, 15, 0), excursion_ticks=200),
            SwingPoint(type="high", price=405.0, index=3,
                       timestamp=datetime(2026, 5, 21, 13, 0), excursion_ticks=100),
        ]
        asia = (pd.Timestamp("2026-05-21 00:00"), pd.Timestamp("2026-05-21 09:00"))
        london = (pd.Timestamp("2026-05-21 09:00"), pd.Timestamp("2026-05-21 11:00"))
        prev_ny = (pd.Timestamp("2026-05-20 13:30"), pd.Timestamp("2026-05-20 20:00"))

        targets = calc.get_targets_for_short(401.0, swings, asia, london, prev_ny)
        # For short, targets are swing lows below entry
        assert all(t.price < 401.0 for t in targets)

    def test_swing_targets_min_40_ticks_from_entry(self):
        calc = TargetCalculator(min_distance_ticks=40, tick_size=0.01)
        swings = [
            SwingPoint(type="high", price=400.3, index=5,
                       timestamp=datetime(2026, 5, 21, 14, 0), excursion_ticks=150),
            SwingPoint(type="high", price=402.0, index=10,
                       timestamp=datetime(2026, 5, 21, 15, 0), excursion_ticks=200),
        ]
        targets = calc._filter_swing_targets(400.0, swings, "high")
        # 400.3 is $0.30 away = 30 ticks -> FILTERED
        # 402.0 is $2.00 away = 200 ticks -> KEPT
        assert len(targets) == 1
        assert targets[0].price == 402.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_targets.py -v
```
Expected: FAIL

- [ ] **Step 3: Write `sniperbot/strategy/targets.py`**

```python
from dataclasses import dataclass, field
import pandas as pd
from sniperbot.strategy.swing_points import SwingPoint


@dataclass
class LiquidityLevel:
    type: str          # 'high' or 'low'
    price: float
    source: str        # 'asia', 'london', 'prev_ny', 'same_level', 'swing_m5'
    distance_ticks: float = 0.0


class TargetCalculator:
    def __init__(self, min_distance_ticks: int = 40, tick_size: float = 0.01):
        self.min_distance_ticks = min_distance_ticks
        self.tick_size = tick_size

    def filter_by_distance(self, entry_price: float,
                           levels: list[LiquidityLevel]) -> list[LiquidityLevel]:
        min_dist = self.min_distance_ticks * self.tick_size
        filtered = []
        for level in levels:
            dist = abs(level.price - entry_price)
            if dist >= min_dist:
                level.distance_ticks = dist / self.tick_size
                filtered.append(level)
        # Sort by distance from entry (closest first)
        filtered.sort(key=lambda l: l.distance_ticks)
        return filtered

    def _filter_swing_targets(self, entry_price: float, swings: list[SwingPoint],
                              target_type: str) -> list[LiquidityLevel]:
        levels = []
        for s in swings:
            if s.type == target_type:
                levels.append(LiquidityLevel(
                    type=s.type, price=s.price, source="swing_m5"
                ))
        return self.filter_by_distance(entry_price, levels)

    def get_targets_for_long(self, entry_price: float, swing_points: list[SwingPoint],
                             asia_session: tuple[pd.Timestamp, pd.Timestamp],
                             london_session: tuple[pd.Timestamp, pd.Timestamp],
                             prev_ny_session: tuple[pd.Timestamp, pd.Timestamp],
                             asia_df: pd.DataFrame | None = None,
                             london_df: pd.DataFrame | None = None,
                             prev_ny_df: pd.DataFrame | None = None) -> list[LiquidityLevel]:
        levels = []

        # Add session high/lows if dataframes provided
        for df, source in [(asia_df, "asia"), (london_df, "london"), (prev_ny_df, "prev_ny")]:
            if df is not None and not df.empty:
                session_high = df["high"].max()
                session_low = df["low"].min()
                levels.append(LiquidityLevel(type="high", price=session_high, source=source))
                levels.append(LiquidityLevel(type="low", price=session_low, source=source))

        # Add swing high targets
        levels.extend(self._filter_swing_targets(entry_price, swing_points, "high"))

        # For long, we only want targets ABOVE entry
        levels = [l for l in levels if l.price > entry_price]
        return self.filter_by_distance(entry_price, levels)

    def get_targets_for_short(self, entry_price: float, swing_points: list[SwingPoint],
                              asia_session: tuple[pd.Timestamp, pd.Timestamp],
                              london_session: tuple[pd.Timestamp, pd.Timestamp],
                              prev_ny_session: tuple[pd.Timestamp, pd.Timestamp],
                              asia_df: pd.DataFrame | None = None,
                              london_df: pd.DataFrame | None = None,
                              prev_ny_df: pd.DataFrame | None = None) -> list[LiquidityLevel]:
        levels = []

        for df, source in [(asia_df, "asia"), (london_df, "london"), (prev_ny_df, "prev_ny")]:
            if df is not None and not df.empty:
                session_high = df["high"].max()
                session_low = df["low"].min()
                levels.append(LiquidityLevel(type="high", price=session_high, source=source))
                levels.append(LiquidityLevel(type="low", price=session_low, source=source))

        levels.extend(self._filter_swing_targets(entry_price, swing_points, "low"))

        # For short, we only want targets BELOW entry
        levels = [l for l in levels if l.price < entry_price]
        return self.filter_by_distance(entry_price, levels)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_targets.py -v
```
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add sniperbot/strategy/targets.py tests/test_targets.py
git commit -m "feat: add TargetCalculator for multi-level TP liquidity"
```

---

### Task 8: RiskManager — daily loss gate

**Files:**
- Create: `sniperbot/execution/risk_manager.py`
- Create: `tests/test_risk_manager.py`

- [ ] **Step 1: Write test file `tests/test_risk_manager.py`**

```python
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
        # Simulate $801 loss (> 8% of 10000 = 800)
        rm.update_pnl(-801.0)
        assert rm.can_trade() is False
        assert rm.daily_loss_hit() is True

    def test_allows_trading_at_exact_limit(self):
        rm = RiskManager(max_daily_loss_pct=0.08)
        rm.start_session(account_equity=10000.0)
        rm.update_pnl(-800.0)  # Exactly 8%
        assert rm.can_trade() is False  # At or above limit

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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_risk_manager.py -v
```
Expected: FAIL

- [ ] **Step 3: Write `sniperbot/execution/risk_manager.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_risk_manager.py -v
```
Expected: 7 PASS

- [ ] **Step 5: Commit**

```bash
git add sniperbot/execution/risk_manager.py tests/test_risk_manager.py
git commit -m "feat: add RiskManager for daily loss limit"
```

---

### Task 9: OrderManager — Entry, trailing SL, TP management

**Files:**
- Create: `sniperbot/execution/order_manager.py`
- Create: `tests/test_order_manager.py`

- [ ] **Step 1: Write test file `tests/test_order_manager.py`**

```python
import pytest
from unittest.mock import MagicMock, call
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_order_manager.py -v
```
Expected: FAIL

- [ ] **Step 3: Write `sniperbot/execution/order_manager.py`**

```python
from sniperbot.strategy.swing_points import SwingPoint
from sniperbot.strategy.targets import LiquidityLevel
from sniperbot.data.ib_client import IBClient
from sniperbot.execution.risk_manager import RiskManager


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
            return False

        side = "buy" if direction == "long" else "sell"
        symbol = "NQ"
        qty = 1

        initial_sl_price = initial_sl_swing.price

        result = self.ib.submit_order(
            symbol=symbol, qty=qty, side=side, order_type="market",
            stop_loss=initial_sl_price,
        )

        if result and result.get("status") in ("Filled", "Submitted", "PreSubmitted"):
            self._current_sl = initial_sl_price
            self._tp_levels = tp_levels
            self._entry_price = entry_price
            self._direction = direction
            return True
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
        result = self.ib.close_position("NQ")
        return result.get("status") != "error"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_order_manager.py -v
```
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add sniperbot/execution/order_manager.py tests/test_order_manager.py
git commit -m "feat: add OrderManager for entry, trailing SL, and TP"
```

---

### Task 10: Main orchestrator — scheduler, main loop, wiring

**Files:**
- Create: `sniperbot/main.py`

This is the entry point that wires all modules together. No unit tests for the orchestrator (it's an integration point), but it should be structured for clarity.

- [ ] **Step 1: Write `sniperbot/main.py`**

```python
import time
import signal
import sys
import logging
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path

import pandas as pd

from sniperbot.config import (
    IB_HOST, IB_PORT, IB_CLIENT_ID, SYMBOL, POSITION_SIZE,
    KILLZONE_START, KILLZONE_END, SWING_WINDOW_LEFT, SWING_WINDOW_RIGHT,
    MIN_SWING_EXCURSION_TICKS, FVG_LOOKBACK_CANDLES, M1_CONFIRMATION_BARS,
    M1_BULLISH_NEEDED, M1_BEARISH_NEEDED, MIN_TP_DISTANCE_TICKS,
    MAX_DAILY_LOSS_PCT, MAX_RETRIES, RETRY_BASE_DELAY, TICK_SIZE,
)
from sniperbot.data.ib_client import IBClient
from sniperbot.strategy.swing_points import SwingPointDetector
from sniperbot.strategy.fvg import FVGDetector
from sniperbot.strategy.zonation import Zonation
from sniperbot.strategy.confirmation import M1Confirmation
from sniperbot.strategy.targets import TargetCalculator
from sniperbot.execution.risk_manager import RiskManager
from sniperbot.execution.order_manager import OrderManager

# Logging setup
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
log_date = datetime.now().strftime("%Y-%m-%d")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_dir / f"{log_date}.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def parse_time(time_str: str) -> dt_time:
    h, m = map(int, time_str.split(":"))
    return dt_time(h, m)


def is_weekday() -> bool:
    return datetime.now().weekday() < 5


def in_killzone() -> bool:
    now = datetime.now().time()
    start = parse_time(KILLZONE_START)
    end = parse_time(KILLZONE_END)
    return start <= now <= end


def sleep_until(target_time: dt_time):
    now = datetime.now()
    target = now.replace(hour=target_time.hour, minute=target_time.minute, second=0, microsecond=0)
    if target < now:
        target += timedelta(days=1)
    seconds = (target - now).total_seconds()
    if seconds > 0:
        logger.info(f"Sleeping {seconds:.0f}s until {target_time}")
        time.sleep(seconds)


def run():
    logger.info("=== SniperBot ICT starting ===")

    # Initialize components and connect to IB Gateway
    ib_client = IBClient(host=IB_HOST, port=IB_PORT, client_id=IB_CLIENT_ID)
    logger.info(f"Connecting to IB Gateway at {IB_HOST}:{IB_PORT}...")
    if not ib_client.connect():
        logger.error("Failed to connect to IB Gateway. Ensure IB Gateway is running.")
        sys.exit(1)
    logger.info("Connected to IB Gateway")

    risk_mgr = RiskManager(max_daily_loss_pct=MAX_DAILY_LOSS_PCT)
    order_mgr = OrderManager(ib_client=ib_client, risk_manager=risk_mgr)
    swing_detector = SwingPointDetector(
        window_left=SWING_WINDOW_LEFT, window_right=SWING_WINDOW_RIGHT,
        min_excursion_ticks=MIN_SWING_EXCURSION_TICKS,
    )
    fvg_detector = FVGDetector(lookback=FVG_LOOKBACK_CANDLES)
    zonation = Zonation()
    confirmation = M1Confirmation(
        bars_needed=M1_BULLISH_NEEDED, total_bars=M1_CONFIRMATION_BARS,
    )
    target_calc = TargetCalculator(min_distance_ticks=MIN_TP_DISTANCE_TICKS, tick_size=TICK_SIZE)

    # Graceful shutdown
    running = True

    def handle_sigterm(signum, frame):
        nonlocal running
        logger.info("Received shutdown signal")
        running = False

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    active_fvgs: list = []
    last_m5_index = None

    while running:
        if not is_weekday():
            logger.info("Weekend — sleeping until Monday")
            now = datetime.now()
            days_until_monday = (7 - now.weekday()) % 7
            if days_until_monday == 0:
                days_until_monday = 1
            next_monday = now + timedelta(days=days_until_monday)
            sleep_until(parse_time(KILLZONE_START))
            continue

        if not in_killzone():
            wait_target = parse_time(KILLZONE_START)
            logger.info(f"Outside killzone — waiting for {KILLZONE_START}")
            sleep_until(wait_target)
            continue

        # === INSIDE KILLZONE ===
        # Start-of-session initialization
        try:
            account = ib_client.get_account()
            risk_mgr.start_session(account["equity"])
        except Exception as e:
            logger.error(f"Failed to get account: {e}")
            time.sleep(60)
            continue

        # Check for existing position (bot restart mid-session)
        existing = ib_client.get_position(SYMBOL)
        in_trade = existing is not None

        while in_killzone() and running:
            try:
                # Fetch M5 data with retry
                df_m5 = pd.DataFrame()
                for attempt in range(MAX_RETRIES):
                    try:
                        df_m5 = ib_client.fetch_bars(SYMBOL, "5Min", limit=FVG_LOOKBACK_CANDLES + 10)
                        break
                    except Exception as e:
                        logger.warning(f"Fetch M5 attempt {attempt+1} failed: {e}")
                        time.sleep(RETRY_BASE_DELAY * (2 ** attempt))

                if df_m5.empty or len(df_m5) < 10:
                    logger.warning("Insufficient M5 data, waiting 60s")
                    time.sleep(60)
                    continue

                current_m5_index = df_m5.index[-1]

                # === Strategy chain (only if not already in a trade) ===
                if not in_trade:
                    # Skip if we already processed this candle
                    if current_m5_index == last_m5_index:
                        time.sleep(30)
                        continue

                    last_m5_index = current_m5_index

                    # 1. Detect swing points
                    swings = swing_detector.detect(df_m5)

                    # 2. Determine zone (Premium/Discount)
                    current_price = df_m5["close"].iloc[-1]
                    zone = zonation.determine(current_price, swings)
                    if zone is None:
                        logger.debug(f"No valid zone at {current_price}")
                        time.sleep(30)
                        continue

                    allowed_dir = zonation.allowed_direction(zone)

                    # 3. Detect FVGs and update closure tracking
                    new_fvgs = fvg_detector.detect(df_m5)
                    active_fvgs = fvg_detector.update_closure(active_fvgs + new_fvgs, df_m5)
                    active_fvgs = [f for f in active_fvgs if not f.closed]

                    # 4. Check if price closed inside an active FVG
                    signal_fvg = None
                    for fvg in active_fvgs:
                        if fvg_detector.is_price_inside(current_price, fvg):
                            # FVG direction must match zone direction
                            fvg_dir = "long" if fvg.type == "bullish" else "short"
                            if fvg_dir == allowed_dir:
                                signal_fvg = fvg
                                break

                    if signal_fvg is None:
                        time.sleep(30)
                        continue

                    logger.info(f"Signal: {allowed_dir.upper()} — "
                                f"Zone={zone}, FVG={signal_fvg.type}, "
                                f"Price={current_price}, Gap=({signal_fvg.bottom:.2f}-{signal_fvg.top:.2f})")

                    # 5. Wait for M1 confirmation
                    # Wait until next M1 candle forms (up to 60s)
                    time.sleep(60)

                    df_m1 = pd.DataFrame()
                    for attempt in range(MAX_RETRIES):
                        try:
                            df_m1 = ib_client.fetch_bars(SYMBOL, "1Min", limit=M1_CONFIRMATION_BARS + 5)
                            break
                        except Exception:
                            time.sleep(RETRY_BASE_DELAY * (2 ** attempt))

                    if len(df_m1) < M1_CONFIRMATION_BARS:
                        logger.debug("Insufficient M1 data for confirmation")
                        time.sleep(30)
                        continue

                    # 6. Check 2/3 confirmation
                    m1_confirmed = confirmation.check(df_m1, allowed_dir)
                    if not m1_confirmed:
                        logger.info(f"M1 2/3 NOT confirmed for {allowed_dir}")
                        time.sleep(30)
                        continue

                    logger.info(f"M1 2/3 CONFIRMED for {allowed_dir}")

                    # 7. Calculate TP levels
                    if allowed_dir == "long":
                        tp_levels = target_calc.get_targets_for_long(
                            current_price, swings, None, None, None
                        )
                    else:
                        tp_levels = target_calc.get_targets_for_short(
                            current_price, swings, None, None, None
                        )

                    if not tp_levels:
                        logger.info("No valid TP targets (all < min distance), skipping")
                        time.sleep(30)
                        continue

                    # 8. Set initial SL at penultimate swing point
                    if allowed_dir == "long":
                        lows = sorted(
                            [s for s in swings if s.type == "low"],
                            key=lambda s: s.index, reverse=True
                        )
                        penultimate_swing = lows[1] if len(lows) > 1 else lows[0] if lows else None
                    else:
                        highs = sorted(
                            [s for s in swings if s.type == "high"],
                            key=lambda s: s.index, reverse=True
                        )
                        penultimate_swing = highs[1] if len(highs) > 1 else highs[0] if highs else None

                    if penultimate_swing is None:
                        logger.info("No swing point for SL, skipping")
                        time.sleep(30)
                        continue

                    # 9. ENTRY
                    logger.info(f">>> ENTRY {allowed_dir.upper()} @ ~{current_price:.2f} "
                                f"| SL={penultimate_swing.price:.2f} "
                                f"| TP targets: {[f'{t.price:.2f}' for t in tp_levels[:3]]}")

                    entered = order_mgr.enter_trade(
                        allowed_dir, current_price, penultimate_swing, tp_levels
                    )
                    if entered:
                        in_trade = True
                        logger.info("Order submitted successfully")
                    else:
                        logger.warning("Entry rejected by risk manager or broker")

                else:
                    # === IN TRADE: monitor for trailing SL and TP ===
                    position = ib_client.get_position(SYMBOL)
                    if position is None:
                        # Position closed (TP or SL hit)
                        in_trade = False
                        logger.info("Position closed — returning to monitoring")
                        continue

                    current_price = position["current_price"]

                    # Check if TP was hit
                    if order_mgr.check_tp_hit(current_price):
                        logger.info(f"TP level reached at {current_price:.2f}")
                        order_mgr.close_position()
                        in_trade = False
                        continue

                    # Refresh data for new swing points (trailing SL)
                    df_m5_latest = ib_client.fetch_bars(SYMBOL, "5Min", limit=20)
                    new_swings = swing_detector.detect(df_m5_latest)

                    # Filter to swings that formed AFTER entry
                    if order_mgr._entry_price is not None:
                        new_swings = [s for s in new_swings
                                      if s.price not in [sp.price for sp in swings]]

                    for ns in new_swings:
                        if ns.type == ("low" if order_mgr._direction == "long" else "high"):
                            if order_mgr.update_trailing_sl(
                                ns, order_mgr._current_sl or 0, order_mgr._direction or ""
                            ):
                                logger.info(f"SL trailed to {order_mgr._current_sl:.2f}")

                    time.sleep(30)

            except Exception as e:
                logger.error(f"Main loop error: {e}", exc_info=True)
                time.sleep(60)

    logger.info("=== SniperBot ICT shutting down ===")


if __name__ == "__main__":
    run()
```

- [ ] **Step 2: Verify the module imports correctly**

```bash
python -c "from sniperbot.main import run; print('main module OK')"
```

Expected: prints `main module OK`. Note: will fail if IB Gateway is not running (connection error), but the import itself should succeed.

- [ ] **Step 3: Commit**

```bash
git add sniperbot/main.py
git commit -m "feat: add main orchestrator with scheduler, strategy loop, and trade monitoring"
```

---

### Task 11: Integration smoke test

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
import pandas as pd
from datetime import datetime
from unittest.mock import MagicMock, patch
from sniperbot.strategy.swing_points import SwingPointDetector
from sniperbot.strategy.fvg import FVGDetector
from sniperbot.strategy.zonation import Zonation
from sniperbot.strategy.confirmation import M1Confirmation
from sniperbot.strategy.targets import TargetCalculator
from sniperbot.strategy.swing_points import SwingPoint


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
        # Build M5 data with:
        # - A significant swing low (discount zone)
        # - A bullish FVG
        # - Price closing inside the FVG in discount zone
        highs = [
            405, 404, 403, 402, 401,  # descending into swing low area
            400, 399, 398,  # swing low forms at ~398
            399, 400, 401, 402, 403,  # recovery
            404, 403, 402,  # slight retrace, FVG forms
            403, 404, 405, 406,  # rally continues
        ]
        lows = [
            403, 402, 401, 400, 399,
            398, 397, 396,
            397, 398, 399, 400, 401,
            402, 401, 400,
            401, 402, 403, 404,
        ]
        closes = [
            404, 403, 402, 401, 400,
            399, 398, 397,
            398, 399, 400, 401, 402,
            403, 402, 401,
            402, 403, 404, 405,
        ]

        df_m5 = make_ohlcv(highs, lows, closes)

        # Run strategy chain
        swing_detector = SwingPointDetector(window_left=5, window_right=3, min_excursion_ticks=50)
        fvg_detector = FVGDetector(lookback=20)
        zonation = Zonation()

        swings = swing_detector.detect(df_m5)
        assert len(swings) > 0, "Should detect at least one swing point"

        current_price = closes[-1]
        zone = zonation.determine(current_price, swings)

        fvgs = fvg_detector.detect(df_m5)

        # Verify the chain produces meaningful output
        # (actual signal depends on exact data, we just verify no exceptions)
        assert zone in (Zonation.PREMIUM, Zonation.DISCOUNT, None)
        assert isinstance(fvgs, list)

    def test_m1_confirmation_with_real_pattern(self):
        """Test M1 confirmation against the 3-candle rule."""
        closes = [400.0, 401.0, 402.0]
        opens = [399.5, 400.5, 401.5]
        n = len(closes)
        df_m1 = pd.DataFrame({
            "open": opens,
            "high": [max(o, c) + 0.2 for o, c in zip(opens, closes)],
            "low": [min(o, c) - 0.2 for o, c in zip(opens, closes)],
            "close": closes,
            "volume": [500] * n,
        }, index=pd.date_range("2026-05-21 15:30", periods=n, freq="1min"))

        checker = M1Confirmation(bars_needed=2, total_bars=3)
        # All 3 are bullish -> LONG confirmed
        assert checker.check(df_m1, "long") is True
        assert checker.check(df_m1, "short") is False
```

- [ ] **Step 2: Run integration tests**

```bash
pytest tests/test_integration.py -v
```
Expected: 2 PASS

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/ -v
```
Expected: all ~47 tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add integration smoke test for full strategy chain"
```

---

## Execution Order

Tasks must run sequentially: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11.

Each task depends on the previous one for imports and shared types.
