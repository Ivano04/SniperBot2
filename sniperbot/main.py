import time
import signal
import sys
import logging
import argparse
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path

import pandas as pd

from sniperbot.config import (
    IB_HOST, IB_PORT, IB_CLIENT_ID, SYMBOL, POSITION_SIZE,
    TRADING_START, TRADING_END, SWING_WINDOW_LEFT, SWING_WINDOW_RIGHT,
    MIN_SWING_EXCURSION_DOLLARS, FVG_LOOKBACK_CANDLES, M1_CONFIRMATION_BARS,
    M1_BULLISH_NEEDED, M1_BEARISH_NEEDED, MIN_TP_DISTANCE_DOLLARS,
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
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_dir / f"{log_date}.log"),
    ],
    force=True,
)
logger = logging.getLogger(__name__)

# Silence ib_insync's verbose internal API logging
logging.getLogger("ib_insync").setLevel(logging.WARNING)
logging.getLogger("ib_insync.wrapper").setLevel(logging.WARNING)
logging.getLogger("ib_insync.client").setLevel(logging.WARNING)
logging.getLogger("ib_insync.ib").setLevel(logging.WARNING)


def parse_time(time_str: str) -> dt_time:
    h, m = map(int, time_str.split(":"))
    return dt_time(h, m)


def is_weekday() -> bool:
    return datetime.now().weekday() < 5


def in_trading_hours() -> bool:
    now = datetime.now().time()
    start = parse_time(TRADING_START)
    end = parse_time(TRADING_END)
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


