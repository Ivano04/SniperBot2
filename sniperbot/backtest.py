"""
Backtest walk-forward della strategia ICT dal 25 al 29 maggio 2026.
Nessun look-ahead: la simulazione processa le barre in ordine cronologico
usando solo i dati disponibili fino a quel momento.
"""
import sys
import time
from datetime import datetime, timedelta

import pandas as pd

from sniperbot.data.ib_client import IBClient
from sniperbot.strategy.swing_points import SwingPointDetector
from sniperbot.strategy.fvg import FVGDetector
from sniperbot.strategy.zonation import Zonation
from sniperbot.strategy.confirmation import M1Confirmation
from sniperbot.strategy.targets import TargetCalculator

# ---- Config (mirrors config.py) ----
IB_HOST = "127.0.0.1"
IB_PORT = 4002
SYMBOL = "NQ"
TICK_SIZE = 0.25
POINT_VALUE = 20  # $20 per punto NQ (4 tick x $5)
TRADING_START = "08:30"  # Chicago (15:30 Italy)
TRADING_END = "15:00"    # Chicago (22:00 Italy)
SWING_WINDOW_LEFT = 3
SWING_WINDOW_RIGHT = 3
MIN_SWING_EXCURSION = 0  # points
FVG_LOOKBACK = 800
M1_BARS_NEEDED = 2
M1_TOTAL_BARS = 3
MIN_TP_DISTANCE = 5  # dollars
ZONATION_MIN_EXCURSION = 5.0  # points

# Backtest period
BACKTEST_START = pd.Timestamp("2026-05-25 00:00:00", tz="US/Central")
BACKTEST_END = pd.Timestamp("2026-05-29 23:59:59", tz="US/Central")


def fetch_m5_chunks() -> pd.DataFrame:
    """Fetch all M5 bars from IB in chunks."""
    print("[FETCH] Connessione IB per M5...")
    client = IBClient(host=IB_HOST, port=IB_PORT, client_id=600)
    if not client.connect():
        print("ERRORE: Connessione IB fallita")
        sys.exit(1)

    df = client.fetch_bars(SYMBOL, "5Min", limit=1500)
    client.disconnect()

    if df.empty:
        print("ERRORE: Nessun dato M5")
        sys.exit(1)

    # Filter to backtest period
    df = df[(df.index >= BACKTEST_START) & (df.index <= BACKTEST_END)]
    # Remove timezone to simplify comparisons
    df = df.copy()
    if hasattr(df.index, 'tz'):
        df.index = df.index.tz_convert("US/Central")
    print(f"[FETCH] {len(df)} barre M5 ({df.index[0]} -> {df.index[-1]})")
    return df


def fetch_m1_chunks() -> pd.DataFrame:
    """Fetch M1 bars for the backtest period using multiple requests."""
    print("[FETCH] Connessione IB per M1 (chunked)...")
    client = IBClient(host=IB_HOST, port=IB_PORT, client_id=601)
    if not client.connect():
        print("ERRORE: Connessione IB fallita per M1")
        sys.exit(1)

    dfs = []
    # Fetch in chunks going backwards: May 29, May 28, May 27, May 26, May 25
    end_dates = [
        "20260529 23:59:00 US/Central",
        "20260528 23:59:00 US/Central",
        "20260527 23:59:00 US/Central",
        "20260526 23:59:00 US/Central",
        "20260525 23:59:00 US/Central",
    ]

    for i, end_date in enumerate(end_dates):
        print(f"  Chunk {i+1}/{len(end_dates)}: ending {end_date}...")
        try:
            bars = client.ib.reqHistoricalData(
                client._get_contract(SYMBOL),
                endDateTime=end_date,
                durationStr="2 D",
                barSizeSetting="1 min",
                whatToShow="TRADES",
                useRTH=False,
                formatDate=1,
            )
            if bars:
                data = [{"open": b.open, "high": b.high, "low": b.low,
                         "close": b.close, "volume": b.volume} for b in bars]
                chunk = pd.DataFrame(
                    data,
                    index=pd.DatetimeIndex([b.date for b in bars]),
                )
                chunk.index.name = "timestamp"
                dfs.append(chunk)
                print(f"    {len(chunk)} barre ricevute")
        except Exception as e:
            print(f"    Errore: {e}")
        time.sleep(3)  # pacing

    client.disconnect()

    if not dfs:
        print("ERRORE: Nessun dato M1")
        sys.exit(1)

    df_all = pd.concat(dfs)
    df_all = df_all[~df_all.index.duplicated(keep="first")]
    df_all = df_all.sort_index()
    if hasattr(df_all.index, 'tz'):
        df_all.index = df_all.index.tz_convert("US/Central")
    df_all = df_all[(df_all.index >= BACKTEST_START) & (df_all.index <= BACKTEST_END)]
    print(f"[FETCH] {len(df_all)} barre M1 totali ({df_all.index[0]} -> {df_all.index[-1]})")
    return df_all


