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

# Trading hours (Italy time)
TRADING_START = "15:30"
TRADING_END = "22:00"

# Swing point detection (M5)
SWING_WINDOW_LEFT = 3
SWING_WINDOW_RIGHT = 3
MIN_SWING_EXCURSION_DOLLARS = 0  # nessun minimo in dollari

# FVG detection
FVG_LOOKBACK_CANDLES = 800  # fetch ~3.5 giorni di dati M5

# M1 confirmation
M1_CONFIRMATION_BARS = 3
M1_BULLISH_NEEDED = 2
M1_BEARISH_NEEDED = 2

# Take profit
MIN_TP_DISTANCE_DOLLARS = 5  # $5 = 1 tick NQ = 0.25 punti indice

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