def run(force_now: bool = False, force_entry: str | None = None):
    logger.info("=== SniperBot ICT starting ===")
    if force_now:
        logger.info("--now flag active: bypassing weekend/trading hours checks")

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
        min_excursion=MIN_SWING_EXCURSION_DOLLARS / 20,  # NQ: $20/point → $50 = 2.5 pts
    )
    fvg_detector = FVGDetector(lookback=FVG_LOOKBACK_CANDLES)
    # --- NUOVA ISTANZA ALLINEATA ---
    # Specifichiamo chiaramente il range minimo di 100 dollari richiesto
    zonation = Zonation(min_range_dollars=100.0, point_value=20.0)    
    confirmation = M1Confirmation(
        bars_needed=M1_BULLISH_NEEDED, total_bars=M1_CONFIRMATION_BARS,
    )
    target_calc = TargetCalculator(min_distance_ticks=MIN_TP_DISTANCE_DOLLARS / 5, tick_size=TICK_SIZE)  # $5 → 1 tick

    # --force-entry: submit a single order and monitor it
    if force_entry:
        logger.info(f"--force-entry={force_entry}: submitting forced order")
        try:
            account = ib_client.get_account()
            risk_mgr.start_session(account["equity"])
        except Exception:
            pass

        side = "buy" if force_entry == "long" else "sell"
        # Get current price
        try:
            df = ib_client.fetch_bars(SYMBOL, "1Min", limit=5)
            if not df.empty:
                price = df["close"].iloc[-1]
            else:
                price = 30000.0
        except Exception:
            price = 30000.0

        sl_price = price - 100 if force_entry == "long" else price + 100
        tp_price = price + 200 if force_entry == "long" else price - 200

        logger.info(f"Forced {force_entry.upper()} @ ~{price:.2f} | SL={sl_price:.2f} | TP={tp_price:.2f}")
        result = ib_client.submit_order(SYMBOL, 1, side, "market", stop_loss=sl_price)
        logger.info(f"Order result: {result}")

        # Monitor position
        for _ in range(600):  # monitor for ~10 minutes max
            time.sleep(1)
            pos = ib_client.get_position(SYMBOL)
            if pos is None:
                logger.info("Position closed — exiting force-entry mode")
                break
            if _ % 5 == 0:
                logger.info(f"P&L: {pos.get('unrealized_pl', 0):.2f}")

        logger.info("Force-entry monitoring ended")
        ib_client.disconnect()
        return

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
        if not force_now:
            if not is_weekday():
                logger.info("Weekend — sleeping until Monday")
                now = datetime.now()
                days_until_monday = (7 - now.weekday()) % 7
                if days_until_monday == 0:
                    days_until_monday = 1
                next_monday = now + timedelta(days=days_until_monday)
                sleep_until(parse_time(TRADING_START))
                continue

            if not in_trading_hours():
                wait_target = parse_time(TRADING_START)
                logger.info(f"Outside trading hours — waiting for {TRADING_START}")
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

        while (force_now or in_trading_hours()) and running:
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
                    logger.debug(f"M5 bars: {len(df_m5)}, swings: {len(swings)} "
                                 f"({len([s for s in swings if s.type=='high'])}H/{len([s for s in swings if s.type=='low'])}L)")

                    current_price = df_m5["close"].iloc[-1]
                    # Identifichiamo il prezzo di CHIUSURA dell'ultima candela M5 COMPLETATA (la penultima nel DataFrame)
                    closed_m5_price = df_m5["close"].iloc[-2] 
                    closed_m5_high = df_m5["high"].iloc[-2]
                    closed_m5_low = df_m5["low"].iloc[-2]

                    # 2. Detect FVGs and update closure tracking (always, for debug visibility)
                    new_fvgs = fvg_detector.detect(df_m5)
                    # Deduplicate by (start_timestamp, type). When the same FVG is
                    # re-detected in a later cycle (e.g., because the forming candle
                    # that served as C3 now has its final OHLC), refresh top/bottom
                    # in-place so downstream checks use the correct values.
                    seen = {(f.start_timestamp, f.type): f for f in active_fvgs}
                    unique_new = []
                    for f in new_fvgs:
                        key = (f.start_timestamp, f.type)
                        if key in seen:
                            seen[key].top = f.top
                            seen[key].bottom = f.bottom
                        else:
                            unique_new.append(f)
                    all_fvgs = fvg_detector.update_closure(active_fvgs + unique_new, df_m5)
                    active_fvgs = [f for f in all_fvgs if not f.closed]
                    closed_fvgs = [f for f in all_fvgs if f.closed]

                    # 3. Determine zone (Premium/Discount)
                    zone = zonation.determine(current_price, swings)
                    allowed_dir = zonation.allowed_direction(zone)

                    # -- FVG debug dump (always printed) ------------------------
                    logger.info(f"=== CYCLE {current_m5_index} ===")
                    logger.info(f"Price={current_price:.0f} | Zone={zone or 'NONE'} | Dir={allowed_dir or 'N/A'}")
                    logger.info(f"FVGs — {len(new_fvgs)} new, {len(active_fvgs)} open, {len(closed_fvgs)} closed")
                    for f in active_fvgs:
                        inside = " <-- PRICE INSIDE" if fvg_detector.is_price_inside(current_price, f) else ""
                        match = ""
                        if allowed_dir:
                            match = " * MATCH" if (f.type == "bullish" and allowed_dir == "long") or (f.type == "bearish" and allowed_dir == "short") else ""
                        logger.info(f"  [{f.type:>7}] gap={f.bottom:.0f}-{f.top:.0f}  (range={f.top - f.bottom:.0f}pt){inside}{match}")
                        ts = f.start_timestamp
                        if ts in df_m5.index:
                            pos = df_m5.index.get_loc(ts)
                            if pos + 2 < len(df_m5):
                                c0 = df_m5.iloc[pos]
                                c1 = df_m5.iloc[pos + 1]
                                c2 = df_m5.iloc[pos + 2]
                                ts0 = str(df_m5.index[pos])[:16]
                                logger.info(f"       C{pos} [{ts0}] O={c0['open']:.0f} H={c0['high']:.0f} L={c0['low']:.0f} C={c0['close']:.0f}")
                                ts1 = str(df_m5.index[pos+1])[:16]
                                logger.info(f"       C{pos+1} [{ts1}] O={c1['open']:.0f} H={c1['high']:.0f} L={c1['low']:.0f} C={c1['close']:.0f}")
                                ts2 = str(df_m5.index[pos+2])[:16]
                                logger.info(f"       C{pos+2} [{ts2}] O={c2['open']:.0f} H={c2['high']:.0f} L={c2['low']:.0f} C={c2['close']:.0f}")
                    # ----------------------------------------------------------

                    if zone is None:
                        logger.info(f"No zone: price={current_price:.0f}")
                        time.sleep(30)
                        continue
                    # --- NUOVO CONTROLLO: VERIFICA SOVRAPPOSIZIONE PARZIALE FVG/ZONA ---
                    signal_fvg = None
                    for fvg in active_fvgs:
                        # 1. Controlliamo prima di tutto se la candela M5 si è CHIUSA dentro questo FVG
                        if fvg_detector.is_price_inside(closed_m5_price, fvg):
                            
                            # 2. Se l'FVG è BULLISH, deve essere *almeno parzialmente* in DISCOUNT.
                            # Significa che la parte bassa dell'FVG (fvg.bottom) deve trovarsi SOTTO il midpoint.
                            if fvg.type == "bullish":
                                if zonation.midpoint is not None and fvg.bottom < zonation.midpoint:
                                    signal_fvg = fvg
                                    allowed_dir = "long"
                                    break # Setup valido trovato!
                                    
                            # 3. Se l'FVG è BEARISH, deve essere *almeno parzialmente* in PREMIUM.
                            # Significa che la parte alta dell'FVG (fvg.top) deve trovarsi SOPRA il midpoint.
                            elif fvg.type == "bearish":
                                if zonation.midpoint is not None and fvg.top > zonation.midpoint:
                                    signal_fvg = fvg
                                    allowed_dir = "short"
                                    break # Setup valido trovato!

                    if signal_fvg is None:
                        logger.info(f"No FVG match: zone={zone}, price={current_price:.0f}")
                        time.sleep(30)
                        continue

                    logger.info(f"Signal: {allowed_dir.upper()} — "
                                f"Zone={zone}, FVG={signal_fvg.type}, "
                                f"Price={current_price}, Gap=({signal_fvg.bottom:.2f}-{signal_fvg.top:.2f})")

                    # 5. Wait for M1 confirmation (ancorato al timestamp di chiusura della M5 che ha triggerato il segnale)
                    m5_trigger_ts = df_m5.index[-2].to_pydatetime()
                    target_time = m5_trigger_ts + timedelta(minutes=3, seconds=30)

                    logger.info(
                        f"Setup FVG rilevato (M5 close={m5_trigger_ts.strftime('%H:%M:%S')}). "
                        f"Attendo la formazione completa delle prossime 3 candele M1 fino alle {target_time.strftime('%H:%M:%S')}..."
                    )

                    # Ciclo di attesa controllato fino allo scadere dei 3 minuti richiesti
                    while datetime.now() < target_time:
                        time.sleep(5)  # Verifica ogni 5 secondi senza bloccare l'esecuzione o l'ascolto di segnali

                    logger.info("I 3 minuti M1 sono trascorsi. Recupero le barre dal broker...")

                    df_m1 = pd.DataFrame()
                    for attempt in range(MAX_RETRIES):
                        try:
                            # Richiediamo esattamente 3 barre (le 3 appena generate dopo il close M5)
                            df_m1 = ib_client.fetch_bars(SYMBOL, "1Min", limit=10)
                            break
                        except Exception as e:
                            logger.warning(f"Fetch M1 fallito (tentativo {attempt+1}): {e}")
                            time.sleep(RETRY_BASE_DELAY * (2 ** attempt))

                    if df_m1.empty or len(df_m1) < 3:
                        logger.warning("Dati M1 insufficienti o incompleti per la conferma, skip ciclo")
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

                    # 8. Set initial SL at the exact swing point defining the range extreme (Orange Circle)
                    initial_sl_swing = None
                    if allowed_dir == "long":
                        # Cerchiamo lo swing low che corrisponde al minimo assoluto del nostro Dealing Range (Livello 1 Fib)
                        for s in swings:
                            if s.type == "low" and s.price == zonation.range_bottom:
                                initial_sl_swing = s
                                break
                        # Fallback di sicurezza se non dovesse trovarlo per arrotondamenti
                        if initial_sl_swing is None:
                            lows = sorted([s for s in swings if s.type == "low"], key=lambda s: s.index, reverse=True)
                            initial_sl_swing = lows[0] if lows else None
                    else:
                        # Cerchiamo lo swing high che corrisponde al massimo assoluto del nostro Dealing Range (Livello 0 Fib)
                        for s in swings:
                            if s.type == "high" and s.price == zonation.range_top:
                                initial_sl_swing = s
                                break
                        # Fallback di sicurezza se non dovesse trovarlo per arrotondamenti
                        if initial_sl_swing is None:
                            highs = sorted([s for s in swings if s.type == "high"], key=lambda s: s.index, reverse=True)
                            initial_sl_swing = highs[0] if highs else None

                    if initial_sl_swing is None:
                        logger.info("No swing point for SL, skipping")
                        time.sleep(30)
                        continue

                    # 9. ENTRY
                    logger.info(f">>> ENTRY {allowed_dir.upper()} @ ~{current_price:.2f} "
                                f"| SL={initial_sl_swing.price:.2f} "
                                f"| TP targets: {[f'{t.price:.2f}' for t in tp_levels[:3]]}")

                    entered = order_mgr.enter_trade(
                        allowed_dir, current_price, initial_sl_swing, tp_levels
                    )
                    if entered:
                        in_trade = True
                        logger.info("Order submitted successfully")
                        # Let IB update its position list before the next loop iteration
                        time.sleep(2)
                    # Il motivo specifico del rifiuto è già loggato da OrderManager.enter_trade()

                else:
                    # === IN TRADE: monitor for trailing SL and TP ===
                    position = ib_client.get_position(SYMBOL)
                    if position is None:
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
    ib_client.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SniperBot ICT")
    parser.add_argument("--now", action="store_true", help="Bypass weekend and trading hours checks")
    parser.add_argument("--force-entry", choices=["long", "short"],
                        help="Force a market order (bypasses strategy)")
    args = parser.parse_args()
    run(force_now=args.now, force_entry=args.force_entry)