def run_backtest(df_m5: pd.DataFrame, df_m1: pd.DataFrame):
    print("\n" + "=" * 70)
    print("BACKTEST WALK-FORWARD — Strategia ICT")
    print(f"Periodo: {df_m5.index[0]} -> {df_m5.index[-1]}")
    print(f"Barre M5: {len(df_m5)}, Barre M1: {len(df_m1)}")
    print("=" * 70)

    swing_detector = SwingPointDetector(
        window_left=SWING_WINDOW_LEFT,
        window_right=SWING_WINDOW_RIGHT,
        min_excursion=MIN_SWING_EXCURSION,
    )
    fvg_detector = FVGDetector(lookback=FVG_LOOKBACK)
    zonation = Zonation(min_excursion=ZONATION_MIN_EXCURSION)
    confirmation = M1Confirmation(bars_needed=M1_BARS_NEEDED, total_bars=M1_TOTAL_BARS)
    target_calc = TargetCalculator(
        min_distance_ticks=int(MIN_TP_DISTANCE / 5),  # $5 = 1 tick
        tick_size=TICK_SIZE,
    )

    trades = []
    active_fvgs = []
    in_trade = False
    trade_entry_price = 0.0
    trade_direction = ""
    trade_sl = 0.0
    trade_tp_levels = []
    trade_entry_bar = None
    trade_entry_swings = []

    warmup = 50  # bars needed before we have enough context

    def in_trading_hours(ts: pd.Timestamp) -> bool:
        """Check if timestamp is within trading hours (Mon-Fri, 08:30-15:00 Chicago)."""
        if ts.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        t = ts.time()
        start = pd.Timestamp(TRADING_START).time()
        end = pd.Timestamp(TRADING_END).time()
        return start <= t <= end

    for idx in range(warmup, len(df_m5)):
        current_data = df_m5.iloc[:idx + 1]
        current_price = float(current_data["close"].iloc[-1])
        current_ts = current_data.index[-1]

        # Skip bars outside trading hours (unless already in a trade)
        if not in_trade and not in_trading_hours(current_ts):
            continue

        # ---- IN TRADE: monitor ----
        if in_trade:
            bar_high = float(current_data["high"].iloc[-1])
            bar_low = float(current_data["low"].iloc[-1])

            # Check TP hit
            tp_hit = False
            for tp in trade_tp_levels:
                if trade_direction == "long" and bar_high >= tp.price:
                    tp_hit = True
                    exit_price = tp.price
                    break
                elif trade_direction == "short" and bar_low <= tp.price:
                    tp_hit = True
                    exit_price = tp.price
                    break

            if tp_hit:
                pnl_points = abs(exit_price - trade_entry_price)
                pnl_dollars = pnl_points * POINT_VALUE
                if trade_direction == "short":
                    pnl_dollars = pnl_points * POINT_VALUE  # positive for short
                # For long: exit > entry = profit; For short: exit < entry = profit
                if trade_direction == "long":
                    pnl_dollars = (exit_price - trade_entry_price) * POINT_VALUE
                else:
                    pnl_dollars = (trade_entry_price - exit_price) * POINT_VALUE

                trades.append({
                    "entry_time": str(trade_entry_bar)[:19],
                    "exit_time": str(current_ts)[:19],
                    "direction": trade_direction,
                    "entry_price": trade_entry_price,
                    "exit_price": exit_price,
                    "exit_reason": "TP",
                    "pnl_points": round(pnl_dollars / POINT_VALUE, 2),
                    "pnl_dollars": round(pnl_dollars, 2),
                })
                print(f"  [TRADE] {trade_direction.upper()} TP HIT | "
                      f"Entry={trade_entry_price:.0f} Exit={exit_price:.0f} | "
                      f"P&L=${pnl_dollars:+.0f} ({pnl_dollars/POINT_VALUE:+.1f}pt)")
                in_trade = False
                continue

            # Check SL hit
            sl_hit = False
            if trade_direction == "long" and bar_low <= trade_sl:
                sl_hit = True
                exit_price = trade_sl
            elif trade_direction == "short" and bar_high >= trade_sl:
                sl_hit = True
                exit_price = trade_sl

            if sl_hit:
                if trade_direction == "long":
                    pnl_dollars = (exit_price - trade_entry_price) * POINT_VALUE
                else:
                    pnl_dollars = (trade_entry_price - exit_price) * POINT_VALUE

                trades.append({
                    "entry_time": str(trade_entry_bar)[:19],
                    "exit_time": str(current_ts)[:19],
                    "direction": trade_direction,
                    "entry_price": trade_entry_price,
                    "exit_price": exit_price,
                    "exit_reason": "SL",
                    "pnl_points": round(pnl_dollars / POINT_VALUE, 2),
                    "pnl_dollars": round(pnl_dollars, 2),
                })
                print(f"  [TRADE] {trade_direction.upper()} SL HIT | "
                      f"Entry={trade_entry_price:.0f} Exit={exit_price:.0f} | "
                      f"P&L=${pnl_dollars:+.0f} ({pnl_dollars/POINT_VALUE:+.1f}pt)")
                in_trade = False
                continue

            # Trail SL with new swing points
            swings_now = swing_detector.detect(current_data)
            for ns in swings_now:
                if trade_direction == "long" and ns.type == "low":
                    if ns.price > trade_sl:
                        trade_sl = ns.price
                elif trade_direction == "short" and ns.type == "high":
                    if ns.price < trade_sl:
                        trade_sl = ns.price

            continue  # stay in trade, next bar

        # ---- NOT IN TRADE: look for entry ----
        # 1. Swing points
        swings = swing_detector.detect(current_data)

        # 2. Zone
        zone = zonation.determine(current_price, swings)
        if zone is None:
            continue

        allowed_dir = zonation.allowed_direction(zone)

        # 3. FVGs
        new_fvgs = fvg_detector.detect(current_data)
        all_fvgs = fvg_detector.update_closure(active_fvgs + new_fvgs, current_data)
        active_fvgs = [f for f in all_fvgs if not f.closed]

        # 4. Match
        signal_fvg = None
        for fvg in active_fvgs:
            if fvg_detector.is_price_inside(current_price, fvg):
                fvg_dir = "long" if fvg.type == "bullish" else "short"
                if fvg_dir == allowed_dir:
                    signal_fvg = fvg
                    break

        if signal_fvg is None:
            continue

        # 5. M1 confirmation
        m1_window = df_m1[df_m1.index <= current_ts].tail(M1_TOTAL_BARS)
        if len(m1_window) < M1_TOTAL_BARS:
            continue

        if not confirmation.check(m1_window, allowed_dir):
            continue

        # 6. Calculate TP levels
        if allowed_dir == "long":
            tp_levels = target_calc.get_targets_for_long(
                current_price, swings, None, None, None
            )
        else:
            tp_levels = target_calc.get_targets_for_short(
                current_price, swings, None, None, None
            )

        if not tp_levels:
            continue

        # 7. Set SL at penultimate swing point
        if allowed_dir == "long":
            lows = sorted(
                [s for s in swings if s.type == "low"],
                key=lambda s: s.index, reverse=True,
            )
            penultimate = lows[1] if len(lows) > 1 else (lows[0] if lows else None)
        else:
            highs = sorted(
                [s for s in swings if s.type == "high"],
                key=lambda s: s.index, reverse=True,
            )
            penultimate = highs[1] if len(highs) > 1 else (highs[0] if highs else None)

        if penultimate is None:
            continue

        # 8. ENTRY
        in_trade = True
        trade_entry_price = current_price
        trade_direction = allowed_dir
        trade_sl = penultimate.price
        trade_tp_levels = tp_levels
        trade_entry_bar = current_ts
        trade_entry_swings = swings

        print(f"\n[SIGNAL] {allowed_dir.upper()} @ {current_ts} | "
              f"Price={current_price:.0f} | Zone={zone} | "
              f"FVG={signal_fvg.type} gap={signal_fvg.bottom:.0f}-{signal_fvg.top:.0f} | "
              f"SL={trade_sl:.0f} | TP={[f'{t.price:.0f}' for t in tp_levels[:3]]}")

    # ---- Finalize: if still in trade at end of data ----
    if in_trade:
        exit_price = current_price
        if trade_direction == "long":
            pnl_dollars = (exit_price - trade_entry_price) * POINT_VALUE
        else:
            pnl_dollars = (trade_entry_price - exit_price) * POINT_VALUE
        trades.append({
            "entry_time": str(trade_entry_bar)[:19],
            "exit_time": "END_OF_DATA",
            "direction": trade_direction,
            "entry_price": trade_entry_price,
            "exit_price": exit_price,
            "exit_reason": "EOD",
            "pnl_points": round(pnl_dollars / POINT_VALUE, 2),
            "pnl_dollars": round(pnl_dollars, 2),
        })

    # ---- Report ----
    print("\n" + "=" * 70)
    print("REPORT FINALE")
    print("=" * 70)

    if not trades:
        print("Nessun trade eseguito nel periodo.")
        return

    df_trades = pd.DataFrame(trades)
    print(f"\nTrade totali: {len(trades)}")
    print(df_trades.to_string(index=True))
    print()

    wins = [t for t in trades if t["pnl_dollars"] > 0]
    losses = [t for t in trades if t["pnl_dollars"] <= 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    total_pnl = sum(t["pnl_dollars"] for t in trades)
    total_points = sum(t["pnl_points"] for t in trades)
    best = max(trades, key=lambda t: t["pnl_dollars"])
    worst = min(trades, key=lambda t: t["pnl_dollars"])

    print(f"Win rate:        {len(wins)}W / {len(losses)}L = {win_rate:.1f}%")
    print(f"P&L netto:       ${total_pnl:+.0f} ({total_points:+.1f} punti)")
    print(f"Trade migliore:  ${best['pnl_dollars']:+.0f} ({best['pnl_points']:+.1f}pt)")
    print(f"Trade peggiore:  ${worst['pnl_dollars']:+.0f} ({worst['pnl_points']:+.1f}pt)")

    if win_rate > 0:
        avg_win = sum(t["pnl_dollars"] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t["pnl_dollars"] for t in losses) / len(losses) if losses else 0
        print(f"Win media:       ${avg_win:+.0f}")
        print(f"Loss media:      ${avg_loss:+.0f}")
        if losses:
            total_win = sum(t["pnl_dollars"] for t in wins)
            total_loss = abs(sum(t["pnl_dollars"] for t in losses))
            pf = total_win / total_loss if total_loss > 0 else float("inf")
            print(f"Profit factor:   {pf:.2f}")

    # Max drawdown from equity curve
    equity = 0
    peak = 0
    max_dd = 0
    for t in trades:
        equity += t["pnl_dollars"]
        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)
    print(f"Max drawdown:    ${max_dd:.0f}")
    print()


if __name__ == "__main__":
    print("=== SniperBot ICT Backtest ===")
    print(f"Periodo: {BACKTEST_START} -> {BACKTEST_END}")

    # Fetch data
    df_m5 = fetch_m5_chunks()
    df_m1 = fetch_m1_chunks()

    # Run backtest
    run_backtest(df_m5, df_m1)
