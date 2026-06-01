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

        # We need to mock qualifyContracts to return something so _get_contract works
        ib.qualifyContracts.return_value = [MagicMock()]

        client.connect()
        df = client.fetch_bars("NQ", "5Min", limit=10)

        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert len(df) == 1
        assert df.iloc[0]["close"] == 20050.0
        assert df.index.name == "timestamp"

    def test_requests_correct_duration_and_bar_size(self, mock_ib):
        client, ib = mock_ib
        ib.reqHistoricalData.return_value = []
        ib.qualifyContracts.return_value = [MagicMock()]

        client.connect()
        client.fetch_bars("NQ", "5Min", limit=300)

        call_args = ib.reqHistoricalData.call_args[1]
        assert call_args["barSizeSetting"] == "5 mins"
        assert "D" in call_args["durationStr"]

    def test_returns_empty_dataframe_when_no_data(self, mock_ib):
        client, ib = mock_ib
        ib.reqHistoricalData.return_value = []
        ib.qualifyContracts.return_value = [MagicMock()]

        client.connect()
        df = client.fetch_bars("NQ", "5Min", limit=10)
        assert len(df) == 0

    def test_returns_empty_dataframe_when_not_connected(self, mock_ib):
        client, ib = mock_ib
        df = client.fetch_bars("NQ", "5Min", limit=10)
        assert len(df) == 0


class TestSubmitOrder:
    def test_submits_market_buy_order_correctly(self, mock_ib):
        client, ib = mock_ib
        mock_trade = MagicMock()
        mock_trade.order.orderId = 123
        mock_trade.orderStatus.status = "Filled"
        ib.placeOrder.return_value = mock_trade
        ib.qualifyContracts.return_value = [MagicMock()]

        client.connect()
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
        ib.qualifyContracts.return_value = [MagicMock()]

        client.connect()
        result = client.submit_order("NQ", 1, "sell", "market", stop_loss=19900.0)

        assert result["id"] == 456
        assert result["status"] == "Submitted"

    def test_returns_error_when_not_connected(self, mock_ib):
        client, ib = mock_ib
        result = client.submit_order("NQ", 1, "buy", "market")
        assert result["status"] == "error"
        assert result["error"] == "not connected"


class TestGetAccount:
    def test_returns_account_summary(self, mock_ib):
        client, ib = mock_ib
        ib.accountSummary.return_value = [
            MagicMock(tag="NetLiquidation", value="100000.0", currency="USD"),
            MagicMock(tag="AvailableFunds", value="50000.0", currency="USD"),
        ]

        client.connect()
        account = client.get_account()
        assert account["equity"] == 100000.0
        assert account["cash"] == 50000.0

    def test_returns_defaults_when_not_connected(self, mock_ib):
        client, ib = mock_ib
        account = client.get_account()
        assert account["equity"] == 0.0
        assert account["cash"] == 0.0


class TestGetPosition:
    def test_returns_none_when_not_connected(self, mock_ib):
        client, ib = mock_ib
        pos = client.get_position("NQ")
        assert pos is None

    def test_returns_position_when_found(self, mock_ib):
        client, ib = mock_ib
        mock_pos = MagicMock()
        mock_pos.contract.symbol = "NQ"
        mock_pos.contract.exchange = "CME"
        mock_pos.position = 2
        mock_pos.avgCost = 20000.0
        mock_pos.unrealizedPNL = 500.0
        mock_pos.markPrice = 20250.0
        ib.positions.return_value = [mock_pos]
        ib.qualifyContracts.return_value = [MagicMock()]

        client.connect()
        pos = client.get_position("NQ")
        assert pos["symbol"] == "NQ"
        assert pos["qty"] == 2
        assert pos["side"] == "long"
        assert pos["avg_entry_price"] == 20000.0
        assert pos["unrealized_pl"] == 500.0
        assert pos["current_price"] == 20250.0


class TestClosePosition:
    def test_returns_error_when_not_connected(self, mock_ib):
        client, ib = mock_ib
        result = client.close_position("NQ")
        assert result["status"] == "error"

    def test_returns_no_position_when_no_position_found(self, mock_ib):
        client, ib = mock_ib
        ib.positions.return_value = []
        ib.qualifyContracts.return_value = [MagicMock()]

        client.connect()
        result = client.close_position("NQ")
        assert result["status"] == "no position"

    def test_closes_long_position(self, mock_ib):
        client, ib = mock_ib
        mock_pos = MagicMock()
        mock_pos.contract.symbol = "NQ"
        mock_pos.contract.exchange = "CME"
        mock_pos.position = 2
        mock_pos.avgCost = 20000.0
        ib.positions.return_value = [mock_pos]

        mock_trade = MagicMock()
        mock_trade.orderStatus.status = "Filled"
        ib.placeOrder.return_value = mock_trade
        ib.qualifyContracts.return_value = [MagicMock()]

        client.connect()
        result = client.close_position("NQ")
        assert result["status"] == "Filled"


class TestCancelOrder:
    def test_cancels_order(self, mock_ib):
        client, ib = mock_ib
        client.connect()
        result = client.cancel_order(123)
        ib.cancelOrder.assert_called_once_with(123)
        assert result["id"] == 123
        assert result["status"] == "cancelled"

    def test_returns_error_when_not_connected(self, mock_ib):
        client, ib = mock_ib
        result = client.cancel_order(123)
        assert result["status"] == "error"
